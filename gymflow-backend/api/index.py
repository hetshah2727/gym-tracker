"""Vercel entry point: serves the FastAPI app as a Python serverless function.

All paths are rewritten here by vercel.json. Background jobs run through Vercel Cron -> /api/v1/cron/*.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402,F401
