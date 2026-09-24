import os
import hashlib
import binascii
import logging

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    """Return env var value or raise a clear error if it is not set."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set. "
            "See middleware/.env.example for the full list of required variables."
        )
    return value


# ── Google Cloud ──────────────────────────────────────────────────────────────
GCP_PROJECT = os.getenv("GCP_PROJECT", "finial-project-494209")
BQ_DATASET  = os.getenv("BQ_DATASET",  "Lab4_IoT_datasets")
BQ_TABLE    = os.getenv("BQ_TABLE",    "weather-records")

# Full dotted reference used in insert; backtick-quoted version used in SQL
BQ_TABLE_REF = f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
BQ_TABLE_SQL  = f"`{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}`"

# ── Device auth ───────────────────────────────────────────────────────────────
DEVICE_PASSWD = os.getenv("DEVICE_PASSWD", "Cloud1802")
DEVICE_HASH   = binascii.hexlify(
    hashlib.sha256(DEVICE_PASSWD.encode()).digest()
).decode()

# ── OpenWeatherMap ────────────────────────────────────────────────────────────
OWM_API_KEY = _require_env("OWM_API_KEY")
OWM_CITY    = os.getenv("OWM_CITY",    "Lausanne")
OWM_COUNTRY = os.getenv("OWM_COUNTRY", "CH")

# ── OpenRouter (voice features) ───────────────────────────────────────────────
OPENROUTER_API_KEY = _require_env("OPENROUTER_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "google/gemini-2.5-flash-lite")
TTS_MODEL = os.getenv("TTS_MODEL", "openai/gpt-4o-mini-tts-2025-12-15")
STT_MODEL = os.getenv("STT_MODEL", "openai/whisper-1")

# ── Server ────────────────────────────────────────────────────────────────────
PORT = int(os.getenv("PORT", 8080))
