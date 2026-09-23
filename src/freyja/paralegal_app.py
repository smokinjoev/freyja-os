"""Freyja Director application with the Paralegal Enclave enabled."""

from contextlib import asynccontextmanager

from freyja.main import app
from freyja.paralegal_enclave import paralegal_router, start_auto_scan, stop_auto_scan

_director_lifespan = app.router.lifespan_context


@asynccontextmanager
async def paralegal_lifespan(app_instance):
    async with _director_lifespan(app_instance):
        start_auto_scan()
        try:
            yield
        finally:
            await stop_auto_scan()


app.include_router(paralegal_router)
app.router.lifespan_context = paralegal_lifespan
