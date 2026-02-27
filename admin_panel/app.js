const API = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : `${window.location.protocol}//${window.location.host}`;

document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', e => {
        e.preventDefault();
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        el.classList.add('active');
        document.getElementById('page-' + el.dataset.page).classList.add('active');
        loadPage(el.dataset.page);
    });
});

const overrideHistory = [];

async function loadPage(name) {
    if (name === 'alerts') await loadAlerts();
    if (name === 'reports') await loadReports();
    if (name === 'recommendations') await loadCropAI();
    if (name === 'market') await loadMarket();
    if (name === 'camera') await loadCamera();
    if (name === 'status') await loadStatus();
}

async function loadAlerts() {
    try {
        const r = await fetch(`${API}/api/v1/alerts/?unacknowledged_only=false&limit=30`);
        if (!r.ok) throw new Error('Failed');
        const data = await r.json();
        renderAlerts(data);
    } catch { renderAlerts([]); }
}

function renderAlerts(data) {
    const el = document.getElementById('alert-list');
    if (data.length === 0) {
        el.innerHTML = '<div style="text-align:center;color:var(--gray-mid);padding:2rem">No alerts — system is clean ✓</div>';
        return;
    }
    el.innerHTML = data.map(a => {
        const sev = (a.severity || '').toLowerCase();
        const cls = sev === 'critical' ? 'critical' : sev === 'warning' ? 'warning' : '';
        const color = sev === 'critical' ? 'var(--red-text)' : sev === 'warning' ? 'var(--orange-text)' : 'var(--gray-mid)';
        const ts = a.created_at ? new Date(a.created_at).toLocaleString('en-IN') : '--';
        return `
      <div class="alert-row ${cls}">
        <div class="alert-info-col">
          <div class="alert-type-badge" style="color:${color}">${a.alert_type}</div>
          <div class="alert-msg">${a.message}</div>
          <div class="alert-meta">${ts} · ${a.zone_id || 'Global'} · ${a.severity}</div>
        </div>
        ${!a.acknowledged ? `<button class="ack-btn" onclick="acknowledgeAlert(${a.id}, this)">Acknowledge</button>` : '<span style="font-size:0.65rem;color:var(--gray-mid)">Acknowledged</span>'}
      </div>`;
    }).join('');
}

async function acknowledgeAlert(id, btn) {
    try {
        await fetch(`${API}/api/v1/alerts/${id}/acknowledge`, { method: 'POST' });
        btn.textContent = 'Done ✓';
        btn.disabled = true;
        btn.style.color = 'var(--green-text)';
    } catch { btn.textContent = 'Error'; }
}

let reportChart = null;
async function loadReports() {
    try {
        const r = await fetch(`${API}/api/v1/admin/reports/irrigation-summary?days=7`);
        if (!r.ok) throw new Error();
        const data = await r.json();
        const tbody = document.getElementById('report-tbody');
        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--gray-mid)">No data yet — run some irrigation cycles</td></tr>';
            return;
        }
        tbody.innerHTML = data.map(z => `
      <tr>
        <td>${z.zone_id}</td>
        <td>${z.event_count}</td>
        <td>${z.total_water_litres.toFixed(1)}</td>
        <td>${z.total_duration_hours.toFixed(2)}</td>
      </tr>`).join('');

        const ctx = document.getElementById('report-chart').getContext('2d');
        if (reportChart) reportChart.destroy();
        reportChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.zone_id),
                datasets: [{
                    label: 'Water Used (L)',
                    data: data.map(d => d.total_water_litres),
                    backgroundColor: 'rgba(255,255,255,0.12)',
                    borderColor: '#ffffff',
                    borderWidth: 1,
                    borderRadius: 4,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: '#909090', font: { family: 'JetBrains Mono', size: 11 } } },
                    tooltip: { backgroundColor: '#181818', borderColor: '#2a2a2a', borderWidth: 1, titleColor: '#f0f0f0', bodyColor: '#b0b0b0' }
                },
                scales: {
                    x: { ticks: { color: '#606060' }, grid: { color: '#181818' } },
                    y: { ticks: { color: '#606060' }, grid: { color: '#1e1e1e' } }
                }
            }
        });
    } catch { }
}

async function loadCropAI() {
    try {
        const r = await fetch(`${API}/api/v1/admin/reports/crop-recommendations`);
        if (!r.ok) throw new Error();
        const data = await r.json();
        const grid = document.getElementById('crop-grid');
        grid.innerHTML = data.recommendations.map(c => `
      <div class="crop-card">
        <div class="crop-name">${c.crop}</div>
        <div class="crop-score">
          <div class="score-bar"><div class="score-fill" style="width:${c.suitability_score * 100}%"></div></div>
          <span class="score-val">${(c.suitability_score * 100).toFixed(0)}%</span>
        </div>
        <div class="crop-meta">
          💧 ${c.water_requirement} water<br>
          🌾 ${c.expected_yield_tons_ha} t/ha expected<br>
          ${c.notes}
        </div>
      </div>`).join('');
    } catch {
        document.getElementById('crop-grid').innerHTML = '<div style="color:var(--gray-mid)">Failed to load</div>';
    }
}

async function loadMarket() {
    try {
        const r = await fetch(`${API}/api/v1/admin/reports/market-prices`);
        if (!r.ok) throw new Error();
        const data = await r.json();
        const grid = document.getElementById('market-grid');
        grid.innerHTML = data.prices.map(p => `
      <div class="market-card">
        <div class="market-name">${p.crop}</div>
        <div class="market-price">₹${p.price_per_quintal_inr}</div>
        <div class="market-sub">per quintal · ${p.market}</div>
        <div class="market-trend ${p.trend}">
          ${p.trend === 'UP' ? '↑ Rising' : p.trend === 'DOWN' ? '↓ Falling' : '→ Stable'}
        </div>
      </div>`).join('');
    } catch { }
}

async function sendOverride(action) {
    const zone = document.getElementById('override-zone').value;
    const dur = parseInt(document.getElementById('override-duration').value) || 15;
    const result = document.getElementById('override-result');
    result.textContent = 'Sending…';
    try {
        const r = await fetch(`${API}/api/v1/irrigation/manual-override`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ zone_id: zone, action, duration_minutes: dur }),
        });
        const data = await r.json();
        result.textContent = `✓ Override sent: ${action.toUpperCase()} for ${zone} (${dur} min)`;
        const now = new Date().toLocaleTimeString('en-IN', { hour12: false });
        overrideHistory.unshift(`<tr><td>${now}</td><td>${zone}</td><td><span class="badge ${action === 'on' ? 'badge-green' : 'badge-red'}">${action.toUpperCase()}</span></td><td>${dur} min</td></tr>`);
        document.getElementById('override-history').innerHTML = overrideHistory.slice(0, 10).join('');
    } catch (e) { result.textContent = 'Error: ' + e.message; }
}

async function loadCamera() {
    try {
        const r = await fetch(`${API}/api/v1/admin/camera/events`);
        if (!r.ok) throw new Error();
        const data = await r.json();
        const grid = document.getElementById('camera-grid');
        if (data.length === 0) {
            grid.innerHTML = '<div style="color:var(--gray-mid);padding:1rem">No camera events detected recently</div>';
            return;
        }
        grid.innerHTML = data.map((e, i) => {
            const ts = e.timestamp ? new Date(e.timestamp).toLocaleTimeString('en-IN', { hour12: false }) : '--';
            return `
        <div class="camera-card">
          <div class="camera-preview">
            <span class="camera-label">${e.node_id}</span>
            <span class="camera-live">● LIVE</span>
            <span class="camera-icon">📷</span>
          </div>
          <div class="camera-info">
            <div class="camera-event-type">${e.event}</div>
            <div class="camera-time">${e.zone_id} · ${ts}</div>
          </div>
        </div>`;
        }).join('');
    } catch {
        document.getElementById('camera-grid').innerHTML = '<div style="color:var(--gray-mid)">No events to display</div>';
    }
}

async function loadStatus() {
    try {
        const r = await fetch(`${API}/api/v1/admin/system/status`);
        if (!r.ok) throw new Error();
        const d = await r.json();
        document.getElementById('status-content').innerHTML = [
            `<strong>Status:</strong> <span style="color:var(--green-text)">${d.status.toUpperCase()}</span>`,
            `<strong>Sensors active (last 10 min):</strong> ${d.sensors_active_last_10min}`,
            `<strong>Open alerts:</strong> ${d.open_alerts}`,
            `<strong>Checked at:</strong> ${new Date(d.checked_at).toLocaleString('en-IN')}`,
            `<strong>API:</strong> ${API}`,
        ].join('<br>');
    } catch {
        document.getElementById('status-content').textContent = 'Unable to reach API — is the backend running?';
    }
}

const WS_URL = API.replace('http', 'ws') + '/ws/stream';
let ws;
function connectWS() {
    ws = new WebSocket(WS_URL);
    ws.onmessage = ({ data }) => {
        try {
            const msg = JSON.parse(data);
            if (msg.type === 'alert') {
                const page = document.getElementById('page-alerts');
                if (page.classList.contains('active')) loadAlerts();
            }
        } catch { }
    };
    ws.onclose = () => setTimeout(connectWS, 3000);
}

loadAlerts();
connectWS();
