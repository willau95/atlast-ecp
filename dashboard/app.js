/* ATLAST Dashboard — app.js */

const DEFAULT_API = 'https://api.weba0.com/v1';
let API_URL = localStorage.getItem('atlast_api_url') || DEFAULT_API;
let API_KEY = localStorage.getItem('atlast_api_key') || '';
let AGENT = null; // { did, public_key, created_at, ... }
let currentPage = 'overview';

// ── API helpers ──

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (API_KEY) headers['X-API-Key'] = API_KEY;
  const res = await fetch(`${API_URL}${path}`, { ...opts, headers: { ...headers, ...opts.headers } });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

// ── Auth ──

async function doLogin() {
  const input = document.getElementById('api-key-input');
  const btn = document.getElementById('login-btn');
  const err = document.getElementById('login-error');
  const key = input.value.trim();
  if (!key) { err.textContent = 'Please enter an API key'; err.hidden = false; return; }

  btn.disabled = true; btn.textContent = 'Connecting...'; err.hidden = true;
  API_KEY = key;
  try {
    AGENT = await api('/auth/me');
    localStorage.setItem('atlast_api_key', key);
    showDashboard();
  } catch (e) {
    err.textContent = `Authentication failed: ${e.message}`; err.hidden = false;
    API_KEY = '';
  } finally {
    btn.disabled = false; btn.textContent = 'Connect';
  }
}

function doLogout() {
  localStorage.removeItem('atlast_api_key');
  API_KEY = ''; AGENT = null;
  document.getElementById('main').hidden = true;
  document.getElementById('login-screen').hidden = false;
  document.getElementById('api-key-input').value = '';
}

function showDashboard() {
  document.getElementById('login-screen').hidden = true;
  document.getElementById('main').hidden = false;
  navigate('overview');
}

// ── Navigation ──

function navigate(page) {
  currentPage = page;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.page === page));
  document.querySelectorAll('.page').forEach(p => p.hidden = true);
  const el = document.getElementById(`page-${page}`);
  if (el) { el.hidden = false; }
  const loaders = { overview: loadOverview, records: loadRecords, batches: loadBatches, superbatches: loadSuperBatches, chain: loadChain, settings: loadSettings };
  if (loaders[page]) loaders[page]();
}

// ── Overview ──

async function loadOverview() {
  const page = document.getElementById('page-overview');
  page.innerHTML = `
    <div class="page-header"><h2>Overview</h2><p>Your ATLAST Protocol dashboard</p></div>
    <div class="cards" id="overview-cards"><div class="loading">Loading</div></div>
    <div class="page-header" style="margin-top:12px"><h2 style="font-size:1rem">Server Status</h2></div>
    <div class="cards" id="server-cards"><div class="loading">Loading</div></div>
  `;

  try {
    const [stats, agentInfo] = await Promise.all([
      api('/stats').catch(() => null),
      AGENT || api('/auth/me').catch(() => null)
    ]);
    if (agentInfo) AGENT = agentInfo;

    const oc = document.getElementById('overview-cards');
    oc.innerHTML = `
      <div class="card card-accent"><div class="card-label">Agent DID</div><div class="card-value" style="font-size:0.9rem">${truncDid(AGENT?.did)}</div><div class="card-sub">${AGENT?.created_at ? 'Since ' + fmtDate(AGENT.created_at) : ''}</div></div>
      <div class="card"><div class="card-label">Total Records</div><div class="card-value">${AGENT?.record_count ?? '—'}</div></div>
      <div class="card"><div class="card-label">Total Batches</div><div class="card-value">${AGENT?.batch_count ?? '—'}</div></div>
      <div class="card"><div class="card-label">Status</div><div class="card-value"><span class="badge badge-green">Active</span></div></div>
    `;

    const sc = document.getElementById('server-cards');
    if (stats) {
      sc.innerHTML = `
        <div class="card"><div class="card-label">Attestations</div><div class="card-value">${stats.total_attestations ?? 0}</div></div>
        <div class="card"><div class="card-label">Anchored Batches</div><div class="card-value">${stats.total_anchored ?? 0}</div></div>
        <div class="card"><div class="card-label">Pending</div><div class="card-value">${stats.pending_batches ?? 0}</div></div>
        <div class="card"><div class="card-label">Server</div><div class="card-value"><span class="badge badge-green">Online</span></div></div>
      `;
    } else {
      sc.innerHTML = '<div class="card"><div class="card-label">Server</div><div class="card-value"><span class="badge badge-red">Unreachable</span></div></div>';
    }
  } catch (e) {
    document.getElementById('overview-cards').innerHTML = `<div class="error">${e.message}</div>`;
  }
}

// ── Records ──

let allRecords = [];

async function loadRecords() {
  const page = document.getElementById('page-records');
  page.innerHTML = `
    <div class="page-header"><h2>Records</h2><p>Evidence chain records for your agent</p></div>
    <div class="search-bar">
      <input type="text" id="records-search" placeholder="Search by ID, type, or hash..." oninput="filterRecords()">
      <select id="records-filter" onchange="filterRecords()">
        <option value="">All types</option>
        <option value="llm_call">llm_call</option>
        <option value="tool_call">tool_call</option>
        <option value="stability_check">stability_check</option>
      </select>
    </div>
    <div id="records-table" class="table-wrap"><div class="loading">Loading records</div></div>
  `;

  if (!AGENT?.did) return;
  try {
    const data = await api(`/discovery/agents/${encodeURIComponent(AGENT.did)}/records`);
    allRecords = data.records || data || [];
    renderRecords(allRecords);
  } catch (e) {
    document.getElementById('records-table').innerHTML = `<div class="error">${e.message}</div>`;
  }
}

function filterRecords() {
  const q = (document.getElementById('records-search')?.value || '').toLowerCase();
  const t = document.getElementById('records-filter')?.value || '';
  const filtered = allRecords.filter(r => {
    const matchQ = !q || JSON.stringify(r).toLowerCase().includes(q);
    const matchT = !t || (r.step_type || r.action) === t;
    return matchQ && matchT;
  });
  renderRecords(filtered);
}

function renderRecords(records) {
  const el = document.getElementById('records-table');
  if (!records.length) {
    el.innerHTML = '<div class="empty"><div class="empty-icon">◎</div><p>No records found</p></div>';
    return;
  }
  el.innerHTML = `<table>
    <tr><th>ID</th><th>Type</th><th>In Hash</th><th>Out Hash</th><th>Chain Hash</th><th>Time</th></tr>
    ${records.slice(0, 200).map(r => `<tr onclick="showRecordDetail('${r.id || r.record_id}')" style="cursor:pointer">
      <td class="mono">${trunc(r.id || r.record_id, 20)}</td>
      <td><span class="badge badge-green">${r.step_type || r.action || '—'}</span></td>
      <td class="mono truncate" title="${r.in_hash || ''}">${trunc(r.in_hash, 16)}</td>
      <td class="mono truncate" title="${r.out_hash || ''}">${trunc(r.out_hash, 16)}</td>
      <td class="mono truncate" title="${r.chain_hash || ''}">${trunc(r.chain_hash, 16)}</td>
      <td>${fmtDate(r.timestamp || r.ts)}</td>
    </tr>`).join('')}
  </table>`;
}

function showRecordDetail(id) {
  const r = allRecords.find(x => (x.id || x.record_id) === id);
  if (!r) return;
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `<div class="modal">
    <span class="modal-close" onclick="this.closest('.modal-overlay').remove()">✕</span>
    <h3>Record ${trunc(id, 24)}</h3>
    ${Object.entries(r).map(([k, v]) => `<div class="detail-row"><span class="detail-key">${k}</span><span class="detail-val">${typeof v === 'object' ? JSON.stringify(v, null, 2) : v}</span></div>`).join('')}
  </div>`;
  document.body.appendChild(overlay);
}

// ── Batches ──

async function loadBatches() {
  const page = document.getElementById('page-batches');
  page.innerHTML = `
    <div class="page-header"><h2>Batches</h2><p>Batch uploads and on-chain anchoring status</p></div>
    <div id="batches-table" class="table-wrap"><div class="loading">Loading batches</div></div>
  `;

  try {
    // Try discovery endpoint or use agent records to infer batches
    let batches = [];
    try {
      const data = await api('/discovery/batches');
      batches = data.batches || data || [];
    } catch {
      // Fallback: try individual batch lookup if we have IDs
      batches = [];
    }

    const el = document.getElementById('batches-table');
    if (!batches.length) {
      el.innerHTML = `<div class="empty"><div class="empty-icon">⧉</div><p>No batches found</p><p style="margin-top:8px;font-size:0.8rem">Batches are created automatically when records are uploaded to the server</p></div>`;
      return;
    }

    el.innerHTML = `<table>
      <tr><th>Batch ID</th><th>Status</th><th>Records</th><th>Merkle Root</th><th>Attestation</th><th>Time</th></tr>
      ${batches.map(b => `<tr>
        <td class="mono">${trunc(b.batch_id || b.id, 24)}</td>
        <td>${b.attestation_uid ? '<span class="badge badge-green">Anchored</span>' : '<span class="badge badge-yellow">Pending</span>'}</td>
        <td>${b.record_count || b.record_hashes?.length || '—'}</td>
        <td class="mono truncate" title="${b.merkle_root || ''}">${trunc(b.merkle_root, 16)}</td>
        <td>${b.attestation_uid ? `<a href="https://base-sepolia.easscan.org/attestation/view/${b.attestation_uid}" target="_blank">${trunc(b.attestation_uid, 12)}</a>` : '—'}</td>
        <td>${fmtDate(b.created_at || b.timestamp)}</td>
      </tr>`).join('')}
    </table>`;
  } catch (e) {
    document.getElementById('batches-table').innerHTML = `<div class="error">${e.message}</div>`;
  }
}

// ── Super-Batches ──

async function loadSuperBatches() {
  const page = document.getElementById('page-superbatches');
  page.innerHTML = `
    <div class="page-header"><h2>Super-Batches</h2><p>Aggregated on-chain attestations — 1000x gas savings</p></div>
    <div id="superbatch-content"><div class="loading">Loading</div></div>
  `;

  try {
    // Fetch recent attestations that may contain super-batch info
    const attestations = await api('/attestations').catch(() => ({ attestations: [] }));
    const el = document.getElementById('superbatch-content');

    // Try to fetch any super-batches from stats or attestation UIDs
    const items = attestations.attestations || [];
    const superBatchIds = new Set();
    const sbData = [];

    // Check each attestation for super_batch references
    for (const att of items.slice(0, 20)) {
      if (att.super_batch_id && !superBatchIds.has(att.super_batch_id)) {
        superBatchIds.add(att.super_batch_id);
        try {
          const sb = await api(`/super-batches/${att.super_batch_id}`);
          sbData.push(sb);
        } catch { /* not found */ }
      }
    }

    if (sbData.length === 0) {
      el.innerHTML = `
        <div class="empty">
          <div class="empty-icon">⬡</div>
          <p>No super-batches yet</p>
          <p class="empty-sub">Super-batches are created when ≥${5} batches are pending during an anchor cycle.<br>
          Each super-batch aggregates multiple batches into a single on-chain attestation.</p>
        </div>
      `;
      return;
    }

    el.innerHTML = `
      <div class="table-wrap"><table class="data-table">
        <thead><tr>
          <th>Super-Batch ID</th>
          <th>Batches</th>
          <th>Merkle Root</th>
          <th>Attestation</th>
          <th>Status</th>
          <th>Created</th>
        </tr></thead>
        <tbody>${sbData.map(sb => `<tr onclick="showSuperBatchDetail('${sb.super_batch_id}')">
          <td><code>${trunc(sb.super_batch_id, 20)}</code></td>
          <td>${sb.batch_count}</td>
          <td><code>${trunc(sb.super_merkle_root, 24)}</code></td>
          <td>${sb.attestation_uid ? `<a href="https://base.easscan.org/attestation/view/${sb.attestation_uid}" target="_blank">${trunc(sb.attestation_uid, 16)}</a>` : '—'}</td>
          <td><span class="badge ${sb.status === 'anchored' ? 'badge-green' : 'badge-yellow'}">${sb.status}</span></td>
          <td>${fmtDate(sb.created_at)}</td>
        </tr>`).join('')}</tbody>
      </table></div>
    `;
  } catch (e) {
    document.getElementById('superbatch-content').innerHTML = `<div class="error">${e.message}</div>`;
  }
}

async function showSuperBatchDetail(sbId) {
  try {
    const sb = await api(`/super-batches/${sbId}`);
    const batchList = (sb.batch_ids || []).map(id => `<li><code>${id}</code></li>`).join('');
    const detail = `
      <div class="modal-overlay" onclick="this.remove()">
        <div class="modal" onclick="event.stopPropagation()">
          <h3>Super-Batch Detail</h3>
          <div class="setting-row"><span class="setting-label">ID</span><code>${sb.super_batch_id}</code></div>
          <div class="setting-row"><span class="setting-label">Merkle Root</span><code style="font-size:0.75rem;word-break:break-all">${sb.super_merkle_root}</code></div>
          <div class="setting-row"><span class="setting-label">Attestation</span><a href="https://base.easscan.org/attestation/view/${sb.attestation_uid}" target="_blank">${sb.attestation_uid || '—'}</a></div>
          <div class="setting-row"><span class="setting-label">TX Hash</span><code style="font-size:0.75rem">${sb.eas_tx_hash || '—'}</code></div>
          <div class="setting-row"><span class="setting-label">Batch Count</span>${sb.batch_count}</div>
          <div class="setting-row"><span class="setting-label">Status</span><span class="badge ${sb.status === 'anchored' ? 'badge-green' : 'badge-yellow'}">${sb.status}</span></div>
          <div class="setting-row"><span class="setting-label">Created</span>${fmtDate(sb.created_at)}</div>
          <div class="setting-row"><span class="setting-label">Anchored</span>${fmtDate(sb.anchored_at)}</div>
          <h4>Included Batches (${sb.batch_count})</h4>
          <ul class="batch-list">${batchList || '<li>—</li>'}</ul>
          <button class="btn" onclick="this.closest('.modal-overlay').remove()">Close</button>
        </div>
      </div>
    `;
    document.body.insertAdjacentHTML('beforeend', detail);
  } catch (e) {
    alert(`Failed to load: ${e.message}`);
  }
}

// ── Chain Visualization ──

async function loadChain() {
  const page = document.getElementById('page-chain');
  page.innerHTML = `
    <div class="page-header"><h2>Evidence Chain</h2><p>Visual chain of records linked by cryptographic hashes</p></div>
    <div id="chain-viz"><div class="loading">Loading chain</div></div>
  `;

  if (!AGENT?.did) return;
  try {
    const data = await api(`/discovery/agents/${encodeURIComponent(AGENT.did)}/records`);
    const records = (data.records || data || []).slice(0, 50); // Show last 50
    const el = document.getElementById('chain-viz');

    if (!records.length) {
      el.innerHTML = '<div class="empty"><div class="empty-icon">⟠</div><p>No records in chain yet</p></div>';
      return;
    }

    // Reverse to show newest first
    const reversed = [...records].reverse();
    el.innerHTML = '<div class="chain-container">' + reversed.map((r, i) => {
      const isGenesis = !r.prev_hash || r.prev_hash === 'genesis';
      return `
        ${i > 0 ? '<div class="chain-link">↓</div>' : ''}
        <div class="chain-node ${isGenesis ? 'chain-genesis' : ''}">
          <div class="chain-node-time">${fmtDate(r.timestamp || r.ts)}</div>
          <div class="chain-node-id">${r.id || r.record_id || '—'}</div>
          <div class="chain-node-type">${r.step_type || r.action || 'record'} ${isGenesis ? '· GENESIS' : ''}</div>
          <div class="chain-node-hash">chain: ${trunc(r.chain_hash, 32)}</div>
          <div class="chain-node-hash">prev: ${isGenesis ? 'genesis' : trunc(r.prev_hash, 32)}</div>
        </div>`;
    }).join('') + '</div>';
  } catch (e) {
    document.getElementById('chain-viz').innerHTML = `<div class="error">${e.message}</div>`;
  }
}

// ── Settings ──

async function loadSettings() {
  const page = document.getElementById('page-settings');
  page.innerHTML = `
    <div class="page-header"><h2>Settings</h2><p>Agent configuration and API key management</p></div>
    <div class="settings-section">
      <h3>Agent Identity</h3>
      <div class="setting-row"><span class="setting-label">DID</span><span class="setting-value">${AGENT?.did || '—'}</span></div>
      <div class="setting-row"><span class="setting-label">Public Key</span><span class="setting-value" style="font-size:0.75rem">${AGENT?.public_key || '—'}</span></div>
      <div class="setting-row"><span class="setting-label">Created</span><span class="setting-value">${AGENT?.created_at ? fmtDate(AGENT.created_at) : '—'}</span></div>
    </div>
    <div class="settings-section">
      <h3>API Key</h3>
      <div class="setting-row"><span class="setting-label">Current Key</span><span class="setting-value">${maskKey(API_KEY)}</span></div>
      <div class="setting-row"><span class="setting-label"></span><button class="btn" onclick="rotateKey()">Rotate Key</button></div>
    </div>
    <div class="settings-section">
      <h3>Server</h3>
      <div class="setting-row">
        <span class="setting-label">API Endpoint</span>
        <input type="text" id="settings-api-url" class="setting-value" value="${API_URL}" style="border:1px solid var(--border);background:var(--bg)">
      </div>
      <div class="setting-row"><span class="setting-label"></span><button class="btn" onclick="saveApiUrl()">Save</button></div>
    </div>
    <div class="settings-section">
      <h3>Danger Zone</h3>
      <button class="btn btn-danger" onclick="doLogout()">Logout & Clear Data</button>
    </div>
  `;
}

async function rotateKey() {
  if (!confirm('Rotate your API key? The current key will be invalidated.')) return;
  try {
    const data = await api('/auth/rotate-key', { method: 'POST' });
    const newKey = data.api_key || data.key;
    if (newKey) {
      API_KEY = newKey;
      localStorage.setItem('atlast_api_key', newKey);
      alert(`New key: ${newKey}\n\nSave this key — it won't be shown again!`);
      loadSettings();
    }
  } catch (e) {
    alert(`Failed to rotate key: ${e.message}`);
  }
}

function saveApiUrl() {
  const url = document.getElementById('settings-api-url')?.value?.trim();
  if (url) {
    API_URL = url;
    localStorage.setItem('atlast_api_url', url);
    alert('API endpoint updated');
  }
}

// ── Helpers ──

function trunc(s, n = 16) { if (!s) return '—'; return s.length > n ? s.slice(0, n) + '…' : s; }
function truncDid(did) { if (!did) return '—'; if (did.length > 30) return did.slice(0, 16) + '…' + did.slice(-8); return did; }
function maskKey(k) { if (!k) return '—'; return k.slice(0, 8) + '••••••••' + k.slice(-4); }
function fmtDate(d) {
  if (!d) return '—';
  try { const dt = new Date(d); return dt.toLocaleDateString() + ' ' + dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  catch { return d; }
}

// ── Init ──

document.getElementById('api-key-input').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });

// ── Auto-Refresh ──

let _refreshTimer = null;
let autoRefresh = localStorage.getItem('atlast_auto_refresh') !== 'false';

function startAutoRefresh() {
  stopAutoRefresh();
  if (autoRefresh && currentPage === 'overview') {
    _refreshTimer = setInterval(() => { if (currentPage === 'overview') loadOverview(); }, 30000);
  }
}

function stopAutoRefresh() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}

// Start auto-refresh when on overview
const _origNavigate = navigate;
// (auto-refresh hooks into page transitions via the loader map)

// Auto-login if key exists
if (API_KEY) {
  api('/auth/me').then(agent => { AGENT = agent; showDashboard(); }).catch(() => {
    localStorage.removeItem('atlast_api_key'); API_KEY = '';
  });
}
