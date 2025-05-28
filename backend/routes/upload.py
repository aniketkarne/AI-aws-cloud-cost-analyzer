from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import pandas as pd
import os
import io
from db import get_connection

router = APIRouter()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        # Validate file extension
        if not (
            file.filename.endswith(".csv") or 
            file.filename.endswith(".xls") or 
            file.filename.endswith(".xlsx")
        ):
            raise HTTPException(
                status_code=400, 
                detail="Unsupported file type. Please upload a CSV or Excel file."
            )

        # Save file temporarily
        temp_file_path = os.path.join("/tmp", file.filename)
        with open(temp_file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Parse file with pandas
        if file.filename.endswith(".csv"):
            df = pd.read_csv(temp_file_path)
        else:
            df = pd.read_excel(temp_file_path)

        # Insert parsed data into the database
        conn = get_connection()
        cursor = conn.cursor()
        # Insert raw billing records
        insert_query = """
            INSERT INTO cost_data (date, service, region, usage_type, cost)
            VALUES (%s, %s, %s, %s, %s)
        """
        records = []
        for _, row in df.iterrows():
            records.append((
                row.get("date") or row.get("usage_date"),
                row.get("service"),
                row.get("region"),
                row.get("usage_type"),
                row.get("cost")
            ))
        cursor.executemany(insert_query, records)
        conn.commit()
        # Update aggregated summary table
        cursor.execute("""
            INSERT INTO cost_summary (date, service, region, usage_type, total_cost)
            SELECT date, service, region, usage_type, SUM(cost)
            FROM cost_data
            GROUP BY date, service, region, usage_type
            ON DUPLICATE KEY UPDATE total_cost = VALUES(total_cost);
        """)
        conn.commit()
        cursor.close()
        conn.close()
        return JSONResponse({
            "message": "File uploaded, parsed, and stored successfully",
            "records_inserted": len(records)
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
