from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .chain import ChainClient
from .config import settings
from .pipeline import JobStore, Pipeline


app = FastAPI(title="ProofFace Pipeline API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "cases").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.data_dir / "cases"), name="media")

jobs = JobStore()
pipeline = Pipeline()


def run_job(case_id: str, image_bytes: bytes, filename: str) -> None:
    try:
        result = pipeline.run(case_id, image_bytes, filename, lambda stage, progress, message: jobs.update(case_id, stage, progress, message))
        jobs.complete(case_id, result)
    except Exception as error:
        jobs.fail(case_id, error)


@app.get("/api/health")
def health() -> dict:
    chain = ChainClient().health()
    return {
        "ok": True,
        "searchConfigured": bool(settings.google_vision_api_key),
        "searchProvider": "Google Cloud Vision Web Detection",
        "chain": chain,
    }


@app.post("/api/investigations", status_code=202)
async def create_investigation(background_tasks: BackgroundTasks, image: UploadFile = File(...)) -> dict:
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, "Use a JPEG, PNG, or WEBP image.")
    image_bytes = await image.read(settings.max_upload_bytes + 1)
    if not image_bytes:
        raise HTTPException(400, "The uploaded image is empty.")
    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(413, "The image exceeds the 10 MB limit.")
    job = jobs.create(image.filename or "portrait")
    background_tasks.add_task(run_job, job["caseId"], image_bytes, image.filename or "portrait")
    return job


@app.get("/api/investigations/{case_id}")
def get_investigation(case_id: str) -> dict:
    job = jobs.get(case_id)
    if not job:
        raise HTTPException(404, "Investigation not found.")
    return job


@app.post("/api/investigations/{case_id}/verify")
def verify_investigation(case_id: str) -> dict:
    job = jobs.get(case_id)
    if not job or not job.get("result"):
        raise HTTPException(404, "Completed investigation not found.")
    result = job["result"]
    evidence = result["evidence"]
    match = result["match"]
    return pipeline.chain.verify(evidence["evidenceHash"], evidence["sourceHash"], match["postUrl"])


@app.post("/api/investigations/{case_id}/tamper-check")
def tamper_check(case_id: str) -> dict:
    job = jobs.get(case_id)
    if not job or not job.get("result"):
        raise HTTPException(404, "Completed investigation not found.")
    result = job["result"]
    evidence = result["evidence"]
    match = result["match"]
    verification = pipeline.chain.verify(
        evidence["evidenceHash"],
        "0" * 64,
        f"{match['postUrl']}?tampered=true",
    )
    return {**verification, "tamperDetected": not verification.get("matches", False)}
