"""Uvicorn entry point for the RepoBrain API."""

from app.api.routes import app

__all__ = ["app"]
