"""
ATLAST ECP — Real-time Incident Detection

Monitors incoming records for anomalies (error spikes, latency spikes).
When thresholds are breached, creates incidents and fires webhooks.

Design:
- Sliding window of last N records (ring buffer)
- Check after each record: error_rate > threshold → incident
- State machine: open → analyzed → resolved
- Fail-Open: never crashes the agent
- Thread-safe
"""

import json
import os
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Optional

_lock = threading.Lock()

# ── Configuration ──

# Thresholds (configurable via env vars)
WINDOW_SIZE = int(os.environ.get("ATLAST_INCIDENT_WINDOW", "50"))
ERROR_RATE_THRESHOLD = float(os.environ.get("ATLAST_INCIDENT_ERROR_THRESHOLD", "0.20"))
LATENCY_SPIKE_MULTIPLIER = float(os.environ.get("ATLAST_INCIDENT_LATENCY_MULTIPLIER", "3.0"))
COOLDOWN_SECONDS = int(os.environ.get("ATLAST_INCIDENT_COOLDOWN", "300"))  # 5 min between incidents

# ── State ──

_window: deque = deque(maxlen=WINDOW_SIZE)
_baseline_latency: float = 0.0  # rolling average
_active_incident: Optional[dict] = None
_last_incident_ts: float = 0.0
_incidents_file: Optional[Path] = None


def _get_incidents_file() -> Path:
    global _incidents_file
    if _incidents_file is None:
        from .storage import ECP_DIR
        _incidents_file = ECP_DIR / "incidents.json"
    return _incidents_file


def _load_incidents() -> list:
    f = _get_incidents_file()
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            return []
    return []


def _save_incidents(incidents: list):
    try:
        _get_incidents_file().write_text(json.dumps(incidents[-100:], indent=2))  # Keep last 100
    except Exception:
        pass


def _fire_incident_webhook(incident: dict):
    """Send incident webhook to configured URL. Fail-Open."""
    try:
        from .config import load_config
        cfg = load_config()
        url = os.environ.get("ATLAST_INCIDENT_WEBHOOK_URL") or cfg.get("incident_webhook_url", "")
        if not url:
            return

        payload = json.dumps({
            "event": "incident.%s" % incident["status"],
            "incident": incident,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Fail-Open


def _fire_discord_incident(incident: dict):
    """Also notify Discord #bug-reports if configured."""
    try:
        import os as _os
        webhook = _os.environ.get("ATLAST_DISCORD_WEBHOOK", "")
        if not webhook:
            return
        emoji = "🔴" if incident["status"] == "created" else "🟢" if incident["status"] == "resolved" else "🟡"
        msg = "%s **Incident %s**: %s\nAgent: %s | Error rate: %.0f%% | Records: %d" % (
            emoji, incident["status"].upper(), incident.get("reason", ""),
            incident.get("agent", "?"), incident.get("error_rate", 0) * 100,
            incident.get("window_size", 0),
        )
        payload = json.dumps({"content": msg[:1900]}).encode()
        req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


# ── Main API ──

def check_record(record: dict):
    """Called after every record creation. Checks for incidents. Fail-Open, never raises."""
    try:
        _check_record_impl(record)
    except Exception:
        pass  # Fail-Open — NEVER crash the agent


def _check_record_impl(record: dict):
    global _active_incident, _last_incident_ts, _baseline_latency

    with _lock:
        # Extract key fields
        meta = record.get("meta", {})
        has_error = bool(meta.get("flags") and any(
            f in (meta.get("flags") if isinstance(meta.get("flags"), list) else [])
            for f in ["error", "exception", "agent_error"]
        ))
        # Also check top-level error field
        if record.get("error"):
            has_error = True

        latency = meta.get("latency_ms", 0) or 0
        agent = record.get("agent", "unknown")

        # Add to window
        _window.append({
            "ts": time.time(),
            "error": has_error,
            "latency": latency,
            "agent": agent,
        })

        if len(_window) < 10:
            return  # Not enough data yet

        # Calculate metrics
        error_count = sum(1 for r in _window if r["error"])
        error_rate = error_count / len(_window)
        latencies = [r["latency"] for r in _window if r["latency"] > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # Update baseline (exponential moving average)
        if _baseline_latency == 0:
            _baseline_latency = avg_latency
        else:
            _baseline_latency = _baseline_latency * 0.95 + avg_latency * 0.05

        # ── Check for incident ──
        now = time.time()

        # Error rate spike
        if error_rate >= ERROR_RATE_THRESHOLD and _active_incident is None:
            if now - _last_incident_ts < COOLDOWN_SECONDS:
                return  # Cooldown

            incident = {
                "id": "inc_%d" % int(now * 1000),
                "status": "created",
                "type": "error_spike",
                "reason": "Error rate %.0f%% exceeds threshold %.0f%%" % (error_rate * 100, ERROR_RATE_THRESHOLD * 100),
                "error_rate": error_rate,
                "error_count": error_count,
                "window_size": len(_window),
                "agent": agent,
                "avg_latency_ms": int(avg_latency),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            _active_incident = incident
            _last_incident_ts = now

            # Persist + notify
            incidents = _load_incidents()
            incidents.append(incident)
            _save_incidents(incidents)
            _fire_incident_webhook(incident)
            _fire_discord_incident(incident)

        # Latency spike
        elif _baseline_latency > 0 and avg_latency > _baseline_latency * LATENCY_SPIKE_MULTIPLIER and _active_incident is None:
            if now - _last_incident_ts < COOLDOWN_SECONDS:
                return

            incident = {
                "id": "inc_%d" % int(now * 1000),
                "status": "created",
                "type": "latency_spike",
                "reason": "Avg latency %dms is %.1fx baseline %dms" % (avg_latency, avg_latency / _baseline_latency, _baseline_latency),
                "error_rate": error_rate,
                "avg_latency_ms": int(avg_latency),
                "baseline_latency_ms": int(_baseline_latency),
                "window_size": len(_window),
                "agent": agent,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            _active_incident = incident
            _last_incident_ts = now

            incidents = _load_incidents()
            incidents.append(incident)
            _save_incidents(incidents)
            _fire_incident_webhook(incident)
            _fire_discord_incident(incident)

        # ── Check for resolution ──
        elif _active_incident is not None:
            if _active_incident["type"] == "error_spike" and error_rate < ERROR_RATE_THRESHOLD * 0.5:
                # Error rate dropped to half the threshold — resolved
                _active_incident["status"] = "resolved"
                _active_incident["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                _active_incident["resolved_error_rate"] = error_rate

                incidents = _load_incidents()
                incidents.append({**_active_incident})
                _save_incidents(incidents)
                _fire_incident_webhook(_active_incident)
                _fire_discord_incident(_active_incident)
                _active_incident = None

            elif _active_incident["type"] == "latency_spike" and avg_latency < _baseline_latency * 1.5:
                _active_incident["status"] = "resolved"
                _active_incident["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                _active_incident["resolved_avg_latency_ms"] = int(avg_latency)

                incidents = _load_incidents()
                incidents.append({**_active_incident})
                _save_incidents(incidents)
                _fire_incident_webhook(_active_incident)
                _fire_discord_incident(_active_incident)
                _active_incident = None


def get_incidents(limit: int = 20, status: Optional[str] = None) -> list:
    """Get recent incidents. Optional filter by status."""
    incidents = _load_incidents()
    if status:
        incidents = [i for i in incidents if i.get("status") == status]
    return incidents[-limit:]


def get_active_incident() -> Optional[dict]:
    """Get the currently active incident, if any."""
    with _lock:
        return _active_incident
