import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Allow `python main.py` from this directory, and `uvicorn backend.main:app`
# from the repo root, to both find the `db` and `routes` modules.
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from backend.routes import upload, ask  # noqa: E402
from db import initialize_tables  # noqa: E402

app = FastAPI()

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    db.initialize_tables()

@app.get("/")
def root():
    return JSONResponse({"message": "Hello from FastAPI AWS Cost Analyzer"})

# Include the upload and ask routers
app.include_router(upload.router)
app.include_router(ask.router)

if __name__ == "__main__":
    # User can simply run: python main.py
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
