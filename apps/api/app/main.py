"""FastAPI application entrypoint."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.analysis import router as analysis_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log_path = Path(__file__).resolve().parents[1] / "reprove.log"
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
if not any(
    isinstance(handler, RotatingFileHandler)
    and Path(handler.baseFilename).resolve() == log_path.resolve()
    for handler in root_logger.handlers
):
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
    )
    root_logger.addHandler(file_handler)

load_dotenv(override=True)

app = FastAPI(
    title="REPROVE API",
    description="PDF extraction and structured research analysis.",
    version="0.1.0",
)

origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(analysis_router)
