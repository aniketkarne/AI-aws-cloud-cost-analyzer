"""Manual sanity-check of the SQL sanitizer.

Run with:
    cd AI-aws-cloud-cost-analyzer
    PYTHONPATH=backend python scripts/smoke_sql_safety.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sql_safety import sanitize_llm_sql, UnsafeSQLError  # noqa: E402


CASES = [
    # (raw_input, expected_output_or_None_to_expect_rejection)
    ("SELECT * FROM cost_data", "SELECT * FROM cost_data"),
    ("select * from cost_data;", "select * from cost_data"),
    ("  \nSELECT NOW()", "SELECT NOW()"),
    ("WITH x AS (SELECT 1) SELECT * FROM x", "WITH x AS (SELECT 1) SELECT * FROM x"),
    ("SHOW TABLES", "SHOW TABLES"),
    ("```sql\nSELECT 1\n```", "SELECT 1"),
    ("SELECT 1; DROP TABLE cost_data;", "SELECT 1"),
    ("DROP TABLE cost_data", None),
    ("DELETE FROM cost_data", None),
    ("UPDATE cost_data SET cost=0", None),
    # MySQL 8 allows CTEs before writes — the main statement after the
    # CTE list must be a SELECT, so these are rejected:
    ("WITH c AS (SELECT 1) DELETE FROM cost_data", None),
    ("WITH c AS (SELECT 1) UPDATE cost_data SET cost = 0", None),
    ("WITH RECURSIVE c AS (SELECT 1) INSERT INTO cost_data VALUES (1)", None),
    # SELECT ... INTO OUTFILE / DUMPFILE writes files on the DB host:
    ("SELECT * FROM cost_data INTO OUTFILE '/tmp/x'", None),
    ("SELECT * FROM cost_data INTO DUMPFILE '/tmp/x'", None),
    # Line/block comments on otherwise-safe SELECTs are stripped,
    # so these pass (a real prod query benefits from author comments).
    ("SELECT 1 -- harmless comment", "SELECT 1"),
    ("SELECT 1 /* block */", "SELECT 1"),
    # String-literal aware: `;`, `--`, `#` inside quotes are preserved.
    ("SELECT 'a;b' FROM t", "SELECT 'a;b' FROM t"),
    ("SELECT '--not a comment' FROM t", "SELECT '--not a comment' FROM t"),
    # `--` only starts a comment when followed by whitespace (MySQL
    # semantics), so arithmetic `5--3` stays intact.
    ("SELECT 5--3", "SELECT 5--3"),
    ("", None),
    ("```sql\nSELECT 1; DELETE FROM x\n```", "SELECT 1"),
    # Multi-statement smuggling attempts. The first `;` separates the
    # payload; only the SELECT half survives.
    ("SELECT 1;\nDROP TABLE x", "SELECT 1"),
    ("SELECT 1\n;\nDROP TABLE x", "SELECT 1"),
    ("  SELECT 1 ;\n   DELETE FROM x  ", "SELECT 1"),
    ("SELECT 1 /*safe*/; DELETE FROM x", "SELECT 1"),
    ("   ;;; SELECT 1 ;;;", "SELECT 1"),
    ("SELECT\n  *\nFROM cost_data\nWHERE cost > 0", "SELECT\n  *\nFROM cost_data\nWHERE cost > 0"),
    # Malformed input is rejected with a 400 instead of a DB error.
    ("SELECT 'abc FROM t", None),
    ("SELECT (1 FROM t", None),
]


def main() -> int:
    failures = 0
    for raw, expected in CASES:
        try:
            got = sanitize_llm_sql(raw)
        except UnsafeSQLError as exc:
            got = f"ERR({exc})"
        if expected is None:
            ok = str(got).startswith("ERR(")
        else:
            ok = got == expected
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}]  in={raw!r}  out={got!r}")
        if not ok:
            failures += 1
    print()
    print(f"{len(CASES) - failures}/{len(CASES)} cases passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
