"""Integration tests for the `/upload` endpoint.

Focus: the untrusted multipart filename must never reach the filesystem
path (path traversal), and the temp file used for parsing must be
cleaned up. The MySQL connection is mocked so no database is needed.

Run with:
    pytest -q tests/test_upload_endpoint.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# --------------------------------------------------------------------------- #
# Stub the MySQL driver before anything imports `db` (same trick as
# test_ask_endpoint.py — self-contained so test ordering doesn't matter).
# --------------------------------------------------------------------------- #
mysql_pkg = types.ModuleType("mysql")
mysql_connector = types.ModuleType("mysql.connector")
mysql_connector.errorcode = types.SimpleNamespace(ER_BAD_DB_ERROR=1049)
mysql_connector.Error = type("Error", (Exception,), {"errno": None})
mysql_connector.connect = lambda **kw: (_ for _ in ()).throw(
    RuntimeError("MySQL is stubbed in tests")
)
sys.modules.setdefault("mysql", mysql_pkg)
sys.modules.setdefault("mysql.connector", mysql_connector)

from main import app  # noqa: E402  (path comes from conftest.py)

# Resolve the module object the running app actually wired the route
# with (handles `routes.upload` vs `backend.routes.upload` duality).
def _runtime_upload_module():
    for route in app.routes:
        if getattr(route, "path", None) == "/upload":
            return sys.modules[route.endpoint.__module__]
    raise RuntimeError("could not locate /upload route module")


_UPLOAD_MODULE = _runtime_upload_module()

CSV_BYTES = b"date,service,region,usage_type,cost\n2025-01-01,EC2,us-east-1,BoxUsage,1.5\n"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_db():
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.cursor = MagicMock(return_value=fake_cursor)
    with patch.object(_UPLOAD_MODULE, "get_connection", return_value=fake_conn):
        yield {"cursor": fake_cursor, "conn": fake_conn}


class TestUploadFilenameSafety:
    def test_bad_extension_returns_400_not_500(self, client, fake_db):
        # The extension check raises HTTPException(400); the generic
        # handler used to swallow it and re-raise as 500.
        resp = client.post(
            "/upload",
            files={"file": ("evil.sh", b"echo hi\n", "text/plain")},
        )
        assert resp.status_code == 400, resp.text

    def test_traversal_filename_neutralized(self, client, fake_db):
        # Old code joined the raw filename onto "/tmp", so this name
        # created /tmp/deep/nested/evil.csv (and ../.. escaped /tmp
        # entirely). The basename is now used only for the extension;
        # the write goes to a mkstemp() path instead.
        resp = client.post(
            "/upload",
            files={"file": ("deep/nested/evil.csv", CSV_BYTES, "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert not os.path.exists(os.path.join("/tmp", "deep"))

    def test_dotdot_filename_neutralized(self, client, fake_db):
        resp = client.post(
            "/upload",
            files={"file": ("../../etc/anything.csv", CSV_BYTES, "text/csv")},
        )
        assert resp.status_code == 200, resp.text

    def test_temp_file_removed_after_parse(self, client, fake_db, monkeypatch):
        real_mkstemp = tempfile.mkstemp
        created = []

        def spy(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            created.append(path)
            return fd, path

        monkeypatch.setattr(tempfile, "mkstemp", spy)
        resp = client.post(
            "/upload",
            files={"file": ("report.csv", CSV_BYTES, "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert created, "mkstemp was not used for the upload temp file"
        for path in created:
            assert path.startswith(tempfile.gettempdir())
            assert not os.path.exists(path), f"temp file left behind: {path}"

    def test_valid_csv_inserts_rows(self, client, fake_db):
        resp = client.post(
            "/upload",
            files={"file": ("report.csv", CSV_BYTES, "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["records_inserted"] == 1
        fake_db["cursor"].executemany.assert_called_once()
        rows = fake_db["cursor"].executemany.call_args[0][1]
        assert rows == [("2025-01-01", "EC2", "us-east-1", "BoxUsage", 1.5)]
