"""ATLAST ECP — Claude Code Stop hook (v4, transcript-scanner-driven).

This hook is a thin trigger. The actual recording logic lives in
atlast_ecp.transcript_scanner, which parses transcript JSONL files and
writes byte-for-byte complete records with deterministic ids. That module
is the single source of truth — the hook only passes in which transcript
to scan.

Why: Claude Code's Stop event doesn't always fire at the true end of a
turn (agent chains can add entries after the last Stop). Scanner-driven
recording catches everything on each invocation and stays correct even
when hooks are unreliable. `atlast sync` achieves the same result without
any hook firing at all.

Self-upgrade: after the installed atlast-ecp package version changes, the
running hook script on disk is stale. Before doing any work, the hook
compares the installed package version to the version baked into this
file; if the package is newer, it rewrites itself from the packaged
template and re-execs. This makes `pip install --upgrade` sufficient —
users never need to re-run `atlast init` to get hook fixes.
"""
import json
import os
import sys
import time
from pathlib import Path

_DEV_SRC = "/Users/seacapital/Desktop/atlast-ecp/sdk/python"
if os.path.isdir(_DEV_SRC) and _DEV_SRC not in sys.path:
    sys.path.insert(0, _DEV_SRC)

LOG_FILE = Path.home() / ".ecp" / "hook_debug.log"

# Version of atlast-ecp whose template produced this hook script.
# Rewritten by atlast init / self-upgrade.
HOOK_BAKED_SDK_VERSION = "0.0.0"


def _self_upgrade_if_stale() -> None:
    """If the installed atlast_ecp package is newer than this script's
    baked version, rewrite this file from the packaged template and
    re-exec so the caller picks up the new code immediately.

    Safe to fail silently — a stale hook still runs (just with older
    logic) until the next opportunity to refresh.
    """
    try:
        from atlast_ecp import __version__ as pkg_ver
    except Exception:
        return
    if pkg_ver == HOOK_BAKED_SDK_VERSION:
        return
    try:
        # Locate the packaged template inside the installed atlast_ecp
        # and read its current contents.
        try:
            from importlib import resources as _res
            template_src = (
                _res.files("atlast_ecp")
                .joinpath("_claude_stop_hook_template.py")
                .read_text(encoding="utf-8")
            )
        except Exception:
            import atlast_ecp as _ae
            tpath = Path(_ae.__file__).parent / "_claude_stop_hook_template.py"
            template_src = tpath.read_text(encoding="utf-8")

        # Stamp the template with the installed version so next fire
        # finds no mismatch.
        stamped = template_src.replace(
            'HOOK_BAKED_SDK_VERSION = "0.0.0"',
            f'HOOK_BAKED_SDK_VERSION = "{pkg_ver}"',
            1,
        )

        script_path = Path(__file__).resolve()
        # Write atomically so a half-written hook never executes.
        tmp_path = script_path.with_suffix(".py.tmp")
        tmp_path.write_text(stamped, encoding="utf-8")
        os.replace(tmp_path, script_path)

        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a") as _f:
                _f.write(
                    f"[{time.strftime('%H:%M:%S')}] Self-upgraded hook "
                    f"({HOOK_BAKED_SDK_VERSION} → {pkg_ver})\n"
                )
        except Exception:
            pass

        # Re-exec so the current process runs the new code.
        os.execv(sys.executable, [sys.executable, str(script_path)])
    except Exception:
        # Never block recording on a self-upgrade hiccup.
        return


_self_upgrade_if_stale()


def _log(msg):
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _find_transcript(data):
    tp = data.get("transcript_path")
    if tp and Path(tp).exists():
        return Path(tp)
    sid = data.get("session_id")
    if sid:
        claude_dir = Path.home() / ".claude" / "projects"
        if claude_dir.exists():
            for f in claude_dir.rglob(f"{sid}.jsonl"):
                if f.exists() and f.stat().st_size > 50:
                    return f
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None
    candidates = []
    for f in claude_dir.rglob("*.jsonl"):
        if "/subagents/" in str(f) or f.name == "history.jsonl":
            continue
        try:
            if f.stat().st_size > 50:
                candidates.append(f)
        except Exception:
            pass
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return candidates[0]


def main():
    _log("Stop hook v4 fired (scanner-driven)")
    try:
        data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        data = {}

    tpath = _find_transcript(data)
    if not tpath:
        _log("ERROR: no transcript found")
        return
    _log(f"Scanning: {tpath}")

    try:
        from atlast_ecp.transcript_scanner import scan_and_record
    except Exception as e:
        _log(f"ERROR importing scanner: {e}")
        return

    try:
        summary = scan_and_record(tpath, log=_log)
        _log(
            f"SUMMARY turns={summary['turns_scanned']} "
            f"recorded={summary['turns_recorded']} "
            f"skipped_final={summary['turns_skipped_finalized']} "
            f"subagents={summary['subagents_recorded']}"
        )
    except Exception as e:
        _log(f"ERROR scan_and_record: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log(f"FATAL: {e}")
