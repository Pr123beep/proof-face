from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .chain import ChainClient
from .config import settings
from .face import FaceEngine
from .search import GoogleVisionSearch


StageCallback = Callable[[str, int, str], None]


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class Pipeline:
    def __init__(self) -> None:
        self.face = FaceEngine()
        self.search = GoogleVisionSearch(self.face)
        self.chain = ChainClient()

    def run(self, case_id: str, image_bytes: bytes, filename: str, update: StageCallback) -> dict:
        case_dir = settings.data_dir / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        update("face", 12, "Loading YuNet detector and SFace encoder")
        encoding = self.face.encode(image_bytes)
        (case_dir / "input.jpg").write_bytes(encoding.preview_jpeg)
        (case_dir / "face.jpg").write_bytes(encoding.crop_jpeg)
        (case_dir / "annotated.jpg").write_bytes(encoding.annotated_jpeg)
        (case_dir / "embedding.json").write_text(json.dumps(encoding.vector.tolist()), encoding="utf-8")
        update("face", 34, f"Encoded {len(encoding.vector)} dimensions · confidence {encoding.confidence:.3f}")

        update("search", 42, "Submitting face crop and source image to genuine reverse-image search")
        selected, search_metadata = self.search.search(
            encoding.crop_jpeg,
            encoding.preview_jpeg,
            encoding.vector,
        )
        update("search", 68, f"Matched a public {selected.platform} post via {selected.match_type} image evidence")

        captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        source_material = "\n".join([
            selected.page_url,
            selected.matched_image_sha256 or "provider-visual-match",
            selected.page_title,
        ]).encode("utf-8")
        source_hash = hashlib.sha256(source_material).hexdigest()
        payload = {
            "schema": "proof-face/evidence-v1",
            "case_id": case_id,
            "captured_at": captured_at,
            "input_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "face": {
                "model": "OpenCV SFace 2021dec",
                "detector": "OpenCV YuNet 2023mar",
                "embedding_sha256": encoding.embedding_sha256,
                "dimensions": int(len(encoding.vector)),
                "bounding_box": encoding.bbox,
                "detection_confidence": encoding.confidence,
            },
            "discovery": {
                "provider": search_metadata["provider"],
                "post_url": selected.page_url,
                "post_title": selected.page_title,
                "platform": selected.platform,
                "match_type": selected.match_type,
                "query_type": selected.query_type,
                "matched_image_url": selected.matched_image_url,
                "matched_image_sha256": selected.matched_image_sha256,
                "face_similarity": selected.face_similarity,
                "identity_confirmed": selected.identity_confirmed,
            },
        }
        evidence_hash = hashlib.sha256(canonical_json(payload)).hexdigest()
        (case_dir / "evidence-payload.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

        update("chain", 76, "Submitting the evidence fingerprint to the local EVM")
        chain_record = self.chain.record(evidence_hash, source_hash, selected.page_url)
        update("verify", 92, "Reading the contract state and recomputing the evidence match")
        verification = self.chain.verify(evidence_hash, source_hash, selected.page_url)
        if not verification.get("matches"):
            raise RuntimeError("The EVM transaction was mined, but contract re-verification failed.")

        identity_signal = 1.0 if selected.identity_confirmed else 0.70
        reverse_signal = selected.provider_score
        trust_score = round((0.20 * encoding.confidence + 0.45 * reverse_signal + 0.20 * identity_signal + 0.15) * 100)
        result = {
            "caseId": case_id,
            "filename": filename,
            "capturedAt": captured_at,
            "trustScore": max(0, min(99, trust_score)),
            "media": {
                "input": f"{settings.public_api_url}/media/{case_id}/input.jpg",
                "face": f"{settings.public_api_url}/media/{case_id}/face.jpg",
                "annotated": f"{settings.public_api_url}/media/{case_id}/annotated.jpg",
            },
            "face": {
                "dimensions": int(len(encoding.vector)),
                "detectionConfidence": encoding.confidence,
                "faceCount": encoding.face_count,
                "boundingBox": encoding.bbox,
                "embeddingHash": encoding.embedding_sha256,
                "vectorPreview": [round(float(value), 5) for value in encoding.vector[:8]],
                "model": "OpenCV YuNet + SFace",
            },
            "match": {
                "postUrl": selected.page_url,
                "postTitle": selected.page_title,
                "platform": selected.platform,
                "matchType": selected.match_type,
                "queryType": selected.query_type,
                "provider": search_metadata["provider"],
                "providerScore": round(selected.provider_score, 3),
                "faceSimilarity": selected.face_similarity,
                "identityConfirmed": selected.identity_confirmed,
                "matchedImageUrl": selected.matched_image_url,
                "socialPostsFound": search_metadata["social_posts_found"],
                "webEntities": search_metadata["web_entities"],
            },
            "evidence": {
                "evidenceHash": evidence_hash,
                "sourceHash": source_hash,
                "payloadPath": str(case_dir / "evidence-payload.json"),
            },
            "blockchain": chain_record,
            "verification": verification,
        }
        (case_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        update("complete", 100, "Evidence is anchored and independently re-verified")
        return result


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def create(self, filename: str) -> dict:
        case_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        job = {
            "caseId": case_id,
            "filename": filename,
            "status": "queued",
            "stage": "queued",
            "progress": 2,
            "message": "Investigation queued",
            "createdAt": now,
            "updatedAt": now,
            "events": [{"stage": "queued", "progress": 2, "message": "Investigation queued", "at": now}],
            "result": None,
            "error": None,
        }
        with self._lock:
            self._jobs[case_id] = job
        return dict(job)

    def update(self, case_id: str, stage: str, progress: int, message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            job = self._jobs[case_id]
            job.update({"status": "running", "stage": stage, "progress": progress, "message": message, "updatedAt": now})
            job["events"].append({"stage": stage, "progress": progress, "message": message, "at": now})

    def complete(self, case_id: str, result: dict) -> None:
        with self._lock:
            job = self._jobs[case_id]
            job.update({"status": "completed", "stage": "complete", "progress": 100, "message": "Verification complete", "result": result})

    def fail(self, case_id: str, error: Exception) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            job = self._jobs[case_id]
            job.update({"status": "failed", "message": str(error), "error": str(error), "updatedAt": now})
            job["events"].append({"stage": job["stage"], "progress": job["progress"], "message": str(error), "at": now, "error": True})

    def get(self, case_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(case_id)
            return json.loads(json.dumps(job)) if job else None
