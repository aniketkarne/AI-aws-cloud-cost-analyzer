"""Integration tests for the `/ask` endpoint.

These tests mock the OpenAI client AND the MySQL `get_connection` helper
so they don't need either service running. They verify the real wiring
between:

    * FastAPI request parsing
    * LLM SQL generation (mocked)
    * the `sql_safety` sanitizer
    * HTTP error codes returned to the client

Run with:
    pytest -q tests/test_ask_endpoint.py
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# --------------------------------------------------------------------------- #
# Stub the MySQL driver before anything imports `db`. Pytest's sys.path
# (see conftest.py) puts `backend/` on the path; importing `db` triggers
# `import mysql.connector`, which isn't installed in CI by default.
# --------------------------------------------------------------------------- #
mysql_pkg = types.ModuleType("mysql")
mysql_connector = types.ModuleType("mysql.connector")
mysql_connector.errorcode = types.SimpleNamespace(ER_BAD_DB_ERROR=1049)


class _FakeMySQLError(Exception):
    errno = None


mysql_connector.Error = _FakeMySQLError
mysql_connector.connect = lambda **kw: (_ for _ in ()).throw(
    RuntimeError("MySQL is stubbed in tests")
)
sys.modules.setdefault("mysql", mysql_pkg)
sys.modules.setdefault("mysql.connector", mysql_connector)

# Now safe to import the app
from main import app  # noqa: E402  (path comes from conftest.py)

# Both `routes.ask` and `backend.routes.ask` may resolve to different
# module objects depending on sys.path order. We patch whichever one
# the running app actually wired its route handlers with — discovered
# by inspecting the FastAPI app's router.
def _runtime_ask_module():
    for route in app.routes:
        if getattr(route, "path", None) == "/ask":
            return sys.modules[route.endpoint.__module__]
    raise RuntimeError("could not locate /ask route module")


_ASK_MODULE = _runtime_ask_module()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def llm_sequence():
    """Return a list of strings the mocked LLM will return, in order.

    `/ask` calls the LLM twice — once for SQL, once for the natural-
    language summary — so we accept up to two entries per test.
    """
    return ["SELECT 1", "Sure."]  # default: a benign SELECT


@pytest.fixture
def patched_llm(llm_sequence):
    """Patch `_ask_llm` so each call yields the next pre-canned string.

    Tests can override individual responses via
    `patched_llm.side_effect = lambda *a, **kw: "new value"`.
    Returns the underlying MagicMock (NOT a wrapper) so side_effect
    reassignment actually takes effect.
    """
    iter_strings = iter(llm_sequence)

    def _fake(system_prompt: str, user_prompt: str) -> str:
        try:
            return next(iter_strings)
        except StopIteration:
            return ""

    mock = MagicMock(side_effect=_fake)
    with patch.object(_ASK_MODULE, "_ask_llm", mock):
        yield mock


@pytest.fixture
def patched_db():
    """Patch `get_connection` so it returns a fake connection with a fake
    cursor. Tests configure the cursor's response by mutating the
    `state["rows"]` / `state["columns"]` dict AFTER setup.
    """
    from unittest.mock import PropertyMock

    state: dict = {"rows": [], "columns": ["date", "cost"]}
    fake_cursor = MagicMock()
    fake_cursor.fetchall.side_effect = lambda: state["rows"]
    # `cursor.description` is an attribute, not a method — use PropertyMock
    # so the route's `cursor.description` access picks up our state lookup.
    type(fake_cursor).description = PropertyMock(
        side_effect=lambda: [
            (c, None, None, None, None, None, None) for c in state["columns"]
        ]
    )
    fake_cursor.fetchall.return_value = state["rows"]
    fake_conn = MagicMock()
    fake_conn.is_connected.return_value = True
    fake_conn.cursor = MagicMock(return_value=fake_cursor)

    with patch.object(_ASK_MODULE, "get_connection", return_value=fake_conn):
        yield {"state": state, "cursor": fake_cursor, "conn": fake_conn}


# --------------------------------------------------------------------------- #
# /ask happy path
# --------------------------------------------------------------------------- #


class TestAskEndpointHappyPath:
    def test_returns_answer_data_and_sql_on_safe_select(
        self, client, patched_llm, patched_db
    ):
        # Set up the DB mock
        patched_db["state"]["rows"] = [("2025-01-01", 12.34)]
        patched_db["state"]["columns"] = ["date", "cost"]

        # SQL on first LLM call, summary on second.
        responses = iter(["SELECT * FROM cost_data", "EC2 cost was $12.34."])
        patched_llm.side_effect = lambda *a, **kw: next(responses)

        resp = client.post("/ask", json={"question": "What did we spend?"})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["sql"] == "SELECT * FROM cost_data"
        assert body["answer"] == "EC2 cost was $12.34."
        assert body["data"] == [{"date": "2025-01-01", "cost": 12.34}]

    def test_missing_question_returns_400(self, client, patched_llm, patched_db):
        resp = client.post("/ask", json={"not_a_question": "oops"})
        assert resp.status_code == 400
        assert "question" in resp.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# /ask security: hostile LLM output is rejected before reaching the DB
# --------------------------------------------------------------------------- #


class TestAskEndpointRejectsHostileSql:
    def test_drop_statement_is_rejected_with_400(
        self, client, patched_llm, patched_db
    ):
        # Simulate an LLM (or a prompt-injected LLM) emitting a DROP.
        responses = iter(
            [
                "DROP TABLE cost_data",
                "I am not going to summarise that.",
            ]
        )
        patched_llm.side_effect = lambda *a, **kw: next(responses)

        resp = client.post("/ask", json={"question": "delete everything"})

        assert resp.status_code == 400, resp.text
        assert "drop" in resp.json()["detail"].lower()

    def test_multi_statement_payload_is_truncated_to_first_select(
        self, client, patched_llm, patched_db
    ):
        # The first SELECT runs; the trailing DROP is dropped at sanitise.
        patched_db["cursor"].fetchall.return_value = []
        patched_db["state"]["rows"] = []
        patched_db["state"]["columns"] = ["x"]
        responses = iter(
            [
                "SELECT 1; DROP TABLE cost_data",
                "result is one.",
            ]
        )
        patched_llm.side_effect = lambda *a, **kw: next(responses)

        resp = client.post("/ask", json={"question": "pick first statement"})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["sql"] == "SELECT 1"

    def test_markdown_fenced_select_is_unwrapped(
        self, client, patched_llm, patched_db
    ):
        patched_db["cursor"].fetchall.return_value = []
        patched_db["state"]["rows"] = []
        patched_db["state"]["columns"] = ["ok"]
        responses = iter(["```sql\nSELECT 1\n```", "done."])
        patched_llm.side_effect = lambda *a, **kw: next(responses)

        resp = client.post("/ask", json={"question": "fence"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["sql"] == "SELECT 1"

    def test_delete_statement_is_rejected_with_400(
        self, client, patched_llm, patched_db
    ):
        responses = iter(
            [
                "DELETE FROM cost_data WHERE 1=1",
                "nope.",
            ]
        )
        patched_llm.side_effect = lambda *a, **kw: next(responses)

        resp = client.post("/ask", json={"question": "scrub"})

        assert resp.status_code == 400, resp.text

    def test_cte_write_smuggle_is_rejected_with_400(
        self, client, patched_llm, patched_db
    ):
        # MySQL 8 permits CTEs before writes: `WITH … DELETE` must not
        # reach the database even though the statement starts with WITH.
        responses = iter(
            [
                "WITH c AS (SELECT 1) DELETE FROM cost_data",
                "nope.",
            ]
        )
        patched_llm.side_effect = lambda *a, **kw: next(responses)

        resp = client.post("/ask", json={"question": "cte smuggle"})

        assert resp.status_code == 400, resp.text

    def test_into_outfile_is_rejected_with_400(
        self, client, patched_llm, patched_db
    ):
        responses = iter(
            [
                "SELECT * FROM cost_data INTO OUTFILE '/tmp/x'",
                "nope.",
            ]
        )
        patched_llm.side_effect = lambda *a, **kw: next(responses)

        resp = client.post("/ask", json={"question": "exfil"})

        assert resp.status_code == 400, resp.text


class TestStartupWiring:
    def test_startup_event_calls_initialize_tables(self):
        # Regression net for the `db.initialize_tables()` NameError that
        # made every boot fail: `from db import initialize_tables` binds
        # the function, not the module. The startup hook must call the
        # imported name.
        main_mod = sys.modules["main"]
        mock_init = MagicMock()
        with patch.object(main_mod, "initialize_tables", mock_init):
            main_mod.startup_event()
        mock_init.assert_called_once()
