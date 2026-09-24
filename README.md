# Smart Indoor Weather Station

An IoT system that collects indoor environmental data (temperature, humidity, air quality) using an M5Stack CORE2 device, streams it to Google BigQuery via a Flask middleware, and visualises it on a live Streamlit dashboard — with AI-powered voice recommendations triggered by motion detection. (The IoT device system has been disconnected)

**Demo video:** [YouTube — ***]

**Live dashboard:** https://weather-dashboard-297113273467.europe-west6.run.app




---

## Group Members & Contributions

Both members jointly designed the overall system architecture, defined the API contract between the device and middleware, and iteratively improved features and bug fixes together throughout the project. Edited and produced the demo video.

| Name | Main responsibility | Details |
|------|-------------------|---------|
| **Florent Schneeberger** | M5Stack device firmware | Wrote the CORE2 firmware (`device/main.py`) including sensor integration (ENV3, SGP30, PIR), dashboard UI on the device screen, WiFi scan with retry and manual fallback, RTC/NTP sync, forecast icon rendering, and AI voice pipeline triggered by motion detection. |
| **Lu Zhou** | Streamlit dashboard & deployment | Built the live dashboard (`dashboard/`) including metric cards, Plotly charts, outdoor weather panel, history & analytics page, and timezone handling. Set up Flask middleware (`middleware/`) REST API, BigQuery integration, and Cloud Run deployment for both services. |

---

## System Architecture

```
M5Stack CORE2 (MicroPython)
        │  POST /send-to-bigquery  (sensor data)
        │  GET  /weather/mini      (outdoor weather)
        │  POST /voice/ask         (AI voice reply)
        ▼
Flask Middleware  ──► Google BigQuery (data store)
(Cloud Run)       ──► OpenWeatherMap  (outdoor weather)
        │         ──► OpenRouter LLM  (AI answers + TTS)
        ▼
Streamlit Dashboard
(Cloud Run)
```

---

## Repository Structure

```
.
├── device/               # M5Stack CORE2 firmware (MicroPython / UIFlow)
│   ├── main.py           #   Full weather station program — sensors, WiFi, dashboard UI, AI voice
│   └── AI_Function_DEBUG.py  # Standalone debug script for the AI/voice pipeline
│
├── middleware/           # Flask REST API — runs on Google Cloud Run
│   ├── app.py            #   All HTTP endpoints (/send-to-bigquery, /weather/*, /voice/*, /ai/*)
│   ├── bigquery_client.py#   BigQuery read/write helpers
│   ├── weather_client.py #   OpenWeatherMap integration
│   ├── voice_client.py   #   LLM (text), TTS (audio), STT (transcription) via OpenRouter
│   ├── config.py         #   Configuration — reads from environment variables (see Security below)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── deploy.sh         #   One-command Cloud Run deploy
│
├── dashboard/            # Streamlit web dashboard — runs on Google Cloud Run
│   ├── app.py            #   Live dashboard + History & Analytics pages
│   ├── api_client.py     #   HTTP client for the middleware
│   ├── static/           #   Background photo (lausanne.jpg)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── deploy.sh         #   One-command Cloud Run deploy
│
├── UIdesign/             # Figma / mockup screenshots of the dashboard design
│
├── images/               # Hardware photos used as dashboard background
│
└── README.md
```

---

## Security — Credentials & Secrets

**Never commit API keys or passwords to Git.**

All secrets are passed as environment variables at deploy time. The middleware will **refuse to start** with a clear error if a required variable is missing. See `middleware/.env.example` for the full list.

| Variable | Used by | Required | Description |
|----------|---------|----------|-------------|
| `OWM_API_KEY` | middleware | **yes** | OpenWeatherMap API key |
| `OPENROUTER_API_KEY` | middleware | **yes** | OpenRouter key (LLM + TTS + STT) |
| `DEVICE_PASSWD` | middleware + device | no | Shared password for device auth (SHA-256 hashed); defaults to `DEVICE_PASSWD` |
| `GCP_PROJECT` | middleware | no | Google Cloud project ID |
| `BQ_DATASET` | middleware | no | BigQuery dataset name |
| `BQ_TABLE` | middleware | no | BigQuery table name |

**For the M5Stack device** — WiFi passwords and `PASSWD` in `device/main.py` must be set locally. Replace secret values with placeholders before committing:

```python
# device/main.py
PASSWD = "CHANGE_ME"
WIFI_LIST = [("YourSSID", "YourPassword")]
```

---

## Deployment

### Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and authenticated:
  ```bash
  gcloud auth login
  gcloud config set project <YOUR_GCP_PROJECT_ID>
  ```
- Docker (used by Cloud Build)

### 1 — Deploy the middleware (Flask API)

```bash
export OWM_API_KEY="your_openweathermap_key"
export OPENROUTER_API_KEY="your_openrouter_key"
export DEVICE_PASSWD="your_device_password"

cd middleware
bash deploy.sh
```

The script builds the Docker image via Cloud Build, then deploys to Cloud Run in `europe-west6`. The service URL is printed on completion.

### 2 — Deploy the dashboard (Streamlit)

```bash
cd dashboard
bash deploy.sh
```

If you want the dashboard to point to a different middleware URL:

```bash
export API_BASE_URL="https://your-middleware-url.run.app"
bash deploy.sh
```

### 3 — Flash the device

1. Open `device/main.py` in [UIFlow](https://flow.m5stack.com/) or any MicroPython IDE.
2. Fill in your WiFi credentials and `PASSWD` locally.
3. Set `CLOUD_BASE` to your own middleware Cloud Run URL (replace the existing URL in `device/main.py` and `device/AI_Function_DEBUG.py`).
4. Upload to the M5Stack CORE2.

The device connects to the strongest known WiFi, syncs the RTC via NTP, then begins sending sensor readings every ~7 minutes and triggers AI voice on motion detection.

---

## Features

- **Indoor sensors**: temperature, humidity, pressure (ENV3 unit), TVOC & eCO₂ (SGP30)
- **Motion detection**: PIR sensor triggers an immediate reading and an AI voice announcement
- **Outdoor weather**: current conditions + 5-day forecast from OpenWeatherMap, with live weather icons
- **AI voice**: LLM-generated health/activity recommendation read aloud via TTS, using the current OWM weather icon code as additional outdoor context
- **Live dashboard**: real-time metric cards, alerts, outdoor atmospheric panel, 5-day forecast cards
- **History & Analytics**: temperature min/max/avg, humidity and air quality trends, atmospheric pressure chart, sensor event log
- **Auto WiFi**: scans for strongest known network; falls back to manual list on boot failure
- **Boot sync**: device restores last known readings from BigQuery on startup, even after a power cut


### AI use 

Designed, integrated, and tested by the project members. Some components were partially or fully generated, improved and debugged using AI tools.
