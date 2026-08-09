"""Vercel Serverless Function entrypoint for Job Hunter Flask Web Dashboard."""
import os
import sys
from pathlib import Path

# Ensure project root is in python path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app

# Export WSGI application for Vercel
app = app
