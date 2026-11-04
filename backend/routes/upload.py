from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import pandas as pd
import os
import tempfile
from db import get_connection

router = APIRouter()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        # Validate file extension
        filename = os.path.basename(file.filename or "")
        if not filename.endswith((".csv", ".xls", ".xlsx")):
            raise HTTPException(
                status_code=400, 
                detail="Unsupported file type. Please upload a CSV or Excel file."
            )
        suffix = os.path.splitext(filename)[1].lower()

        # Save to a private temp file. The client-supplied filename is
        # untrusted: joining it onto "/tmp" let a crafted multipart name
        # like "../../etc/anything.csv" write anywhere the process can.
        # mkstemp() picks the path and the file is removed after parsing.
        fd, temp_file_path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as f:
                content = await file.read()
                f.write(content)

            # Parse file with pandas
            if suffix == ".csv":
                df = pd.read_csv(temp_file_path)
            else:
                df = pd.read_excel(temp_file_path)
        finally:
            os.remove(temp_file_path)

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
