import os
from dataclasses import dataclass, field


def _f(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass
class Settings:
    groq_api_key: str = field(default_factory=lambda: _f("GROQ_API_KEY", ""))
    primary_model: str = field(default_factory=lambda: _f("GROQ_MODEL", "openai/gpt-oss-120b"))
    fallback_model: str = field(default_factory=lambda: _f("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b"))
    llm_timeout_s: float = field(default_factory=lambda: float(_f("LLM_TIMEOUT_S", "20")))
    chroma_dir: str = field(default_factory=lambda: _f("CHROMA_DIR", "./chroma"))
    kb_dir: str = field(default_factory=lambda: _f("KB_DIR", "./kb"))
    db_path: str = field(default_factory=lambda: _f("DB_PATH", "./triage.db"))
    top_k: int = field(default_factory=lambda: int(_f("TOP_K", "3")))
    min_retrieval_score: float = field(default_factory=lambda: float(_f("MIN_RETRIEVAL_SCORE", "0.35")))
    max_revisions: int = field(default_factory=lambda: int(_f("MAX_REVISIONS", "1")))
    service_api_key: str = field(default_factory=lambda: _f("SERVICE_API_KEY", ""))
    ticketing_webhook_url: str = field(default_factory=lambda: _f("TICKETING_WEBHOOK_URL", ""))
