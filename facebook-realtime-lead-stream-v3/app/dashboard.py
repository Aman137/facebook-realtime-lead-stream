from __future__ import annotations


def dashboard_html(refresh_seconds: int) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lead Stream Operations</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#64748b; --line:#dbe3ee;
      --brand:#155eef; --good:#137a55; --bad:#b42318; --bg:#f6f8fc; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 system-ui,sans-serif; }}
    main {{ max-width:1200px; margin:0 auto; padding:28px 20px 56px; }}
    header {{ display:flex; justify-content:space-between; gap:24px; align-items:end; margin-bottom:22px; }}
    h1 {{ margin:0; font-size:27px; }} h2 {{ font-size:18px; margin:30px 0 12px; }}
    p {{ color:var(--muted); margin:5px 0 0; }}
    .auth {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
    input,button {{ border:1px solid var(--line); border-radius:8px; padding:9px 11px; font:inherit; }}
    input {{ min-width:235px; background:white; }} button {{ cursor:pointer; background:var(--brand); color:white; border-color:var(--brand); font-weight:650; }}
    .status {{ min-height:20px; margin:8px 0 16px; color:var(--muted); }}
    .status.error {{ color:var(--bad); }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); gap:12px; }}
    .card {{ background:white; border:1px solid var(--line); border-radius:12px; padding:16px; }}
    .card span {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
    .card strong {{ display:block; font-size:25px; margin-top:5px; }}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:12px; background:white; }}
    table {{ width:100%; border-collapse:collapse; min-width:780px; }}
    th,td {{ text-align:left; padding:11px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ color:#344054; background:#f8fafc; font-size:12px; text-transform:uppercase; letter-spacing:.03em; }}
    tr:last-child td {{ border-bottom:0; }}
    .pill {{ display:inline-block; border-radius:999px; padding:2px 8px; background:#eef4ff; color:#1849a9; font-size:12px; }}
    .qualified {{ background:#ecfdf3; color:var(--good); }} .failed {{ background:#fef3f2; color:var(--bad); }}
    .text {{ max-width:390px; }} .muted {{ color:var(--muted); }}
    a {{ color:var(--brand); }}
    @media (max-width:720px) {{ header {{ align-items:start; flex-direction:column; }} .auth {{ justify-content:start; }} }}
  </style>
</head>
<body><main>
  <header><div><h1>Lead Stream Operations</h1><p>Live pipeline activity, latency, filters, and failures.</p></div>
    <div class="auth"><input id="key" type="password" autocomplete="off" placeholder="Dashboard key"><button id="connect">Connect</button></div>
  </header>
  <div id="status" class="status">Enter the dashboard key from your .env file.</div>
  <section class="cards" id="cards"></section>
  <h2>Qualified leads by category</h2>
  <div class="table-wrap"><table><thead><tr><th>Category</th><th>Count</th></tr></thead><tbody id="categories"></tbody></table></div>
  <h2>Recent events</h2>
  <div class="table-wrap"><table><thead><tr><th>Time</th><th>Status</th><th>Group</th><th>Category</th><th>Confidence</th><th>Post</th></tr></thead><tbody id="events"></tbody></table></div>
  <h2>Recent failures</h2>
  <div class="table-wrap"><table><thead><tr><th>Time</th><th>Stage</th><th>Event</th><th>Attempts</th><th>Error</th></tr></thead><tbody id="failures"></tbody></table></div>
</main>
<script>
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const keyInput = $('key');
keyInput.value = sessionStorage.getItem('leadDashboardKey') || '';
const request = async (path) => {{
  const response = await fetch(path, {{headers: {{'X-Dashboard-Key': keyInput.value}}}});
  if (!response.ok) throw new Error(response.status === 401 ? 'Incorrect dashboard key.' : `Request failed (${{response.status}}).`);
  return response.json();
}};
const pill = (status) => `<span class="pill ${{status === 'qualified' ? 'qualified' : status === 'failed' ? 'failed' : ''}}">${{escapeHtml(status)}}</span>`;
async function refresh() {{
  if (!keyInput.value) return;
  try {{
    const [stats, events, failures] = await Promise.all([request('/stats'), request('/events/recent?limit=25'), request('/failures?limit=25')]);
    sessionStorage.setItem('leadDashboardKey', keyInput.value);
    const values = [
      ['Events', stats.total_events], ['Qualified', stats.qualified], ['Rejected', stats.rejected],
      ['Notified', stats.notified], ['Failures', stats.unresolved_failures], ['Duplicates', stats.duplicates_suppressed],
      ['Avg processing', `${{Number(stats.avg_processing_ms).toFixed(0)}} ms`],
      ['Avg notification', `${{Number(stats.avg_notification_latency_ms).toFixed(0)}} ms`]
    ];
    $('cards').innerHTML = values.map(([label,value]) => `<div class="card"><span>${{label}}</span><strong>${{value}}</strong></div>`).join('');
    $('categories').innerHTML = (stats.qualified_by_category.length ? stats.qualified_by_category : [{{category:'No qualified leads yet',count:0}}])
      .map(row => `<tr><td>${{escapeHtml(row.category)}}</td><td>${{row.count}}</td></tr>`).join('');
    $('events').innerHTML = (events.length ? events : [null]).map(row => row ? `<tr>
      <td class="muted">${{new Date(row.received_at).toLocaleString()}}</td><td>${{pill(row.status)}}</td>
      <td>${{escapeHtml(row.group_name)}}</td><td>${{escapeHtml(row.classification?.category || '-')}}</td>
      <td>${{row.classification ? Math.round(row.classification.confidence * 100) + '%' : '-'}}</td>
      <td class="text">${{escapeHtml(row.post_text)}}</td></tr>` : '<tr><td colspan="6">No events yet.</td></tr>').join('');
    $('failures').innerHTML = (failures.length ? failures : [null]).map(row => row ? `<tr>
      <td class="muted">${{new Date(row.failed_at).toLocaleString()}}</td><td>${{escapeHtml(row.stage)}}</td>
      <td>${{escapeHtml(row.event_id)}}</td><td>${{row.attempts}}</td><td class="text">${{escapeHtml(row.error)}}</td></tr>` : '<tr><td colspan="5">No failures recorded.</td></tr>').join('');
    $('status').className = 'status'; $('status').textContent = `Connected. Refreshes every {refresh_seconds} seconds.`;
  }} catch (error) {{ $('status').className = 'status error'; $('status').textContent = error.message; }}
}}
$('connect').addEventListener('click', refresh);
keyInput.addEventListener('keydown', event => {{ if (event.key === 'Enter') refresh(); }});
if (keyInput.value) refresh();
setInterval(refresh, {refresh_seconds * 1000});
</script></body></html>"""
