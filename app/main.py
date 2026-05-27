import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.services.storage import init_db
from app.api import api_router
from app.services.sse_adapter import get_sse_adapter


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("storage", exist_ok=True)
    init_db()
    yield
    get_sse_adapter().shutdown()


app = FastAPI(title="Research Map Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)

# Serve frontend static files in production
frontend_dist = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "dist"
)
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True),
              name="frontend")


def main():
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
