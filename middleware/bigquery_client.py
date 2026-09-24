from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from datetime import datetime, timezone
import logging
import config

logger = logging.getLogger(__name__)

_client: bigquery.Client | None = None


def get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.GCP_PROJECT)
    return _client


# Schema matches the EXISTING table exactly
_SCHEMA = [
    bigquery.SchemaField("date",             "DATE",    mode="NULLABLE"),
    bigquery.SchemaField("time",             "TIME",    mode="NULLABLE"),
    bigquery.SchemaField("indoor_temp",      "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("indoor_humidity",  "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("outdoor_temp",     "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("outdoor_humidity", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("outdoor_weather",  "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("indoor_pressure",  "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("source",           "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("motion_detected",  "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("indoor_tvoc_ppb",  "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("indoor_eco2_ppm",  "INTEGER", mode="NULLABLE"),
]


def ensure_table_exists() -> None:
    client = get_client()
    table_ref = bigquery.TableReference.from_string(config.BQ_TABLE_REF)
    try:
        client.get_table(table_ref)
    except NotFound:
        table = bigquery.Table(table_ref, schema=_SCHEMA)
        client.create_table(table)
        logger.info("Created BigQuery table %s", config.BQ_TABLE_REF)


# ── Write ─────────────────────────────────────────────────────────────────────

def insert_reading(values: dict) -> bool:
    """Insert one sensor reading. Outdoor fields are optional."""
    now = datetime.now(timezone.utc)
    row = {
        "date":             now.strftime("%Y-%m-%d"),
        "time":             now.strftime("%H:%M:%S"),
        "source":           values.get("source"),
        "indoor_temp":      values.get("indoor_temp"),
        "indoor_humidity":  values.get("indoor_humidity"),
        "indoor_pressure":  values.get("indoor_pressure"),
        "motion_detected":  values.get("motion_detected", 0),
        "indoor_tvoc_ppb":  values.get("indoor_tvoc_ppb"),
        "indoor_eco2_ppm":  values.get("indoor_eco2_ppm"),
        "outdoor_temp":     values.get("outdoor_temp"),
        "outdoor_humidity": values.get("outdoor_humidity"),
        "outdoor_weather":  values.get("outdoor_weather"),
    }
    errors = get_client().insert_rows_json(config.BQ_TABLE_REF, [row])
    if errors:
        logger.error("BigQuery insert errors: %s", errors)
    return len(errors) == 0


# ── Read helpers ──────────────────────────────────────────────────────────────

def _serialize_row(row) -> dict:
    """Convert a BQ row to a JSON-safe dict, adding a combined timestamp field."""
    r = dict(row)
    # Convert date/time objects → strings (they are not JSON serializable)
    d = r.get("date")
    t = r.get("time")
    d_str = d.isoformat() if hasattr(d, "isoformat") else str(d) if d else None
    t_str = t.isoformat() if hasattr(t, "isoformat") else str(t) if t else None
    if d_str:
        r["date"] = d_str
    if t_str:
        r["time"] = t_str
    if d_str and t_str:
        r["timestamp"] = f"{d_str}T{t_str}Z"
    elif d_str:
        r["timestamp"] = d_str
    return r

# BigQuery DATETIME filter for time-window queries
_WINDOW = "DATETIME(date, time) >= DATETIME_SUB(CURRENT_DATETIME('UTC'), INTERVAL {hours} HOUR)"
_ORDER  = "ORDER BY date DESC, time DESC"


def get_latest() -> dict | None:
    query = f"""
        SELECT *
        FROM {config.BQ_TABLE_SQL}
        {_ORDER}
        LIMIT 1
    """
    rows = list(get_client().query(query).result())
    return _serialize_row(rows[0]) if rows else None


def get_history(hours: int = 24, limit: int = 500) -> list[dict]:
    hours = max(1, min(int(hours), 720))

    if hours <= 48:
        # Short windows: return raw rows
        limit = max(1, min(int(limit), 2000))
        query = f"""
            SELECT *
            FROM {config.BQ_TABLE_SQL}
            WHERE {_WINDOW.format(hours=hours)}
            {_ORDER}
            LIMIT {limit}
        """
        return [_serialize_row(r) for r in get_client().query(query).result()]

    # Longer windows: aggregate to hourly buckets to avoid row-limit truncation
    query = f"""
        SELECT
            FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ',
                TIMESTAMP_TRUNC(TIMESTAMP(DATETIME(date, time)), HOUR)) AS timestamp,
            ROUND(AVG(indoor_temp),      1) AS indoor_temp,
            ROUND(AVG(indoor_humidity),  1) AS indoor_humidity,
            ROUND(AVG(indoor_tvoc_ppb),  0) AS indoor_tvoc_ppb,
            ROUND(AVG(indoor_eco2_ppm),  0) AS indoor_eco2_ppm,
            ROUND(AVG(indoor_pressure),  1) AS indoor_pressure
        FROM {config.BQ_TABLE_SQL}
        WHERE {_WINDOW.format(hours=hours)}
        GROUP BY timestamp
        ORDER BY timestamp DESC
    """
    return [dict(r) for r in get_client().query(query).result()]


def get_stats(hours: int = 24) -> dict:
    hours = max(1, min(int(hours), 720))
    query = f"""
        SELECT
            COUNT(*)                       AS row_count,
            ROUND(AVG(indoor_temp),    2)  AS avg_temp,
            ROUND(MIN(indoor_temp),    2)  AS min_temp,
            ROUND(MAX(indoor_temp),    2)  AS max_temp,
            ROUND(AVG(indoor_humidity),1)  AS avg_humidity,
            ROUND(MIN(indoor_humidity),1)  AS min_humidity,
            ROUND(MAX(indoor_humidity),1)  AS max_humidity,
            ROUND(AVG(indoor_tvoc_ppb),0)  AS avg_tvoc,
            ROUND(MAX(indoor_tvoc_ppb),0)  AS max_tvoc,
            ROUND(AVG(indoor_eco2_ppm),0)  AS avg_eco2,
            ROUND(MAX(indoor_eco2_ppm),0)  AS max_eco2
        FROM {config.BQ_TABLE_SQL}
        WHERE {_WINDOW.format(hours=hours)}
    """
    rows = list(get_client().query(query).result())
    return dict(rows[0]) if rows else {}


# ── Alerts ────────────────────────────────────────────────────────────────────

def get_alerts() -> list[dict]:
    latest = get_latest()
    if not latest:
        return []

    alerts = []

    hum = latest.get("indoor_humidity")
    if hum is not None and hum < 40:
        alerts.append({
            "type":     "LOW_HUMIDITY",
            "severity": "warning",
            "message":  f"Indoor humidity is low: {hum:.0f}%",
            "value":    hum,
        })

    tvoc = latest.get("indoor_tvoc_ppb")
    if tvoc is not None:
        if tvoc >= 1000:
            alerts.append({
                "type":     "BAD_AIR_QUALITY",
                "severity": "danger",
                "message":  f"TVOC very high: {tvoc} ppb — ventilate now!",
                "value":    tvoc,
            })
        elif tvoc >= 250:
            alerts.append({
                "type":     "MODERATE_AIR_QUALITY",
                "severity": "warning",
                "message":  f"TVOC elevated: {tvoc} ppb",
                "value":    tvoc,
            })

    eco2 = latest.get("indoor_eco2_ppm")
    if eco2 is not None and eco2 >= 1200:
        alerts.append({
            "type":     "HIGH_CO2",
            "severity": "danger",
            "message":  f"eCO₂ very high: {eco2} ppm — open a window!",
            "value":    eco2,
        })

    return alerts
