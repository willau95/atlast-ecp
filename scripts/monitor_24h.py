#!/usr/bin/env python3
"""
C6 — 24h Production Stability Monitor for ATLAST ECP Server

Checks every 5 minutes for 24 hours:
1. /health — server alive
2. /v1/stats — API stats responding
3. /v1/discovery/agents — discovery endpoint
4. /.well-known/atlast-ecp.json — well-known file
5. Response time < 2s
6. No 5xx errors

Results written to monitor_24h_report.json
"""

import asyncio
import json
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
import aiohttp
import functools

# Force unbuffered prints
print = functools.partial(print, flush=True)

API_BASE = "https://api.weba0.com"
CHECK_INTERVAL = 300  # 5 minutes
TOTAL_DURATION = 86400  # 24 hours
TIMEOUT = 10  # seconds per request
MAX_RESPONSE_TIME = 2.0  # seconds

ENDPOINTS = [
    ("GET", "/health", 200),
    ("GET", "/v1/stats", 200),
    ("GET", "/v1/discovery/agents", 200),
    ("GET", "/.well-known/ecp.json", 200),
]

report_path = Path(__file__).parent.parent / "docs" / "C6-24H-MONITOR-REPORT.json"


async def check_endpoint(session: aiohttp.ClientSession, method: str, path: str, expected_status: int) -> dict:
    url = f"{API_BASE}{path}"
    start = time.monotonic()
    try:
        async with session.request(method, url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
            elapsed = time.monotonic() - start
            body = await resp.text()
            return {
                "endpoint": path,
                "status": resp.status,
                "expected_status": expected_status,
                "response_time_s": round(elapsed, 3),
                "ok": resp.status == expected_status and elapsed < MAX_RESPONSE_TIME,
                "error": None if resp.status == expected_status else f"got {resp.status}",
                "slow": elapsed >= MAX_RESPONSE_TIME,
            }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "endpoint": path,
            "status": None,
            "expected_status": expected_status,
            "response_time_s": round(elapsed, 3),
            "ok": False,
            "error": str(e),
            "slow": False,
        }


async def run_check(session: aiohttp.ClientSession) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    results = await asyncio.gather(
        *[check_endpoint(session, m, p, s) for m, p, s in ENDPOINTS]
    )
    all_ok = all(r["ok"] for r in results)
    return {
        "timestamp": ts,
        "all_ok": all_ok,
        "checks": results,
    }


async def main():
    print(f"🟢 C6 24h Monitor started at {datetime.now(timezone.utc).isoformat()}")
    print(f"   Target: {API_BASE}")
    print(f"   Interval: {CHECK_INTERVAL}s ({CHECK_INTERVAL//60} min)")
    print(f"   Duration: {TOTAL_DURATION}s ({TOTAL_DURATION//3600}h)")
    print(f"   Report: {report_path}")
    print()

    report = {
        "monitor": "C6-24h-stability",
        "target": API_BASE,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "interval_s": CHECK_INTERVAL,
        "total_checks": 0,
        "total_pass": 0,
        "total_fail": 0,
        "uptime_pct": 0.0,
        "avg_response_time_s": 0.0,
        "max_response_time_s": 0.0,
        "failures": [],
        "checks": [],
    }

    start_time = time.monotonic()
    all_response_times = []

    async with aiohttp.ClientSession() as session:
        while (time.monotonic() - start_time) < TOTAL_DURATION:
            check = await run_check(session)
            report["total_checks"] += 1

            for r in check["checks"]:
                all_response_times.append(r["response_time_s"])

            if check["all_ok"]:
                report["total_pass"] += 1
                status_icon = "✅"
            else:
                report["total_fail"] += 1
                report["failures"].append(check)
                status_icon = "❌"

            # Keep last 50 checks in report for size management
            report["checks"].append(check)
            if len(report["checks"]) > 50:
                report["checks"] = report["checks"][-50:]

            report["uptime_pct"] = round(
                report["total_pass"] / report["total_checks"] * 100, 2
            )
            if all_response_times:
                report["avg_response_time_s"] = round(
                    sum(all_response_times) / len(all_response_times), 3
                )
                report["max_response_time_s"] = round(max(all_response_times), 3)

            report["last_check"] = check["timestamp"]
            elapsed_h = (time.monotonic() - start_time) / 3600
            remaining_h = (TOTAL_DURATION - (time.monotonic() - start_time)) / 3600

            print(
                f"{status_icon} [{check['timestamp'][:19]}] "
                f"Check #{report['total_checks']} | "
                f"Uptime: {report['uptime_pct']}% | "
                f"Avg: {report['avg_response_time_s']}s | "
                f"Elapsed: {elapsed_h:.1f}h | "
                f"Remaining: {remaining_h:.1f}h"
            )

            # Write report after each check
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2))

            # Wait for next check
            await asyncio.sleep(CHECK_INTERVAL)

    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "PASS" if report["uptime_pct"] >= 99.0 else "FAIL"
    report_path.write_text(json.dumps(report, indent=2))

    print()
    print(f"{'='*60}")
    print(f"C6 24h Monitor COMPLETE")
    print(f"  Status: {report['status']}")
    print(f"  Uptime: {report['uptime_pct']}%")
    print(f"  Total checks: {report['total_checks']}")
    print(f"  Failures: {report['total_fail']}")
    print(f"  Avg response: {report['avg_response_time_s']}s")
    print(f"  Max response: {report['max_response_time_s']}s")
    print(f"  Report: {report_path}")
    print(f"{'='*60}")

    sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    asyncio.run(main())
