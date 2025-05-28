from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import openai
import os
from db import get_connection

# configure OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

router = APIRouter()

@router.post("/ask")
async def ask_question(payload: dict):
    if "question" not in payload:
        raise HTTPException(status_code=400, detail="Field 'question' is required.")
    question = payload["question"]

    # 1. Generate SQL query from natural language
    sql_prompt = (
        f"Generate an SQL query for MySQL based on the following user question. "
        f"Use the 'cost_data' or 'cost_summary' tables. "
        f"Question: \"{question}\". "
        f"Return only the SQL query without additional explanation."
    )
    sql_resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You generate MySQL SQL queries."},
            {"role": "user", "content": sql_prompt}
        ]
    )
    sql_query = sql_resp.choices[0].message.content.strip()

    # 2. Execute SQL against the database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql_query)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    data = [dict(zip(columns, row)) for row in rows]
    cursor.close()
    conn.close()

    # 3. Summarize results via LLM
    summary_prompt = (
        f"You are an AWS cost analysis assistant. "
        f"Use the following query results to answer the user's question.\n"
        f"Question: \"{question}\"\n"
        f"Data: {data}"
    )
    sum_resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You provide concise AWS cost insights."},
            {"role": "user", "content": summary_prompt}
        ]
    )
    answer = sum_resp.choices[0].message.content.strip()

    return JSONResponse({
        "answer": answer,
        "data": data,
        "sql": sql_query
    })
