let currentDataset = null;
let moistureChart = null;

const STATUS_COLORS = {
  critical_low: '#DC2626',
  low: '#F97316',
  moderate: '#EAB308',
  optimal: '#22C55E',
  high: '#3B82F6',
  saturated: '#06B6D4',
};

const SENSOR_NAMES = {
  moisture0: 'Sensor 0 · Top',
  moisture1: 'Sensor 1 · Upper Mid',
  moisture2: 'Sensor 2 · Mid',
  moisture3: 'Sensor 3 · Lower Mid',
  moisture4: 'Sensor 4 · Drainage',
};

async function selectDataset(key, btnEl) {
  currentDataset = key;
  document.querySelectorAll('.ds-btn').forEach(b => b.classList.remove('active'));
  btnEl.classList.add('active');
  document.getElementById('dashboard').style.display = 'block';
  document.getElementById('liveLabel').textContent = `Live: ${btnEl.querySelector('.ds-name').textContent}`;
  document.querySelector('.live-dot').classList.add('active');

  await loadSummary(key);
  await loadChart(key);
  document.getElementById('dashboard').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function loadSummary(key) {
  const res = await fetch(`/api/summary/${key}`);
  const data = await res.json();
  if (data.error) { showToast(data.error); return; }

  document.getElementById('statRecords').textContent = data.total_records.toLocaleString();
  document.getElementById('statRange').textContent = `${data.date_range.start} → ${data.date_range.end}`;
  document.getElementById('statIrrigation').textContent = data.irrigation_events;
  document.getElementById('statAvg').textContent = (data.averages.moisture0 * 100).toFixed(1) + '%';

  renderGauges(data.latest_reading);
}

function renderGauges(latest) {
  const grid = document.getElementById('gaugesGrid');
  grid.innerHTML = Object.entries(latest).map(([sensor, info]) => {
    const color = STATUS_COLORS[info.status];
    const circumference = 2 * Math.PI * 38;
    const offset = circumference - (info.percent / 100) * circumference;
    return `
      <div class="gauge-card ${info.status}">
        <div class="gauge-sensor-name">${SENSOR_NAMES[sensor] || sensor}</div>
        <div class="gauge-ring">
          <svg width="90" height="90" viewBox="0 0 90 90">
            <circle class="bg" cx="45" cy="45" r="38" stroke-width="8" fill="none"/>
            <circle cx="45" cy="45" r="38" stroke-width="8" fill="none"
              stroke="${color}" stroke-linecap="round"
              stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"/>
          </svg>
          <div class="gauge-pct">${info.percent}%</div>
        </div>
        <div class="gauge-status ${info.status}">${info.label}</div>
      </div>
    `;
  }).join('');
}

async function loadChart(key) {
  const res = await fetch(`/api/chart/${key}`);
  const data = await res.json();
  if (data.error) { showToast(data.error); return; }

  const ctx = document.getElementById('moistureChart').getContext('2d');
  const colors = ['#2D6A4F', '#52B788', '#F97316', '#3B82F6', '#EAB308'];

  const datasets = Object.entries(data.sensors).map(([sensor, values], i) => ({
    label: SENSOR_NAMES[sensor] || sensor,
    data: values,
    borderColor: colors[i % colors.length],
    backgroundColor: colors[i % colors.length] + '20',
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.3,
  }));

  if (moistureChart) moistureChart.destroy();
  moistureChart = new Chart(ctx, {
    type: 'line',
    data: { labels: data.labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        y: { min: 0, max: 100, title: { display: true, text: 'Moisture %' } },
        x: { ticks: { maxTicksLimit: 12 } }
      },
      plugins: { legend: { position: 'bottom' } }
    }
  });
}

function statusForValue(v) {
  if (v === '' || isNaN(v)) return '';
  v = parseFloat(v);
  if (v < 0.15) return { label: 'Critical', color: '#DC2626' };
  if (v < 0.30) return { label: 'Low', color: '#F97316' };
  if (v < 0.50) return { label: 'Moderate', color: '#EAB308' };
  if (v <= 0.80) return { label: 'Optimal', color: '#22C55E' };
  if (v <= 0.90) return { label: 'High', color: '#3B82F6' };
  return { label: 'Saturated', color: '#06B6D4' };
}

['f0','f1','f2','f3','f4'].forEach((id, i) => {
  document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById(id);
    const hint = document.getElementById('h' + i);
    input.addEventListener('input', () => {
      const s = statusForValue(input.value);
      if (s) {
        hint.textContent = s.label;
        hint.style.color = s.color;
        hint.style.fontWeight = '700';
      } else {
        hint.textContent = '';
      }
    });
  });
});

async function submitReading() {
  if (!currentDataset) { showToast('Please select a plant dataset first.'); return; }

  const vals = {};
  for (let i = 0; i < 5; i++) {
    const raw = document.getElementById(`f${i}`).value;
    if (raw === '') { showToast(`Please fill in Sensor ${i}.`); return; }
    vals[`moisture${i}`] = parseFloat(raw);
  }

  const res = await fetch('/api/feed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset: currentDataset, ...vals })
  });
  const data = await res.json();
  const resultBox = document.getElementById('feedResult');
  resultBox.style.display = 'block';

  if (data.error) {
    resultBox.className = 'feed-result error';
    resultBox.textContent = '❌ ' + data.error;
    showToast(data.error);
    return;
  }

  resultBox.className = 'feed-result';
  resultBox.innerHTML = `✅ Reading saved! Total records: <strong>${data.total_records}</strong><br/>` +
    Object.entries(data.statuses).map(([s, info]) =>
      `${SENSOR_NAMES[s]}: <strong>${info.percent}%</strong> — ${info.label}`
    ).join('<br/>');

  showToast('Reading saved successfully 🌱');
  loadSummary(currentDataset);
  loadChart(currentDataset);
}

async function logIrrigation() {
  if (!currentDataset) { showToast('Please select a plant dataset first.'); return; }
  const res = await fetch('/api/irrigate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset: currentDataset })
  });
  const data = await res.json();
  showToast(data.message || 'Done');
  loadSummary(currentDataset);
}

function clearForm() {
  ['f0','f1','f2','f3','f4'].forEach((id, i) => {
    document.getElementById(id).value = '';
    document.getElementById('h' + i).textContent = '';
  });
  document.getElementById('feedResult').style.display = 'none';
}

function showToast(msg) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
}
