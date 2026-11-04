"""Sanitize LLM-generated SQL before executing it.

The natural-language `/ask` endpoint in `routes/ask.py` generates a SQL
query with the OpenAI API and runs it directly against MySQL. Anything
that lands in the LLM's output gets passed to `cursor.execute()` —
including DROP / DELETE / UPDATE / INSERT statements, multi-statement
payloads (`; DROP TABLE …`), or markdown-fenced ```sql ``` blocks.

This module applies the only sane policy for a read-only Q&A endpoint:

- strip Markdown code fences (```sql … ```)
- take the first statement only (split on `;`, string-literal aware)
- reject anything that isn't a SELECT / WITH / SHOW (case-insensitive,
  ignoring leading whitespace and comments)
- for `WITH` statements, parse the CTE list and require the main
  statement to be a SELECT — MySQL 8 permits CTEs before UPDATE /
  DELETE / INSERT, so a bare keyword check would let
  `WITH c AS (…) DELETE FROM …` through
- reject `INTO OUTFILE` / `INTO DUMPFILE` anywhere in the statement
  (SELECT can write files on the database host)
- raise `UnsafeSQLError` for anything that fails the policy so the
  caller can return a 400 to the client

Scanning is string-literal aware: `;`, `--` and `/* */` inside quoted
strings and backtick identifiers are left untouched, so legitimate
queries containing them are not mangled. Comments (`--`, `#`, `/* */`)
outside quotes are removed before validation.

The sanitizer is deliberately conservative. It is a defense-in-depth
control, not a substitute for read-only DB users. String literals are
parsed with default MySQL escaping rules (backslash escapes, doubled
quotes); a server running `NO_BACKSLASH_ESCAPES` could in principle
disagree with the scan on where a literal ends.
"""

from __future__ import annotations

import re
from typing import Final


class UnsafeSQLError(ValueError):
    """Raised when LLM-generated SQL fails the safety policy."""


# Statements we are willing to execute. Anything else (INSERT, UPDATE,
# DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, …) is rejected.
_ALLOWED_LEAD: Final[tuple[str, ...]] = ("SELECT", "WITH", "SHOW")

# The main statement after a WITH … CTE list must be a plain SELECT.
# MySQL also allows TABLE and parenthesized query expressions there;
# both are read-only but rare in LLM output, so they are rejected for a
# simpler contract.

_RE_FENCE_KV = re.compile(r"```(?:sql|mysql|sqlblock|postgresql)?\s*", re.IGNORECASE)
_RE_FENCE = re.compile(r"```", re.IGNORECASE)

_QUOTES: Final[str] = "'\"`"


def _skip_quoted(sql: str, i: int) -> int:
    """Return the index just past the quoted run starting at sql[i].

    Handles backslash escapes in ' and " literals and doubled-quote
    escapes in all three quote styles. Raises on an unterminated run.
    """
    quote = sql[i]
    i += 1
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "\\" and quote != "`":
            i += 2
            continue
        if ch == quote:
            if i + 1 < n and sql[i + 1] == quote:
                i += 2
                continue
            return i + 1
        i += 1
    raise UnsafeSQLError("SQL contains an unterminated string literal.")


def _strip_comments(sql: str) -> str:
    """Remove `--`, `#` and `/* */` comments outside quotes/identifiers.

    Comment introducers inside quoted strings and backtick identifiers
    are preserved verbatim. `--` only starts a comment when followed by
    whitespace or end of input (MySQL semantics), so `SELECT 5--3` is
    left intact.
    """
    out = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in _QUOTES:
            j = _skip_quoted(sql, i)
            out.append(sql[i:j])
            i = j
            continue
        if ch == "#":
            while i < n and sql[i] != "\n":
                i += 1
            out.append(" ")
            continue
        if ch == "-" and sql.startswith("--", i) and (
            i + 2 >= n or sql[i + 2] in " \t\r\n"
        ):
            while i < n and sql[i] != "\n":
                i += 1
            out.append(" ")
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end == -1:
                raise UnsafeSQLError("SQL contains an unterminated block comment.")
            out.append(" ")
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_fences(sql: str) -> str:
    # ```sql\nSELECT ...\n```
    # Most common pattern. The first fence sets the language; the second closes.
    fences = _RE_FENCE.findall(sql)
    if len(fences) >= 2:
        sql = _RE_FENCE_KV.sub("", sql, count=1)
        sql = _RE_FENCE.sub("", sql, count=1)
    return sql


def _split_statements(sql: str) -> list[str]:
    """Split on `;` outside string literals and identifiers.

    MySQL's `cursor.execute` rejects multi-statement strings unless
    `multi=True`, but we still want to drop anything past the first
    statement so a hostile string like `SELECT 1; DROP TABLE …` doesn't
    slip through if a future maintainer enables multi-statement mode.
    """
    parts = []
    start = 0
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in _QUOTES:
            i = _skip_quoted(sql, i)
            continue
        if ch == ";":
            parts.append(sql[start:i])
            start = i + 1
        i += 1
    parts.append(sql[start:])
    return parts


def _scan_tokens(stmt: str) -> list[tuple[str, str, int]]:
    """Tokenize a statement into (kind, value, depth) tuples.

    kind is 'word' (bare identifier/keyword), 'ident' (backtick-quoted
    identifier) or 'punct' (one of `(`, `)`, `,`). depth is the paren
    nesting level at the token. Raises on unbalanced parentheses.
    """
    tokens: list[tuple[str, str, int]] = []
    depth = 0
    i, n = 0, len(stmt)
    while i < n:
        ch = stmt[i]
        if ch in "'\"":
            i = _skip_quoted(stmt, i)
            continue
        if ch == "`":
            j = _skip_quoted(stmt, i)
            tokens.append(("ident", stmt[i:j], depth))
            i = j
            continue
        if ch == "(":
            tokens.append(("punct", "(", depth))
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth -= 1
            if depth < 0:
                raise UnsafeSQLError("SQL has unbalanced parentheses.")
            tokens.append(("punct", ")", depth))
            i += 1
            continue
        if ch == ",":
            tokens.append(("punct", ",", depth))
            i += 1
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (stmt[j].isalnum() or stmt[j] in "_$"):
                j += 1
            tokens.append(("word", stmt[i:j], depth))
            i = j
            continue
        i += 1
    if depth != 0:
        raise UnsafeSQLError("SQL has unbalanced parentheses.")
    return tokens


def _reject_file_writes(tokens: list[tuple[str, str, int]]) -> None:
    """Reject `INTO OUTFILE` / `INTO DUMPFILE` at any paren depth."""
    for idx, (kind, value, _depth) in enumerate(tokens):
        if kind == "word" and value.upper() == "INTO" and idx + 1 < len(tokens):
            nxt_kind, nxt_value, _ = tokens[idx + 1]
            if nxt_kind == "word" and nxt_value.upper() in ("OUTFILE", "DUMPFILE"):
                raise UnsafeSQLError(
                    "INTO OUTFILE / INTO DUMPFILE is not allowed: it writes "
                    "files on the database host."
                )


def _validate_with(tokens: list[tuple[str, str, int]]) -> None:
    """Validate `WITH [RECURSIVE] cte AS (…) [, cte AS (…)] … <main>`.

    MySQL permits a CTE list before SELECT, UPDATE, DELETE and INSERT,
    so the keyword check alone would let `WITH c AS (…) DELETE FROM …`
    through. Walk the CTE list and require the main statement to be a
    SELECT (optionally parenthesized).
    """
    i = 1  # skip the leading WITH
    if i < len(tokens) and tokens[i][0] == "word" and tokens[i][1].upper() == "RECURSIVE":
        i += 1

    while True:
        # CTE name: a bare or backtick-quoted identifier.
        if i >= len(tokens) or tokens[i][0] not in ("word", "ident") or tokens[i][2] != 0:
            raise UnsafeSQLError("Malformed WITH clause: expected a CTE name.")
        i += 1
        # AS
        if (
            i >= len(tokens)
            or tokens[i][0] != "word"
            or tokens[i][1].upper() != "AS"
            or tokens[i][2] != 0
        ):
            raise UnsafeSQLError("Malformed WITH clause: expected AS after CTE name.")
        i += 1
        # ( … ) body
        if i >= len(tokens) or tokens[i][:2] != ("punct", "(") or tokens[i][2] != 0:
            raise UnsafeSQLError("Malformed WITH clause: expected a parenthesized CTE body.")
        depth = 1
        i += 1
        while depth > 0:
            if i >= len(tokens):
                raise UnsafeSQLError("Malformed WITH clause: unbalanced CTE body.")
            kind, value, _ = tokens[i]
            if kind == "punct":
                if value == "(":
                    depth += 1
                elif value == ")":
                    depth -= 1
            i += 1
        # Either `,` (another CTE) or the main statement.
        if i < len(tokens) and tokens[i][:2] == ("punct", ","):
            i += 1
            continue
        break

    # Main statement: SELECT, optionally wrapped in parentheses.
    paren_wraps = 0
    while i < len(tokens) and tokens[i][:2] == ("punct", "("):
        paren_wraps += 1
        i += 1
    if (
        i >= len(tokens)
        or tokens[i][0] != "word"
        or tokens[i][2] != paren_wraps
    ):
        raise UnsafeSQLError("WITH must be followed by a SELECT statement.")
    main = tokens[i][1].upper()
    if main != "SELECT":
        raise UnsafeSQLError(
            f"WITH ... {main} is not allowed; the main statement must be SELECT."
        )


def _validate(tokens: list[tuple[str, str, int]]) -> None:
    if not tokens:
        raise UnsafeSQLError("LLM returned no SQL statement.")
    kind, value, depth = tokens[0]
    if kind != "word" or depth != 0:
        raise UnsafeSQLError("SQL must start with SELECT, WITH, or SHOW.")
    head = value.upper()
    if head in ("SELECT", "SHOW"):
        _reject_file_writes(tokens)
        return
    if head == "WITH":
        _validate_with(tokens)
        _reject_file_writes(tokens)
        return
    raise UnsafeSQLError(
        f"Only {', '.join(_ALLOWED_LEAD)} statements are allowed; got {head!r}."
    )


def sanitize_llm_sql(raw: str) -> str:
    """Return a safe-to-execute SQL string or raise `UnsafeSQLError`.

    Policy:
        1. Strip Markdown fences and (quote-aware) comments.
        2. Take the first statement only (split on `;` outside literals).
        3. Reject anything not starting with SELECT / WITH / SHOW.
        4. For WITH, require the main statement after the CTE list to
           be a SELECT.
        5. Reject INTO OUTFILE / INTO DUMPFILE anywhere in the statement.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise UnsafeSQLError("LLM returned empty SQL.")

    cleaned = _strip_fences(raw).strip()
    cleaned = _strip_comments(cleaned)

    statement = ""
    for part in _split_statements(cleaned):
        if part.strip():
            statement = part.strip()
            break
    if not statement:
        raise UnsafeSQLError("LLM returned no SQL statement.")

    _validate(_scan_tokens(statement))
    return statement
