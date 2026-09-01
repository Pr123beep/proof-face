from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from .config import settings
from .face import FaceEngine


VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
SOCIAL_HOSTS = {
    "x.com": "X",
    "twitter.com": "X",
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "m.facebook.com": "Facebook",
    "reddit.com": "Reddit",
    "pinterest.com": "Pinterest",
    "linkedin.com": "LinkedIn",
    "threads.net": "Threads",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "tumblr.com": "Tumblr",
    "vk.com": "VK",
}

POST_PATTERNS = {
    "X": re.compile(r"/(?:[^/]+)/(?:status|statuses)/\d+", re.I),
    "Instagram": re.compile(r"/(?:p|reel|tv)/[^/]+", re.I),
    "Facebook": re.compile(r"/(?:photo|permalink|posts|story|watch|reel)|/photo\.php", re.I),
    "Reddit": re.compile(r"/comments/|/r/[^/]+/s/", re.I),
    "Pinterest": re.compile(r"/pin/\d+", re.I),
    "LinkedIn": re.compile(r"/(?:posts|feed/update)/", re.I),
    "Threads": re.compile(r"/@[^/]+/post/", re.I),
    "TikTok": re.compile(r"/@[^/]+/video/\d+", re.I),
    "YouTube": re.compile(r"/(?:watch|shorts/)|youtu\.be/", re.I),
    "Tumblr": re.compile(r"/post/\d+", re.I),
    "VK": re.compile(r"/wall-?\d+_\d+", re.I),
}


class SearchError(RuntimeError):
    pass


@dataclass
class SearchCandidate:
    page_url: str
    page_title: str
    platform: str
    query_type: str
    match_type: str
    image_urls: list[str] = field(default_factory=list)
    provider_score: float = 0.0
    face_similarity: float | None = None
    matched_image_url: str | None = None
    matched_image_sha256: str | None = None
    identity_confirmed: bool = False


def normalize_url(value: str) -> str:
    parsed = urlsplit(value)
    query = [(key, val) for key, val in parse_qsl(parsed.query) if not key.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), urlencode(query), ""))


def platform_for_url(value: str) -> str | None:
    host = (urlsplit(value).hostname or "").lower().removeprefix("www.")
    for domain, platform in SOCIAL_HOSTS.items():
        if host == domain or host.endswith(f".{domain}"):
            return platform
    return None


def is_post_url(value: str, platform: str) -> bool:
    return bool(POST_PATTERNS[platform].search(value))


class GoogleVisionSearch:
    """Genuine reverse-image search using Google Cloud Vision Web Detection."""

    def __init__(self, face_engine: FaceEngine) -> None:
        self.face_engine = face_engine

    def _request(self, face_crop: bytes, full_image: bytes) -> list[dict]:
        if not settings.google_vision_api_key:
            raise SearchError(
                "GOOGLE_VISION_API_KEY is not configured. Enable Cloud Vision Web Detection, add the key to .env, and restart the API."
            )
        requests_payload = []
        for image_bytes in (face_crop, full_image):
            requests_payload.append({
                "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
                "features": [{"type": "WEB_DETECTION", "maxResults": 50}],
            })
        try:
            response = requests.post(
                VISION_ENDPOINT,
                params={"key": settings.google_vision_api_key},
                json={"requests": requests_payload},
                timeout=settings.vision_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            detail = ""
            if getattr(error, "response", None) is not None:
                detail = f" ({error.response.text[:300]})"
            raise SearchError(f"Google Vision reverse-image search failed{detail}") from error

        responses = payload.get("responses", [])
        if not responses:
            raise SearchError("Google Vision returned no web-detection response.")
        for item in responses:
            if item.get("error"):
                raise SearchError(f"Google Vision error: {item['error'].get('message', 'unknown error')}")
        return responses

    @staticmethod
    def _candidates(responses: list[dict]) -> list[SearchCandidate]:
        deduped: dict[str, SearchCandidate] = {}
        for response_index, response in enumerate(responses):
            query_type = "face crop" if response_index == 0 else "full image"
            web = response.get("webDetection", {})
            for page in web.get("pagesWithMatchingImages", []):
                raw_url = page.get("url", "")
                platform = platform_for_url(raw_url)
                if not platform or not is_post_url(raw_url, platform):
                    continue
                page_url = normalize_url(raw_url)
                full = [item.get("url") for item in page.get("fullMatchingImages", []) if item.get("url")]
                partial = [item.get("url") for item in page.get("partialMatchingImages", []) if item.get("url")]
                match_type = "full" if full else "partial"
                score = (0.83 if full else 0.70) + (0.04 if query_type == "face crop" else 0)
                candidate = SearchCandidate(
                    page_url=page_url,
                    page_title=page.get("pageTitle") or f"Matching {platform} post",
                    platform=platform,
                    query_type=query_type,
                    match_type=match_type,
                    image_urls=list(dict.fromkeys(full + partial)),
                    provider_score=min(score, 0.99),
                )
                previous = deduped.get(page_url)
                if previous is None or candidate.provider_score > previous.provider_score:
                    deduped[page_url] = candidate
                elif previous:
                    previous.image_urls = list(dict.fromkeys(previous.image_urls + candidate.image_urls))
        return sorted(deduped.values(), key=lambda item: item.provider_score, reverse=True)

    @staticmethod
    def _download_image(url: str) -> bytes | None:
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return None
            for answer in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)):
                address = ipaddress.ip_address(answer[4][0])
                if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
                    return None
            response = requests.get(
                url,
                timeout=15,
                stream=True,
                headers={"user-agent": "ProofFace/1.0 reverse-image-verifier"},
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "image" not in content_type.lower():
                return None
            chunks = []
            total = 0
            for chunk in response.iter_content(128 * 1024):
                total += len(chunk)
                if total > 10 * 1024 * 1024:
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
        except requests.RequestException:
            return None

    def search(self, face_crop: bytes, full_image: bytes, reference_vector) -> tuple[SearchCandidate, dict]:
        responses = self._request(face_crop, full_image)
        candidates = self._candidates(responses)
        if not candidates:
            raise SearchError(
                "The reverse-image search found no matching social-media post URL. Try an image that is already published in a public post."
            )

        for candidate in candidates[:8]:
            best_similarity = -1.0
            for image_url in candidate.image_urls[:4]:
                image = self._download_image(image_url)
                if not image:
                    continue
                remote = self.face_engine.encode_remote(image)
                if remote is None:
                    continue
                similarity = self.face_engine.cosine_similarity(reference_vector, remote.vector)
                if similarity > best_similarity:
                    best_similarity = similarity
                    candidate.face_similarity = round(similarity, 6)
                    candidate.matched_image_url = image_url
                    candidate.matched_image_sha256 = hashlib.sha256(image).hexdigest()
                    candidate.identity_confirmed = similarity >= 0.363
            if candidate.identity_confirmed:
                candidate.provider_score = min(0.99, candidate.provider_score + 0.08)

        candidates.sort(
            key=lambda item: (item.identity_confirmed, item.face_similarity or -1, item.provider_score),
            reverse=True,
        )
        selected = candidates[0]
        if settings.require_face_confirmation and not selected.identity_confirmed:
            raise SearchError(
                "A social post was found, but its remote image could not be independently confirmed with SFace. Set REQUIRE_FACE_CONFIRMATION=false to accept Google's visual match signal."
            )

        metadata = {
            "provider": "Google Cloud Vision Web Detection",
            "queries_sent": 2,
            "social_posts_found": len(candidates),
            "web_entities": [
                {"description": item.get("description", ""), "score": item.get("score")}
                for response in responses
                for item in response.get("webDetection", {}).get("webEntities", [])[:5]
            ][:8],
            "candidate_urls": [item.page_url for item in candidates[:10]],
        }
        return selected, metadata
