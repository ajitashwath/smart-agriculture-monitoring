const API = window.location.hostname === 'localhost'
  ? 'http://localhost:8000'
  : `${window.location.protocol}//${window.location.host}`;
const WS_URL = API.replace('http', 'ws') + '/ws/stream';

const state = {
  sensors: {},
  decisions: [],
  pumps: {},
  alerts: [],
  weather: null,
  chartLabels: [],
  chartDatasets: {},
  MAX_CHART_POINTS: 30,
};

const ZONE_COLORS = ['#ffffff', '#c8c8c8', '#909090', '#585858'];

function updateClock() {
  const now = new Date();
  document.getElementById('live-clock').textContent =
    now.toLocaleTimeString('en-IN', { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

const chartCtx = document.getElementById('moisture-chart').getContext('2d');
const moistureChart = new Chart(chartCtx, {
  type: 'line',
  data: { labels: [], datasets: [] },
  options: {
    animation: { duration: 400 },
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        labels: { color: '#909090', font: { family: 'JetBrains Mono', size: 11 }, boxWidth: 12 }
      },
      tooltip: {
        backgroundColor: '#181818',
        borderColor: '#2a2a2a',
        borderWidth: 1,
        titleColor: '#f0f0f0',
        bodyColor: '#b0b0b0',
      }
    },
    scales: {
      x: {
        ticks: { color: '#606060', font: { size: 10, family: 'JetBrains Mono' }, maxTicksLimit: 8 },
        grid: { color: '#181818' },
      },
      y: {
        min: 0, max: 0.6,
        ticks: { color: '#606060', font: { size: 10 }, callback: v => v.toFixed(2) },
        grid: { color: '#1e1e1e' },
      }
    }
  }
});

function ensureDataset(zoneId, idx) {
  if (!state.chartDatasets[zoneId]) {
    state.chartDatasets[zoneId] = [];
    moistureChart.data.datasets.push({
      label: zoneId,
      data: state.chartDatasets[zoneId],
      borderColor: ZONE_COLORS[idx % ZONE_COLORS.length],
      borderWidth: 1.5,
      pointRadius: 2,
      tension: 0.4,
      fill: false,
    });
  }
}

function pushChartPoint(zoneId, moisture, idx) {
  ensureDataset(zoneId, idx);
  const ts = new Date().toLocaleTimeString('en-IN', { hour12: false });
  if (!state.chartLabels.includes(ts)) {
    state.chartLabels.push(ts);
    if (state.chartLabels.length > state.MAX_CHART_POINTS)
      state.chartLabels.shift();
    moistureChart.data.labels = state.chartLabels;
  }
  const ds = state.chartDatasets[zoneId];
  ds.push(moisture);
  if (ds.length > state.MAX_CHART_POINTS) ds.shift();
  moistureChart.update('none');
}

function moistureClass(m, threshold) {
  if (m < threshold * 0.75) return 'low';
  if (m < threshold) return 'mid';
  return 'ok';
}

function renderZoneSidebar() {
  const container = document.getElementById('zone-list');
  const nodes = Object.values(state.sensors);
  if (nodes.length === 0) {
    container.innerHTML = '<div class="empty-state" style="font-size:0.75rem">Waiting for zones…</div>';
    return;
  }
  container.innerHTML = nodes.map(r => {
    const threshold = 0.30;
    const pct = Math.min(100, Math.round(r.soil_moisture * 100 / 0.55));
    const cls = moistureClass(r.soil_moisture, threshold);
    const pumpOn = Object.values(state.pumps).some(p => p.zone_id === r.zone_id && p.state === 'ON');
    return `
      <div class="zone-card">
        <div class="zone-card-header">
          <span class="zone-name">${r.zone_id}</span>
          <span class="pump-badge ${pumpOn ? 'active' : ''}">${pumpOn ? '● irrigating' : '○ idle'}</span>
        </div>
        <div class="moisture-bar-wrap">
          <div class="moisture-label">
            <span>${r.node_id}</span>
            <span>${r.soil_moisture.toFixed(3)}</span>
          </div>
          <div class="moisture-bar">
            <div class="moisture-fill ${cls}" style="width:${pct}%"></div>
          </div>
        </div>
      </div>`;
  }).join('');
}

function renderSensorGrid() {
  const grid = document.getElementById('sensor-grid');
  const nodes = Object.values(state.sensors);
  if (nodes.length === 0) return;

  grid.innerHTML = nodes.map(r => {
    const alerts = [];
    if (r.pest_alert) alerts.push('<span class="alert-tag">⚠ PEST</span>');
    if (r.camera_event) alerts.push('<span class="camera-tag">📷 CAMERA</span>');
    const ts = r.timestamp ? new Date(r.timestamp).toLocaleTimeString('en-IN', { hour12: false }) : '--';
    return `
      <div class="sensor-tile" id="tile-${r.node_id}">
        <div class="sensor-tile-header">
          <div>
            <div class="sensor-id">${r.node_id}</div>
            <div class="sensor-zone">${r.zone_id}</div>
          </div>
          <div class="sensor-time">${ts}</div>
        </div>
        <div class="sensor-metrics">
          <div class="metric">
            <div class="metric-lbl">Moisture</div>
            <div class="metric-val">${r.soil_moisture.toFixed(3)}</div>
          </div>
          <div class="metric">
            <div class="metric-lbl">Temp</div>
            <div class="metric-val">${r.temperature_c.toFixed(1)}<span class="metric-unit">°C</span></div>
          </div>
          <div class="metric">
            <div class="metric-lbl">Humidity</div>
            <div class="metric-val">${r.humidity_pct.toFixed(0)}<span class="metric-unit">%</span></div>
          </div>
          <div class="metric">
            <div class="metric-lbl">Wind</div>
            <div class="metric-val">${r.wind_speed_mps.toFixed(1)}<span class="metric-unit">m/s</span></div>
          </div>
          <div class="metric">
            <div class="metric-lbl">Battery</div>
            <div class="metric-val">${r.battery_pct.toFixed(0)}<span class="metric-unit">%</span></div>
          </div>
          <div class="metric">
            <div class="metric-lbl">RSSI</div>
            <div class="metric-val">${r.signal_rssi}<span class="metric-unit">dBm</span></div>
          </div>
        </div>
        ${alerts.length ? '<div class="sensor-alerts">' + alerts.join('') + '</div>' : ''}
      </div>`;
  }).join('');
}

function updateStats() {
  const nodes = Object.values(state.sensors);
  document.getElementById('stat-nodes').textContent = nodes.length;
  if (nodes.length > 0) {
    const avg = nodes.reduce((a, n) => a + n.soil_moisture, 0) / nodes.length;
    document.getElementById('stat-moisture').textContent = avg.toFixed(3);
  }
  const activePumps = Object.values(state.pumps).filter(p => p.state === 'ON').length;
  document.getElementById('stat-pumps').textContent = activePumps;
  document.getElementById('stat-alerts').textContent = state.alerts.filter(a => !a.acknowledged).length;
}

function addDecision(data) {
  state.decisions.unshift(data);
  if (state.decisions.length > 50) state.decisions.pop();
  renderDecisions();
}

function renderDecisions() {
  const tbody = document.getElementById('decisions-tbody');
  document.getElementById('decision-count').textContent = `${state.decisions.length} decisions`;
  if (state.decisions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--gray-mid);padding:1.5rem">No decisions yet</td></tr>';
    return;
  }
  tbody.innerHTML = state.decisions.slice(0, 20).map(d => {
    const ts = d.started_at ? new Date(d.started_at).toLocaleTimeString('en-IN', { hour12: false }) : '--';
    const badge = d.event === 'started'
      ? '<span class="badge badge-green">IRRIGATE</span>'
      : '<span class="badge badge-gray">ENDED</span>';
    return `
      <tr>
        <td>${ts}</td>
        <td>${d.zone_id || '--'}</td>
        <td>${d.pump_id || '--'}</td>
        <td>${badge}</td>
        <td>${d.duration_seconds ? (d.duration_seconds / 60).toFixed(1) + 'm' : '--'}</td>
        <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${d.reason || d.event || '--'}</td>
      </tr>`;
  }).join('');
}

function renderPumpStatus() {
  const container = document.getElementById('pump-status-list');
  const pumps = Object.values(state.pumps);
  if (pumps.length === 0) {
    container.innerHTML = '<div class="empty-state">No pump data</div>';
    return;
  }
  container.innerHTML = pumps.map(p => `
    <div class="pump-row">
      <div>
        <div class="pump-name">${p.pump_id}</div>
        <div class="pump-runtime">${p.zone_id} · ${p.runtime_seconds.toFixed(0)}s</div>
      </div>
      <span class="pump-status-badge ${p.state === 'ON' ? 'on' : 'off'}">${p.state}</span>
    </div>`).join('');
}

function addAlert(data) {
  state.alerts.unshift(data);
  if (state.alerts.length > 30) state.alerts.pop();
  renderAlerts();
  updateStats();
}

function renderAlerts() {
  const container = document.getElementById('alert-list');
  if (state.alerts.length === 0) {
    container.innerHTML = '<div class="empty-state">No alerts</div>';
    return;
  }
  container.innerHTML = state.alerts.slice(0, 15).map(a => {
    const sev = (a.severity || 'INFO').toLowerCase();
    const cls = sev === 'critical' ? 'critical' : sev === 'warning' ? 'warning' : 'info';
    const ts = a.created_at ? new Date(a.created_at).toLocaleTimeString('en-IN', { hour12: false }) : '--';
    return `
      <div class="alert-item ${cls}">
        <div class="alert-type ${cls}">${a.alert_type || 'ALERT'}</div>
        <div class="alert-msg">${a.message || ''}</div>
        <div class="alert-ts">${ts}</div>
      </div>`;
  }).join('');
}

function renderWeather(w) {
  state.weather = w;
  document.getElementById('w-temp').textContent = w.temperature_c?.toFixed(1) || '--';
  document.getElementById('w-hum').textContent = w.humidity_pct?.toFixed(0) + '%' || '--';
  document.getElementById('w-rain').textContent = ((w.rain_probability || 0) * 100).toFixed(0) + '%';
  document.getElementById('w-wind').textContent = w.wind_speed_mps?.toFixed(1) || '--';
  document.getElementById('weather-detail').textContent =
    `${w.condition} · ${w.city} · ${w.source === 'mock' ? '(simulated)' : 'live'}`;
}

let ws, wsRetryDelay = 2000;

function connectWS() {
  ws = new WebSocket(WS_URL);
  const dot = document.getElementById('ws-dot');
  const label = document.getElementById('ws-status');

  ws.onopen = () => {
    dot.className = 'ws-dot connected';
    label.textContent = 'Live';
    wsRetryDelay = 2000;
    setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('ping'), 25000);
  };

  ws.onmessage = ({ data }) => {
    try {
      const msg = JSON.parse(data);
      handleMessage(msg);
    } catch (_) { }
  };

  ws.onerror = () => { dot.className = 'ws-dot error'; label.textContent = 'Error'; };
  ws.onclose = () => {
    dot.className = 'ws-dot';
    label.textContent = 'Reconnecting…';
    setTimeout(connectWS, wsRetryDelay);
    wsRetryDelay = Math.min(wsRetryDelay * 1.5, 30000);
  };
}

function handleMessage(msg) {
  if (msg.type === 'sensor_reading') {
    const r = msg.data;
    state.sensors[r.node_id] = r;
    const idx = Object.keys(state.sensors).indexOf(r.node_id);
    pushChartPoint(r.zone_id, r.soil_moisture, idx);
    document.getElementById('last-update').textContent =
      'Updated ' + new Date().toLocaleTimeString('en-IN', { hour12: false });
    renderSensorGrid();
    renderZoneSidebar();
    updateStats();
    const tile = document.getElementById(`tile-${r.node_id}`);
    if (tile) { tile.classList.add('updated'); setTimeout(() => tile.classList.remove('updated'), 1500); }
    if (r.pest_alert) addAlert({ alert_type: 'PEST', severity: 'WARNING', message: `Pest signal on ${r.node_id}`, created_at: r.timestamp });
    if (r.camera_event) addAlert({ alert_type: 'CAMERA', severity: 'INFO', message: `Motion detected on ${r.node_id}`, created_at: r.timestamp });
  }
  else if (msg.type === 'irrigation_event') {
    addDecision(msg.data);
    const d = msg.data;
    if (d.pump_id) {
      state.pumps[d.pump_id] = state.pumps[d.pump_id] || {};
      state.pumps[d.pump_id].pump_id = d.pump_id;
      state.pumps[d.pump_id].zone_id = d.zone_id;
      state.pumps[d.pump_id].state = d.event === 'started' ? 'ON' : 'OFF';
      state.pumps[d.pump_id].runtime_seconds = d.duration_seconds || 0;
      renderPumpStatus();
      updateStats();
    }
  }
  else if (msg.type === 'alert') {
    addAlert(msg.data);
  }
  else if (msg.type === 'manual_override') {
    addDecision({ event: 'manual_override', ...msg.data, reason: `Manual ${msg.data.action.toUpperCase()} for ${msg.data.duration_minutes}min` });
  }
}

async function fetchWeather() {
  try {
    const r = await fetch(`${API}/api/v1/weather`);
    if (r.ok) renderWeather(await r.json());
  } catch (_) { }
}

async function fetchLatestSensors() {
  try {
    const r = await fetch(`${API}/api/v1/sensors/latest`);
    if (r.ok) {
      const data = await r.json();
      data.forEach((s, i) => {
        state.sensors[s.node_id] = s;
        pushChartPoint(s.zone_id, s.soil_moisture, i);
      });
      renderSensorGrid(); renderZoneSidebar(); updateStats();
    }
  } catch (_) { }
}

async function fetchAlerts() {
  try {
    const r = await fetch(`${API}/api/v1/alerts/?unacknowledged_only=true&limit=20`);
    if (r.ok) {
      const data = await r.json();
      state.alerts = data;
      renderAlerts(); updateStats();
    }
  } catch (_) { }
}

(async () => {
  connectWS();
  await fetchLatestSensors();
  await fetchWeather();
  await fetchAlerts();
  setInterval(fetchWeather, 60000);
  setInterval(fetchAlerts, 15000);
})();
