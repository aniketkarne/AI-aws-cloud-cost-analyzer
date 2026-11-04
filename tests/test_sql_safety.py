"""Pytest suite for the LLM → SQL sanitizer.

These tests target `backend.sql_safety` directly. The sanitizer is the
defense-in-depth control that keeps a hostile LLM (or a hostile user
question, fed verbatim into the LLM) from getting DROP / DELETE / UPDATE
statements into `cursor.execute` via the `/ask` endpoint.

Run with:
    PYTHONPATH=backend pytest -q tests/
"""
from __future__ import annotations

import pytest

from sql_safety import UnsafeSQLError, sanitize_llm_sql


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


class TestSanitizerHappyPath:
    def test_passes_through_plain_select(self):
        assert sanitize_llm_sql("SELECT * FROM cost_data") == "SELECT * FROM cost_data"

    def test_strips_trailing_semicolon(self):
        assert sanitize_llm_sql("SELECT 1;") == "SELECT 1"

    def test_normalises_lowercase_keyword(self):
        assert sanitize_llm_sql("select * from cost_data") == "select * from cost_data"

    def test_preserves_internal_whitespace(self):
        sql = "SELECT\n  *\nFROM cost_data\nWHERE cost > 0"
        assert sanitize_llm_sql(sql) == sql

    def test_accepts_with_cte(self):
        sql = "WITH x AS (SELECT 1) SELECT * FROM x"
        assert sanitize_llm_sql(sql) == sql

    def test_accepts_show(self):
        assert sanitize_llm_sql("SHOW TABLES") == "SHOW TABLES"

    def test_strips_markdown_fence(self):
        assert sanitize_llm_sql("```sql\nSELECT 1\n```") == "SELECT 1"

    def test_strips_markdown_fence_without_language_tag(self):
        assert sanitize_llm_sql("```\nSELECT NOW()\n```") == "SELECT NOW()"

    def test_strips_line_comment_on_safe_statement(self):
        assert sanitize_llm_sql("SELECT 1 -- harmless note") == "SELECT 1"

    def test_strips_block_comment_on_safe_statement(self):
        assert sanitize_llm_sql("SELECT 1 /* note */") == "SELECT 1"


# --------------------------------------------------------------------------- #
# Adversarial / smuggling attempts
# --------------------------------------------------------------------------- #


class TestSanitizerRejectsUnsafe:
    @pytest.mark.parametrize(
        "raw",
        [
            "DROP TABLE cost_data",
            "drop table cost_data",
            "DROP DATABASE aws_costs",
            "DELETE FROM cost_data",
            "UPDATE cost_data SET cost = 0",
            "INSERT INTO cost_data VALUES (1, '2025-01-01', 'EC2', 'us-east-1', 'BoxUsage', 0.0)",
            "TRUNCATE TABLE cost_data",
            "CREATE TABLE evil (id INT)",
            "ALTER TABLE cost_data ADD COLUMN evil TEXT",
            "GRANT ALL ON *.* TO 'evil'@'%'",
            "REVOKE ALL ON *.* FROM 'evil'@'%'",
            "RENAME TABLE cost_data TO evil",
            "REPLACE INTO cost_data VALUES (1, '2025-01-01', 'EC2', 'us-east-1', 'BoxUsage', 0.0)",
        ],
    )
    def test_blocks_write_or_ddl_keywords(self, raw):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql(raw)

    def test_rejects_empty_string(self):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql("   \n  ")

    def test_rejects_only_semicolons(self):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql(";;;")


# --------------------------------------------------------------------------- #
# Multi-statement / comment-trailer injection
# --------------------------------------------------------------------------- #


class TestSanitizerMultiStatement:
    def test_drops_anything_after_first_semicolon(self):
        assert sanitize_llm_sql("SELECT 1; DROP TABLE cost_data") == "SELECT 1"

    def test_drops_ddl_smuggled_after_fence(self):
        assert (
            sanitize_llm_sql("```sql\nSELECT 1; DELETE FROM x\n```")
            == "SELECT 1"
        )

    def test_drops_smuggled_ddl_with_newline(self):
        assert sanitize_llm_sql("SELECT 1;\nDROP TABLE x") == "SELECT 1"

    def test_drops_smuggled_delete_after_bracket(self):
        assert (
            sanitize_llm_sql("SELECT 1 /*safe*/; DELETE FROM x")
            == "SELECT 1"
        )

    def test_strips_leading_semicolons_and_whitespace(self):
        assert sanitize_llm_sql("   ;;; SELECT 1 ;;;") == "SELECT 1"

    def test_rejects_trailing_comment_marker_smuggle(self):
        # If a future LLM tries to smuggle `;--\nDROP …`, step 2
        # truncates at `;`, so only the legitimate SELECT survives once
        # comments are stripped (the policy allows author comments on
        # read queries).
        assert sanitize_llm_sql("SELECT 1 -- note\n") == "SELECT 1"


# --------------------------------------------------------------------------- #
# CTE / file-write bypasses (MySQL 8 semantics)
# --------------------------------------------------------------------------- #


class TestSanitizerCteBypass:
    """MySQL 8 permits CTEs before UPDATE / DELETE / INSERT — a bare
    keyword check on the statement head would let `WITH … DELETE`
    through. The main statement after the CTE list must be a SELECT."""

    @pytest.mark.parametrize(
        "raw",
        [
            "WITH c AS (SELECT 1) DELETE FROM cost_data",
            "WITH RECURSIVE c AS (SELECT 1) UPDATE cost_data SET cost = 0",
            "WITH c AS (SELECT 1) INSERT INTO cost_data VALUES (1)",
            "WITH c AS (SELECT 1) REPLACE INTO cost_data VALUES (1)",
            "WITH c AS (SELECT 1) DROP TABLE cost_data",
            "with c as (select 1) delete from cost_data",
        ],
    )
    def test_rejects_write_as_cte_main_statement(self, raw):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql(raw)

    @pytest.mark.parametrize(
        "raw",
        [
            "WITH c AS (SELECT 1) TABLE cost_data",
            "WITH c AS (SELECT 1)",
            "WITH c AS SELECT 1",
            "WITH",
        ],
    )
    def test_rejects_malformed_with(self, raw):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql(raw)

    def test_rejects_unbalanced_cte_body(self):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql("WITH c AS (SELECT 1 SELECT * FROM cost_data")

    def test_accepts_multi_cte_select(self):
        sql = (
            "WITH a AS (SELECT 1), b AS (SELECT 2) "
            "SELECT * FROM a JOIN b"
        )
        assert sanitize_llm_sql(sql) == sql

    def test_accepts_recursive_cte_select(self):
        sql = "WITH RECURSIVE c AS (SELECT 1) SELECT * FROM c"
        assert sanitize_llm_sql(sql) == sql

    def test_accepts_parenthesized_select_main(self):
        sql = "WITH c AS (SELECT 1) (SELECT * FROM c)"
        assert sanitize_llm_sql(sql) == sql

    def test_accepts_lowercase_with_select(self):
        sql = "with c as (select 1) select * from c"
        assert sanitize_llm_sql(sql) == sql


class TestSanitizerFileWriteBypass:
    """SELECT ... INTO OUTFILE / DUMPFILE writes files on the DB host."""

    @pytest.mark.parametrize(
        "raw",
        [
            "SELECT * FROM cost_data INTO OUTFILE '/tmp/x'",
            "SELECT * FROM cost_data INTO DUMPFILE '/tmp/x'",
            "select * from cost_data into outfile '/tmp/x'",
            "WITH c AS (SELECT * FROM cost_data INTO OUTFILE '/tmp/x') SELECT 1",
        ],
    )
    def test_rejects_into_outfile_and_dumpfile(self, raw):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql(raw)

    def test_accepts_select_into_variable(self):
        # SELECT ... INTO @var is read-only-ish (session variable) and
        # must not be caught by the OUTFILE/DUMPFILE rule.
        sql = "SELECT cost INTO @c FROM cost_data LIMIT 1"
        assert sanitize_llm_sql(sql) == sql


# --------------------------------------------------------------------------- #
# String-literal-aware scanning
# --------------------------------------------------------------------------- #


class TestStringLiteralAwareness:
    def test_preserves_semicolon_inside_literal(self):
        sql = "SELECT 'a;b' FROM cost_data"
        assert sanitize_llm_sql(sql) == sql

    def test_preserves_comment_markers_inside_literal(self):
        sql = "SELECT '--not a comment', '#neither' FROM cost_data"
        assert sanitize_llm_sql(sql) == sql

    def test_preserves_dashes_inside_literal(self):
        sql = "SELECT * FROM cost_data WHERE note = 'x -- y'"
        assert sanitize_llm_sql(sql) == sql

    def test_preserves_doubled_quote_escape(self):
        sql = "SELECT 'it''s; fine' FROM cost_data"
        assert sanitize_llm_sql(sql) == sql

    def test_preserves_backslash_escaped_quote(self):
        sql = "SELECT 'it\\'s; fine' FROM cost_data"
        assert sanitize_llm_sql(sql) == sql

    def test_non_comment_double_dash_kept(self):
        # MySQL: `--` only starts a comment when followed by whitespace,
        # so `5--3` is arithmetic, not a comment.
        sql = "SELECT 5--3"
        assert sanitize_llm_sql(sql) == sql

    def test_rejects_unterminated_literal(self):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql("SELECT 'abc FROM cost_data")

    def test_rejects_unterminated_block_comment(self):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql("SELECT 1 /* note")

    def test_rejects_unbalanced_parens(self):
        with pytest.raises(UnsafeSQLError):
            sanitize_llm_sql("SELECT (1 FROM cost_data")

    def test_strips_hash_comment(self):
        assert sanitize_llm_sql("SELECT 1 # note") == "SELECT 1"
