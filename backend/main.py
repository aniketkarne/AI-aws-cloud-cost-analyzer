import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.routes import upload, ask

import db

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
