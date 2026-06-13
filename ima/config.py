from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    scheme: str
    verify_tls: bool
    token: str | None
    username: str | None
    password: str | None
    app: str
    owner: str
    kv_annotations: str
    kv_knowledge: str
    kv_assets: str
    foundation_sec_endpoint: str | None
    foundation_sec_api_key: str | None
    llm_provider: str
    ollama_endpoint: str
    ollama_model: str

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


def load() -> Settings:
    return Settings(
        host=os.getenv("SPLUNK_HOST", "localhost"),
        port=int(os.getenv("SPLUNK_PORT", "8089")),
        scheme=os.getenv("SPLUNK_SCHEME", "https"),
        verify_tls=_bool(os.getenv("SPLUNK_VERIFY_TLS"), default=False),
        token=os.getenv("SPLUNK_TOKEN") or None,
        username=os.getenv("SPLUNK_USERNAME") or None,
        password=os.getenv("SPLUNK_PASSWORD") or None,
        app=os.getenv("SPLUNK_APP", "search"),
        owner=os.getenv("SPLUNK_OWNER", "nobody"),
        kv_annotations=os.getenv("IMA_KV_ANNOTATIONS", "ima_annotations"),
        kv_knowledge=os.getenv("IMA_KV_KNOWLEDGE", "ima_knowledge"),
        kv_assets=os.getenv("IMA_KV_ASSETS", "ima_assets"),
        foundation_sec_endpoint=os.getenv("FOUNDATION_SEC_ENDPOINT") or None,
        foundation_sec_api_key=os.getenv("FOUNDATION_SEC_API_KEY") or None,
        llm_provider=os.getenv("LLM_PROVIDER", "ollama").lower(),
        ollama_endpoint=os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M"),
    )
