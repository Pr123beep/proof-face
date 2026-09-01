from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import cv2
import numpy as np
import requests

from .config import settings


YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SFACE_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"


class FaceError(RuntimeError):
    pass


@dataclass
class FaceEncoding:
    vector: np.ndarray
    embedding_sha256: str
    bbox: list[int]
    landmarks: list[list[int]]
    confidence: float
    face_count: int
    preview_jpeg: bytes
    crop_jpeg: bytes
    annotated_jpeg: bytes


class FaceEngine:
    """OpenCV YuNet detection + SFace 128-dimensional face encoding."""

    _download_lock = Lock()

    def __init__(self) -> None:
        self.model_dir = settings.model_dir
        self.yunet_path = self.model_dir / "face_detection_yunet_2023mar.onnx"
        self.sface_path = self.model_dir / "face_recognition_sface_2021dec.onnx"
        self._detector = None
        self._recognizer = None
        self._inference_lock = Lock()

    def _download(self, url: str, target: Path) -> None:
        if target.exists() and target.stat().st_size > 50_000:
            return
        self.model_dir.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".download")
        with requests.get(url, stream=True, timeout=90, allow_redirects=True) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_content(1024 * 256):
                    handle.write(chunk)
        if partial.stat().st_size <= 50_000:
            partial.unlink(missing_ok=True)
            raise FaceError(f"Downloaded model is unexpectedly small: {target.name}")
        partial.replace(target)

    def _load(self) -> None:
        if self._detector is not None:
            return
        with self._download_lock:
            self._download(YUNET_URL, self.yunet_path)
            self._download(SFACE_URL, self.sface_path)
        try:
            self._detector = cv2.FaceDetectorYN.create(str(self.yunet_path), "", (320, 320), 0.85, 0.3, 5000)
            self._recognizer = cv2.FaceRecognizerSF.create(str(self.sface_path), "")
        except cv2.error as error:
            raise FaceError(f"Could not initialize OpenCV face models: {error}") from error

    @staticmethod
    def decode(image_bytes: bytes) -> np.ndarray:
        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FaceError("The uploaded file is not a readable JPEG, PNG, or WEBP image.")
        height, width = image.shape[:2]
        if min(height, width) < 80:
            raise FaceError("The image is too small. Use an image at least 80 × 80 pixels.")
        return image

    @staticmethod
    def _jpeg(image: np.ndarray, quality: int = 92) -> bytes:
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise FaceError("Could not encode the processed face image.")
        return encoded.tobytes()

    def encode(self, image_bytes: bytes) -> FaceEncoding:
        self._load()
        image = self.decode(image_bytes)
        height, width = image.shape[:2]
        with self._inference_lock:
            self._detector.setInputSize((width, height))
            _, faces = self._detector.detect(image)
            if faces is None or len(faces) == 0:
                raise FaceError("No face was detected. Use a clear, front-facing portrait with good lighting.")

            face = max(faces, key=lambda item: float(item[2] * item[3]))
            aligned = self._recognizer.alignCrop(image, face)
            vector = self._recognizer.feature(aligned).flatten().astype(np.float32)
        norm = float(np.linalg.norm(vector))
        if norm <= 0:
            raise FaceError("OpenCV returned an invalid face embedding.")
        vector /= norm

        x, y, w, h = [int(round(float(value))) for value in face[:4]]
        x, y = max(0, x), max(0, y)
        w, h = min(width - x, w), min(height - y, h)
        annotated = image.copy()
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (185, 248, 73), max(2, width // 350))
        landmarks = []
        for index in range(5):
            point = [int(round(float(face[4 + index * 2]))), int(round(float(face[5 + index * 2])))]
            landmarks.append(point)
            cv2.circle(annotated, tuple(point), max(2, width // 420), (73, 221, 112), -1)

        return FaceEncoding(
            vector=vector,
            embedding_sha256=hashlib.sha256(vector.tobytes()).hexdigest(),
            bbox=[x, y, w, h],
            landmarks=landmarks,
            confidence=round(float(face[14]), 6),
            face_count=int(len(faces)),
            preview_jpeg=self._jpeg(image),
            crop_jpeg=self._jpeg(aligned),
            annotated_jpeg=self._jpeg(annotated),
        )

    def encode_remote(self, image_bytes: bytes) -> FaceEncoding | None:
        try:
            return self.encode(image_bytes)
        except FaceError:
            return None

    @staticmethod
    def cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
        return float(np.clip(np.dot(first, second), -1.0, 1.0))
