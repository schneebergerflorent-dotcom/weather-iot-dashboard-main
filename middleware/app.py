"""
Flask middleware — Weather IoT project
Tiers: BigQuery (data) ← this file ← Streamlit dashboard + M5Stack device
"""

import base64
import json
import logging
from flask import Flask, request, jsonify, Response

import config
import bigquery_client as bq
import weather_client  as weather
import voice_client    as voice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth_error():
    return jsonify({"error": "Unauthorized"}), 401

def _bad(msg: str):
    return jsonify({"error": msg}), 400

def _ok(data):
    return jsonify(data), 200


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return _ok({"status": "ok", "project": config.GCP_PROJECT})


# ── Device → BigQuery (existing endpoint kept backward-compatible) ─────────────

@app.route("/send-to-bigquery", methods=["POST"])
def send_to_bigquery():
    body = request.get_json(force=True, silent=True)
    if not body:
        return _bad("Invalid or missing JSON body")

    if body.get("passwd") != config.DEVICE_HASH:
        logger.warning("Rejected request with bad passwd hash")
        return _auth_error()

    values = body.get("values")
    if not isinstance(values, dict) or not values:
        return _bad("Missing 'values' object")

    required = {"indoor_temp", "indoor_humidity", "indoor_pressure"}
    missing  = required - values.keys()
    if missing:
        return _bad(f"Missing required fields: {', '.join(missing)}")

    # Enrich with current outdoor weather before storing
    try:
        ow = weather.get_current()
        values["outdoor_temp"]     = int(round(ow["temp"]))
        values["outdoor_humidity"] = ow["humidity"]
        values["outdoor_weather"]  = ow["description"]
    except Exception as exc:
        logger.warning("Could not fetch outdoor weather for insert: %s", exc)

    ok = bq.insert_reading(values)
    if ok:
        logger.info("Inserted reading from source=%s", values.get("source"))
        return _ok({"status": "ok"})
    return jsonify({"error": "BigQuery insert failed"}), 500


# ── Indoor data ───────────────────────────────────────────────────────────────

@app.route("/indoor/latest", methods=["GET"])
def indoor_latest():
    """Most recent sensor reading. Used by M5Stack on boot to sync last values."""
    row = bq.get_latest()
    if row is None:
        return jsonify({"error": "No data in table"}), 404
    return _ok(row)


@app.route("/indoor/history", methods=["GET"])
def indoor_history():
    """
    Historical readings.
    Query params:
        hours  – lookback window (default 24, max 720)
        limit  – max rows returned (default 500, max 2000)
    """
    try:
        hours = int(request.args.get("hours", 24))
        limit = int(request.args.get("limit", 500))
    except ValueError:
        return _bad("hours and limit must be integers")

    rows = bq.get_history(hours=hours, limit=limit)
    return _ok({"count": len(rows), "data": rows})


@app.route("/indoor/stats", methods=["GET"])
def indoor_stats():
    """
    Aggregate stats for a time window.
    Query params:
        hours – lookback window (default 24, max 720)
    """
    try:
        hours = int(request.args.get("hours", 24))
    except ValueError:
        return _bad("hours must be an integer")

    stats = bq.get_stats(hours=hours)
    return _ok({"hours": hours, "stats": stats})


@app.route("/indoor/alerts", methods=["GET"])
def indoor_alerts():
    """Active alerts based on the latest reading (humidity < 40%, bad air, high CO₂)."""
    alerts = bq.get_alerts()
    return _ok({"count": len(alerts), "alerts": alerts})


# ── Outdoor weather ───────────────────────────────────────────────────────────

@app.route("/weather/current", methods=["GET"])
def weather_current():
    """
    Current outdoor weather from OpenWeatherMap.
    Query params:
        city, country  – override the default location
    """
    city    = request.args.get("city")
    country = request.args.get("country")
    try:
        data = weather.get_current(city, country)
        return _ok(data)
    except Exception as exc:
        logger.error("OWM current error: %s", exc)
        return jsonify({"error": str(exc)}), 502


def _owm_symbol(desc: str) -> str:
    d = (desc or "").lower()
    if "thunder"              in d: return "STRM"
    if "drizzle"              in d: return "DRZL"
    if "rain"                 in d: return "RAIN"
    if "snow"                 in d: return "SNOW"
    if "fog" in d or "mist"   in d: return "FOG"
    if "clear"                in d: return "SUN"
    if "cloud" in d or "overcast" in d: return "CLDY"
    return "----"


@app.route("/weather/mini", methods=["GET"])
def weather_mini():
    """
    Minimal current weather for M5Stack UIFlow devices.
    Returns only temp + description with explicit Content-Length so
    UIFlow's urequests (which can't handle chunked encoding) works correctly.
    """
    try:
        data = weather.get_current()
        body = json.dumps({
            "t":    data["temp"],
            "d":    data["description"],
            "icon": data.get("icon", ""),
        }).encode()
        return Response(body, mimetype="application/json",
                        headers={"Content-Length": str(len(body))})
    except Exception as exc:
        logger.error("OWM mini error: %s", exc)
        return jsonify({"error": str(exc)}), 502


@app.route("/forecast/mini", methods=["GET"])
def forecast_mini():
    """
    Minimal 3-day forecast for M5Stack UIFlow devices.
    Returns pre-computed day name, max temp, and weather symbol.
    Explicit Content-Length prevents chunked-encoding issues on UIFlow.
    """
    import calendar
    try:
        days_data = weather.get_forecast(days=3)
        result = []
        for d in days_data[:3]:
            parts = d["date"].split("-")
            dow = calendar.day_abbr[
                calendar.weekday(int(parts[0]), int(parts[1]), int(parts[2]))
            ][:3]
            result.append({
                "n": dow,
                "t": int(round(d["temp_max"])),
                "s": _owm_symbol(d["description"]),
                "icon": d.get("icon", ""),
            })
        body = json.dumps(result).encode()
        return Response(body, mimetype="application/json",
                        headers={"Content-Length": str(len(body))})
    except Exception as exc:
        logger.error("Forecast mini error: %s", exc)
        return jsonify({"error": str(exc)}), 502


@app.route("/weather/forecast", methods=["GET"])
def weather_forecast():
    """
    Daily forecast (up to 7 days).
    Query params:
        city, country, days
    """
    city    = request.args.get("city")
    country = request.args.get("country")
    try:
        days = int(request.args.get("days", 5))
    except ValueError:
        return _bad("days must be an integer")

    try:
        data = weather.get_forecast(city, country, days)
        return _ok(data)
    except Exception as exc:
        logger.error("OWM forecast error: %s", exc)
        return jsonify({"error": str(exc)}), 502


@app.route("/weather/rain-today", methods=["GET"])
def weather_rain_today():
    """Simple boolean: will it rain today? Used by the device for umbrella reminder."""
    city    = request.args.get("city")
    country = request.args.get("country")
    try:
        raining = weather.will_rain_today(city, country)
        return _ok({"rain_today": raining})
    except Exception as exc:
        logger.error("OWM rain-today error: %s", exc)
        return jsonify({"error": str(exc)}), 502


# ── Combined snapshot (one call for the dashboard's landing page) ─────────────

@app.route("/snapshot", methods=["GET"])
def snapshot():
    """
    Return current indoor reading + active alerts + current outdoor weather
    in a single response so the dashboard / device can boot quickly.
    """
    city    = request.args.get("city")
    country = request.args.get("country", "CH")
    indoor  = bq.get_latest()
    alerts  = bq.get_alerts()
    outdoor = None
    try:
        outdoor = weather.get_current(city, country)
    except Exception as exc:
        logger.warning("Could not fetch outdoor weather: %s", exc)

    return _ok({
        "indoor":  indoor,
        "alerts":  alerts,
        "outdoor": outdoor,
    })


# ── Voice: Text-to-Speech ─────────────────────────────────────────────────────

@app.route("/voice/speak", methods=["POST"])
def voice_speak():
    """
    Convert text to WAV audio and return it base64-encoded.
    Body: {"text": "Hello world"}
    Response: {"audio_b64": "<base64 WAV>", "text": "Hello world"}
    """
    body = request.get_json(force=True, silent=True)
    if not body or not body.get("text"):
        return _bad("Missing 'text' field")
    try:
        audio_b64 = voice.text_to_wav_b64(body["text"])
        return _ok({"audio_b64": audio_b64, "text": body["text"]})
    except Exception as exc:
        logger.error("TTS error: %s", exc)
        return jsonify({"error": str(exc)}), 502


# ── Voice: Speech-to-Text ─────────────────────────────────────────────────────

@app.route("/voice/transcribe", methods=["POST"])
def voice_transcribe():
    """
    Transcribe audio to text.
    Accepts either:
      - multipart/form-data with an 'audio' file field, OR
      - application/json with {"audio_b64": "<base64 raw PCM or WAV>"}
    Response: {"text": "transcribed words"}
    """
    try:
        if request.content_type and "multipart" in request.content_type:
            if "audio" not in request.files:
                return _bad("Missing 'audio' file field")
            f = request.files["audio"]
            audio_bytes = f.read()
            filename = f.filename or "recording.wav"
        else:
            body = request.get_json(force=True, silent=True) or {}
            if "audio_b64" not in body:
                return _bad("Missing 'audio_b64' in JSON or 'audio' file")
            audio_bytes = base64.b64decode(body["audio_b64"])
            filename = body.get("filename", "recording.wav")

        text = voice.transcribe(audio_bytes, filename)
        return _ok({"text": text})
    except Exception as exc:
        logger.error("STT error: %s", exc)
        return jsonify({"error": str(exc)}), 502


# ── Voice: Q&A (text question → LLM answer → optional audio) ─────────────────

@app.route("/voice/ask", methods=["POST"])
def voice_ask():
    """
    Answer a text question about home conditions using BigQuery context.

    Body:
      {"question": "..."}                 -> returns answer + audio_b64
      {"question": "...", "audio": false} -> returns answer only

    Response with audio:
      {"answer": "...", "audio_b64": "<base64 WAV>"}

    Response text-only:
      {"answer": "..."}
    """
    body = request.get_json(force=True, silent=True)
    if not body or not body.get("question"):
        return _bad("Missing 'question' field")
    try:
        indoor    = bq.get_latest()
        stats_24h = bq.get_stats(hours=24)
        stats_48h = bq.get_stats(hours=48)

        answer = voice.answer_question(
            body["question"],
            indoor,
            stats_24h,
            stats_48h
        )

        if body.get("audio") is False:
            return _ok({"answer": answer})

        audio_b64 = voice.text_to_wav_b64(answer)
        return _ok({"answer": answer, "audio_b64": audio_b64})
    except Exception as exc:
        logger.error("Voice ask error: %s", exc)
        return jsonify({"error": str(exc)}), 502


# ── AI: Text-only Q&A ────────────────────────────────────────────────────────

@app.route("/ai/ask-text", methods=["POST"])
def ai_ask_text():
    """
    Text-only AI endpoint. Does not generate audio.
    Body: {"question": "How is the indoor air quality?"}
    Response: {"answer": "..."}
    """
    body = request.get_json(force=True, silent=True)
    if not body or not body.get("question"):
        return _bad("Missing 'question' field")
    try:
        indoor    = bq.get_latest()
        stats_24h = bq.get_stats(hours=24)
        stats_48h = bq.get_stats(hours=48)

        answer = voice.answer_question(
            body["question"],
            indoor,
            stats_24h,
            stats_48h
        )
        return _ok({"answer": answer})
    except Exception as exc:
        logger.error("AI ask-text error: %s", exc)
        return jsonify({"error": str(exc)}), 502


# ── Voice: Full pipeline (device mic → STT → LLM → TTS → device speaker) ─────

@app.route("/voice/query-audio", methods=["POST"])
def voice_query_audio():
    """
    All-in-one voice pipeline for the M5Stack Button A press.
    Accepts raw PCM audio bytes (8 kHz, 16-bit, mono) as the request body.
    Returns: {"question": "...", "answer": "...", "audio_b64": "<base64 WAV>"}
    """
    audio_bytes = request.get_data()
    if not audio_bytes:
        return _bad("Empty audio body")
    try:
        question  = voice.transcribe(audio_bytes, "query.wav")
        logger.info("Voice query transcribed: %s", question)

        if not question:
            return _ok({"question": "", "answer": "Sorry, I didn't catch that.",
                        "audio_b64": voice.text_to_wav_b64("Sorry, I didn't catch that.")})

        indoor    = bq.get_latest()
        stats_24h = bq.get_stats(hours=24)
        stats_48h = bq.get_stats(hours=48)

        answer    = voice.answer_question(question, indoor, stats_24h, stats_48h)
        audio_b64 = voice.text_to_wav_b64(answer)
        return _ok({"question": question, "answer": answer, "audio_b64": audio_b64})
    except Exception as exc:
        logger.error("Voice query-audio error: %s", exc)
        return jsonify({"error": str(exc)}), 502


# ── Voice: PIR announcement ───────────────────────────────────────────────────

@app.route("/voice/announce", methods=["GET"])
def voice_announce():
    """
    Generate a spoken announcement based on current conditions.
    Called by the M5Stack when PIR detects motion (throttled to once per hour).
    Response: {"text": "...", "audio_b64": "<base64 WAV>"}
    """
    try:
        indoor  = bq.get_latest()
        alerts  = bq.get_alerts()
        outdoor, forecast = None, []
        try:
            outdoor  = weather.get_current()
            forecast = weather.get_forecast(days=1)
        except Exception as exc:
            logger.warning("Weather unavailable for announcement: %s", exc)

        text      = voice.build_announcement(indoor, outdoor, forecast, alerts)
        audio_b64 = voice.text_to_wav_b64(text)
        return _ok({"text": text, "audio_b64": audio_b64})
    except Exception as exc:
        logger.error("Announce error: %s", exc)
        return jsonify({"error": str(exc)}), 502


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bq.ensure_table_exists()
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
