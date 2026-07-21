"""Freyja Director application with the Road Mode reader enabled."""

from freyja.main import app
from freyja.roadmode import roadmode_router

app.include_router(roadmode_router)
