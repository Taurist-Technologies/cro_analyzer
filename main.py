"""
CRO Analyzer Service - Main Application

A high-performance FastAPI backend service with distributed task processing
that captures website screenshots using Playwright and analyzes them with
Claude AI (Anthropic) to identify Conversion Rate Optimization (CRO) issues.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routes import router

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="CRO Analyzer Service")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routes from routes.py
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=60, workers=2)
