"""Natural-language → SQL → summarization endpoint.

Uses the modern openai>=1.0 SDK (client.chat.completions.create).
Model defaults to gpt-4o-mini for cost-effective natural-language SQL
generation. Override with the OPENAI_MODEL env var.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import os

from openai import OpenAI

from db import get_connection


_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY environment variable is not set.",
            )
        _client = OpenAI(api_key=api_key)
    return _client


router = APIRouter()


def _ask_llm(system_prompt: str, user_prompt: str) -> str:
    """Single-turn chat completion helper."""
    client = _get_client()
    resp = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


@router.post("/ask")
async def ask_question(payload: dict):
    if "question" not in payload:
        raise HTTPException(status_code=400, detail="Field 'question' is required.")
    question = payload["question"]

    # 1. Generate SQL query from natural language.
    sql_query = _ask_llm(
        system_prompt="You generate MySQL SQL queries.",
        user_prompt=(
            "Generate an SQL query for MySQL based on the following user "
            "question. Use the 'cost_data' or 'cost_summary' tables. "
            f"Question: \"{question}\". "
            "Return only the SQL query without additional explanation."
        ),
    )

    # 2. Execute SQL against the database.
    conn = get_connection()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            data = [dict(zip(columns, row)) for row in rows]
        finally:
            cursor.close()
    finally:
        conn.close()

    # 3. Summarize results via LLM.
    answer = _ask_llm(
        system_prompt="You provide concise AWS cost insights.",
        user_prompt=(
            "You are an AWS cost analysis assistant. "
            "Use the following query results to answer the user's question.\n"
            f"Question: \"{question}\"\n"
            f"Data: {data}"
        ),
    )

    return JSONResponse(
        {
            "answer": answer,
            "data": data,
            "sql": sql_query,
        }
    )