"""
OpenRouter client for voice features.
  - LLM  : google/gemini-2.5-flash-lite  (chat completions)
  - TTS  : openai/tts-1                  (text → MP3, then converted to WAV)
  - STT  : openai/whisper-1              (audio bytes → text transcription)
"""

import io
import base64
import logging
import requests
from pydub import AudioSegment

import config

logger = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://weather-iot-project",
        "X-Title": "Weather IoT Monitor",
    }


# ── LLM ───────────────────────────────────────────────────────────────────────

def ask_llm(messages: list[dict], system: str | None = None) -> str:
    """Send a chat to Gemini 2.5 Flash Lite and return the reply string."""
    payload = {
        "model": config.LLM_MODEL,
        "messages": (
            [{"role": "system", "content": system}] if system else []
        ) + messages,
    }
    resp = requests.post(
        f"{OPENROUTER_BASE}/chat/completions",
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── TTS ───────────────────────────────────────────────────────────────────────

def text_to_wav(text: str) -> bytes:
    """
    Convert text to a WAV bytes object the M5Stack speaker can play.
    Step 1: call OpenRouter TTS → get MP3 bytes.
    Step 2: convert MP3 → WAV (8 kHz, 16-bit, mono) with pydub.
    """
    payload = {
        "model": config.TTS_MODEL,
        "input": text,
        "voice": "alloy",          # ignored by some models but required by the API
        "response_format": "mp3",
    }
    resp = requests.post(
        f"{OPENROUTER_BASE}/audio/speech",
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if not resp.ok:
        logger.error("TTS failed HTTP %s: %s", resp.status_code, resp.text[:1000])
        resp.raise_for_status()

    mp3_bytes = resp.content

    # Convert to 8 kHz mono WAV (M5Stack speaker format)
    audio = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
    audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)

    buf = io.BytesIO()
    audio.export(buf, format="wav")
    return buf.getvalue()


def text_to_wav_b64(text: str) -> str:
    """Return text_to_wav result as a base64 string (for JSON transport to device)."""
    return base64.b64encode(text_to_wav(text)).decode()


# ── STT ───────────────────────────────────────────────────────────────────────

def transcribe(audio_bytes: bytes, filename: str = "recording.wav") -> str:
    """
    Transcribe raw audio bytes using Whisper via OpenRouter.
    The device sends raw 8 kHz 16-bit mono PCM; we wrap it in a WAV header first.
    """
    # If the bytes look like raw PCM (no RIFF header), wrap them
    if audio_bytes[:4] != b"RIFF":
        audio_bytes = _pcm_to_wav(audio_bytes)

    files = {
        "file": (filename, io.BytesIO(audio_bytes), "audio/wav"),
        "model": (None, config.STT_MODEL),
    }
    resp = requests.post(
        f"{OPENROUTER_BASE}/audio/transcriptions",
        headers=_auth_headers(),   # no Content-Type — let requests set multipart
        files=files,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("text", "").strip()


def _pcm_to_wav(pcm: bytes, rate: int = 8000, channels: int = 1, width: int = 2) -> bytes:
    """Wrap raw PCM bytes in a minimal WAV container."""
    audio = AudioSegment(data=pcm, sample_width=width, frame_rate=rate, channels=channels)
    buf = io.BytesIO()
    audio.export(buf, format="wav")
    return buf.getvalue()


# ── Smart announcement generator ──────────────────────────────────────────────

def build_announcement(indoor: dict | None, outdoor: dict | None,
                        forecast: list | None, alerts: list | None) -> str:
    """
    Ask the LLM to produce a short spoken announcement based on current data.
    Called by the M5Stack PIR trigger (at most once per hour).
    """
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    morning = 6 <= hour <= 9

    system = (
        "You are a friendly smart-home assistant making a brief verbal announcement. "
        "Speak naturally in 1–2 sentences. No bullet points, no markdown. "
        "If it is morning and rain is forecast, remind the user to take an umbrella. "
        "If humidity is below 40%, mention it. "
        "If air quality is poor (TVOC > 250 ppb or eCO2 > 1200 ppm), warn the user. "
        "Otherwise give a pleasant summary of indoor and outdoor conditions."
    )

    context = (
        f"Time of day: {'morning' if morning else 'daytime/evening'}. "
        f"Indoor: {indoor}. "
        f"Outdoor: {outdoor}. "
        f"Today's forecast: {forecast[0] if forecast else 'unknown'}. "
        f"Active alerts: {alerts}."
    )

    return ask_llm([{"role": "user", "content": context}], system=system)


# ── Q&A answer builder ────────────────────────────────────────────────────────

def answer_question(question: str, indoor: dict | None,
                    stats_24h: dict, stats_48h: dict) -> str:
    """
    Answer a natural-language question about home conditions using BigQuery context.
    """
    system = (
        "You are a smart-home assistant with access to indoor sensor history. "
        "Answer the user's question in 1–2 spoken sentences. "
        "No markdown, no bullet points. "
        "If the data is insufficient to answer, say so politely."
    )
    context = (
        f"Question: {question}\n"
        f"Current reading: {indoor}\n"
        f"Last 24 h stats: {stats_24h}\n"
        f"Last 48 h stats: {stats_48h}"
    )
    return ask_llm([{"role": "user", "content": context}], system=system)
