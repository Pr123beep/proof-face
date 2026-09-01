from __future__ import annotations

import requests

from .config import settings


class ChainError(RuntimeError):
    pass


class ChainClient:
    def _post(self, path: str, payload: dict) -> dict:
        try:
            response = requests.post(f"{settings.chain_api_url}{path}", json=payload, timeout=45)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            detail = ""
            if getattr(error, "response", None) is not None:
                detail = f" ({error.response.text[:300]})"
            raise ChainError(f"Local EVM service is unavailable{detail}. Start it with `npm run chain`.") from error

    def health(self) -> dict:
        try:
            response = requests.get(f"{settings.chain_api_url}/health", timeout=3)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return {"ok": False}

    def record(self, evidence_hash: str, source_hash: str, source_url: str) -> dict:
        return self._post("/record", {
            "evidenceHash": f"0x{evidence_hash}",
            "sourceHash": f"0x{source_hash}",
            "sourceUrl": source_url,
        })

    def verify(self, evidence_hash: str, source_hash: str, source_url: str) -> dict:
        return self._post("/verify", {
            "evidenceHash": f"0x{evidence_hash}",
            "sourceHash": f"0x{source_hash}",
            "sourceUrl": source_url,
        })
