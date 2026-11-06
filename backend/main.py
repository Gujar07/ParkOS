"""
ParkOS Backend Server Entry Point.
Run directly with:
    python main.py
or:
    uvicorn app.main:app --reload
"""
import os
import sys
import uvicorn

# Ensure the backend directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("APP_ENV", "development") == "development"

    print(f"Starting ParkOS Backend on http://{host}:{port} ...")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
