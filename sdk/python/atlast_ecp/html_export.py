"""
Vault v4 — self-contained single-file HTML export of one ECP record.

Inspired by claude-trace's approach: a single .html file that bundles the
record + vault + wire evidence as a base64-encoded data island, plus a
zero-dependency JS viewer that renders it. No server needed; opens offline
in any browser; trivially shareable as one-file evidence.

Design constraints:
- One file, no external CDN (CSP-safe)
- No template injection vulnerabilities — record content is JSON.stringify'd
  via the browser, never interpolated into HTML
- Integrity claim baked in: sha256 of the data block printed in the file
  so the recipient can verify nobody mangled it in transit
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import wire as _wire
from .storage import load_record_by_id, load_vault, load_local_summary


def _gather_record_bundle(record_id: str) -> Dict[str, Any]:
    """Pull together everything we know about a record into a single dict."""
    rec = load_record_by_id(record_id)
    if not rec:
        raise ValueError(f"record {record_id!r} not found")
    vault = load_vault(record_id) or {}
    summary = load_local_summary(record_id) or ""
    wire_ids: List[str] = []
    if isinstance(vault, dict):
        wire_ids = list(vault.get("wire_ids") or [])

    wire_entries = []
    for wid in wire_ids:
        meta = _wire.load_wire(wid, include_body=True)
        if meta:
            wire_entries.append(meta)

    return {
        "schema": "atlast.export.html.v1",
        "exported_at_unix_ms": int(__import__("time").time() * 1000),
        "record": rec,
        "vault": vault,
        "local_summary": summary,
        "wire_entries": wire_entries,
        "wire_count": len(wire_entries),
    }


# ── HTML template ──────────────────────────────────────────────────────
# The viewer is tiny (~10KB minified). It renders sections progressively.
# Two replacement points:
#   __ATLAST_DATA_B64__  — base64(json(bundle))
#   __ATLAST_DATA_SHA__  — sha256 of the base64 string, for tamper-detect
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ATLAST Evidence — __RECORD_ID__</title>
<style>
  :root {
    --bg: #0f1115; --fg: #e7e9ee; --muted: #8c92a4; --accent: #4ea2ff;
    --ok: #4ade80; --warn: #fbbf24; --bad: #f87171;
    --panel: #181b22; --border: #262b35; --code-bg: #11131a;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg);
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
                font-size: 14px; line-height: 1.5; }
  body { padding: 24px; max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 18px; margin: 0 0 4px 0; }
  h2 { font-size: 15px; margin: 24px 0 8px 0; color: var(--accent);
       border-bottom: 1px solid var(--border); padding-bottom: 6px; }
  h3 { font-size: 13px; margin: 12px 0 6px 0; color: var(--muted); font-weight: 600;
       text-transform: uppercase; letter-spacing: 0.04em; }
  .muted { color: var(--muted); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px;
           font-weight: 600; background: var(--panel); border: 1px solid var(--border); }
  .ok    { color: var(--ok); }
  .warn  { color: var(--warn); }
  .bad   { color: var(--bad); }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
           padding: 12px 16px; margin: 12px 0; }
  .kv { display: grid; grid-template-columns: 180px 1fr; gap: 4px 12px; font-size: 13px; }
  .kv > .k { color: var(--muted); }
  pre { background: var(--code-bg); border: 1px solid var(--border); border-radius: 6px;
        padding: 12px; overflow-x: auto; font-size: 12px; line-height: 1.45;
        white-space: pre-wrap; word-break: break-all; max-height: 480px; overflow-y: auto; }
  details { margin: 6px 0; }
  details > summary { cursor: pointer; padding: 4px 0; user-select: none; }
  .header { display: flex; justify-content: space-between; align-items: baseline;
            border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 4px; }
  .integrity { font-size: 12px; color: var(--muted); margin-top: 8px; }
  .sha { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px;
         color: var(--muted); word-break: break-all; }
  .pill { font-size: 11px; padding: 1px 6px; border-radius: 4px; margin-right: 6px;
          background: rgba(78, 162, 255, 0.15); color: var(--accent); }
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>ATLAST Evidence Export</h1>
    <div class="muted" id="subhead">loading…</div>
  </div>
  <div class="muted" style="font-size:11px">single-file • offline-viewable • <span id="exportedAt"></span></div>
</div>

<div id="root"></div>

<div class="integrity panel">
  <strong>Integrity</strong> · this file was generated with a cryptographic
  fingerprint of the embedded data.<br>
  <span class="muted">data sha256:</span>
  <span class="sha">__ATLAST_DATA_SHA__</span><br>
  <span class="muted">verify with:</span>
  <code class="sha">echo -n &lt;the base64 data block&gt; | shasum -a 256</code>
</div>

<script id="atlast-data" type="application/json">__ATLAST_DATA_B64__</script>
<script>
(function() {
  // Decode the embedded bundle. The data island holds base64 to keep it
  // transport-safe (no quote escaping needed in HTML).
  var b64 = document.getElementById('atlast-data').textContent.trim();
  var json;
  try {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    var text = new TextDecoder('utf-8').decode(bytes);
    json = JSON.parse(text);
  } catch (e) {
    document.getElementById('root').textContent = 'failed to decode evidence: ' + e;
    return;
  }

  var rec = json.record || {};
  var vault = json.vault || {};
  var wires = json.wire_entries || [];

  document.getElementById('subhead').textContent =
    rec.id + ' · ' + (rec.action || 'record') + ' · ' + (rec.agent || 'unknown agent');
  document.getElementById('exportedAt').textContent =
    new Date(json.exported_at_unix_ms || Date.now()).toISOString();

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function fmtBytes(n) { if (n == null) return '?'; if (n < 1024) return n + ' B'; if (n < 1048576) return (n/1024).toFixed(1) + ' KB'; return (n/1048576).toFixed(2) + ' MB'; }
  function row(k, v) { return '<div class="k">' + escapeHtml(k) + '</div><div>' + (v == null ? '<span class="muted">—</span>' : v) + '</div>'; }

  var root = document.getElementById('root');

  // ── Record summary ──
  var html = '<h2>Record</h2><div class="panel"><div class="kv">';
  html += row('id', '<code>' + escapeHtml(rec.id) + '</code>');
  html += row('agent', escapeHtml(rec.agent));
  html += row('action', escapeHtml(rec.action));
  html += row('timestamp', new Date(rec.ts).toISOString());
  if (rec.meta && rec.meta.model) html += row('model', escapeHtml(rec.meta.model));
  if (rec.meta && rec.meta.latency_ms != null) html += row('latency', rec.meta.latency_ms + ' ms');
  if (rec.meta && rec.meta.flags) html += row('flags', (rec.meta.flags || []).map(function(f) { return '<span class="pill">' + escapeHtml(f) + '</span>'; }).join(''));
  html += row('input hash', '<span class="sha">' + escapeHtml(rec.in_hash) + '</span>');
  html += row('output hash', '<span class="sha">' + escapeHtml(rec.out_hash) + '</span>');
  html += row('chain prev', '<span class="sha">' + escapeHtml(rec.chain && rec.chain.prev) + '</span>');
  html += row('chain hash', '<span class="sha">' + escapeHtml(rec.chain && rec.chain.hash) + '</span>');
  html += row('signature', '<span class="sha">' + escapeHtml(rec.sig) + '</span>');
  html += '</div></div>';

  // ── Local summary (human-readable input/output) ──
  if (json.local_summary) {
    html += '<h2>Local Summary</h2><div class="panel"><pre>' + escapeHtml(json.local_summary) + '</pre></div>';
  }

  // ── Vault detail ──
  if (vault && Object.keys(vault).length) {
    html += '<h2>Vault</h2><div class="panel">';
    if (vault.system_prompt) {
      html += '<details><summary><strong>System Prompt</strong> ('
              + fmtBytes((vault.system_prompt || '').length) + ')</summary>';
      html += '<pre>' + escapeHtml(typeof vault.system_prompt === 'string' ? vault.system_prompt : JSON.stringify(vault.system_prompt, null, 2)) + '</pre>';
      html += '</details>';
    }
    if (vault.input_text) {
      html += '<details open><summary><strong>Input</strong> ('
              + fmtBytes((vault.input_text || '').length) + ')</summary>';
      html += '<pre>' + escapeHtml(vault.input_text) + '</pre></details>';
    }
    if (vault.output_text) {
      html += '<details open><summary><strong>Output</strong> ('
              + fmtBytes((vault.output_text || '').length) + ')</summary>';
      html += '<pre>' + escapeHtml(vault.output_text) + '</pre></details>';
    }
    if (vault.conversation_steps && vault.conversation_steps.length) {
      html += '<details><summary><strong>Conversation Steps</strong> ('
              + vault.conversation_steps.length + ')</summary>';
      html += '<pre>' + escapeHtml(JSON.stringify(vault.conversation_steps, null, 2)) + '</pre></details>';
    }
    html += '</div>';
  }

  // ── Wire evidence (Vault v4) ──
  if (wires.length) {
    html += '<h2>Wire-Level Evidence (Vault v4) <span class="badge">' + wires.length + ' roundtrip' + (wires.length > 1 ? 's' : '') + '</span></h2>';
    wires.forEach(function(w, i) {
      var req = w.request || {};
      var resp = w.response || {};
      var t = w.timing || {};
      html += '<div class="panel">';
      html += '<h3>Roundtrip ' + (i + 1) + ' · ' + escapeHtml(w.wire_id) + '</h3>';
      html += '<div class="kv">';
      html += row('provider', escapeHtml(w.provider));
      html += row('method/url', escapeHtml(req.method) + ' ' + escapeHtml(req.url));
      html += row('model', escapeHtml(req.model));
      html += row('status', resp.status + ' <span class="muted">request-id: ' + escapeHtml(resp.request_id || '—') + '</span>');
      html += row('streaming', req.is_streaming ? 'yes (SSE)' : 'no (JSON)');
      html += row('counts', 'tools: ' + req.tool_count + ' · messages: ' + req.message_count);
      html += row('sizes', 'req: ' + fmtBytes(req.body_bytes) + ' · resp: ' + fmtBytes(resp.body_bytes));
      html += row('duration', (t.duration_ms || 0) + ' ms');
      html += row('req sha256', '<span class="sha">' + escapeHtml(req.body_sha256) + '</span>');
      html += row('resp sha256', '<span class="sha">' + escapeHtml(resp.body_sha256) + '</span>');
      if (req.system_prompt_sha256) html += row('system sha256', '<span class="sha">' + escapeHtml(req.system_prompt_sha256) + '</span>');
      if (req.tool_definitions_sha256) html += row('tools sha256', '<span class="sha">' + escapeHtml(req.tool_definitions_sha256) + '</span>');
      html += '</div>';
      // Bodies
      if (req.body_text) {
        html += '<details><summary><strong>Request body</strong> (' + fmtBytes((req.body_text || '').length) + ')</summary>';
        html += '<pre>' + escapeHtml(req.body_text) + '</pre></details>';
      }
      if (resp.body_text) {
        html += '<details><summary><strong>Response body</strong> ' + (resp.is_sse ? '<span class="pill">SSE</span>' : '<span class="pill">JSON</span>') + ' (' + fmtBytes((resp.body_text || '').length) + ')</summary>';
        html += '<pre>' + escapeHtml(resp.body_text) + '</pre></details>';
      }
      // Headers (already redacted at write-time)
      if (req.headers && Object.keys(req.headers).length) {
        html += '<details><summary><strong>Request headers</strong> (' + Object.keys(req.headers).length + ')</summary>';
        html += '<pre>' + escapeHtml(JSON.stringify(req.headers, null, 2)) + '</pre></details>';
      }
      if (resp.headers && Object.keys(resp.headers).length) {
        html += '<details><summary><strong>Response headers</strong> (' + Object.keys(resp.headers).length + ')</summary>';
        html += '<pre>' + escapeHtml(JSON.stringify(resp.headers, null, 2)) + '</pre></details>';
      }
      html += '</div>';
    });
  } else {
    html += '<h2>Wire-Level Evidence</h2><div class="panel muted">No wire evidence attached to this record. (Vault v3 record from before wire capture, or wire was disabled.)</div>';
  }

  root.innerHTML = html;
})();
</script>
</body>
</html>
"""


def export_record_html(record_id: str, output_path: Optional[Path] = None) -> Path:
    """Build a self-contained HTML evidence file for a single record.

    Returns the path the file was written to. Default path is
    ./atlast-evidence-<record_id>.html in the current working directory.
    """
    bundle = _gather_record_bundle(record_id)

    # Encode bundle as base64(json) to keep it embed-safe and easy to verify.
    raw_json = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64 = base64.b64encode(raw_json).decode("ascii")
    sha = hashlib.sha256(b64.encode("ascii")).hexdigest()

    html = (_TEMPLATE
            .replace("__RECORD_ID__", record_id)
            .replace("__ATLAST_DATA_B64__", b64)
            .replace("__ATLAST_DATA_SHA__", sha))

    out = output_path or Path.cwd() / f"atlast-evidence-{record_id}.html"
    out = Path(out)
    out.write_text(html, encoding="utf-8")
    return out
