/* ── Live marks total ─────────────────────────────────────────────────────── */
function updateTotal() {
  const ids = ['m1', 'm2', 'm3', 'm4', 'm5'];
  let total = 0;
  ids.forEach(id => {
    const v = parseFloat(document.getElementById(id).value);
    if (!isNaN(v) && v >= 0 && v <= 100) total += v;
  });
  document.getElementById('total-display').textContent = total;
  const pct = (total / 500 * 100).toFixed(2);
  document.getElementById('percent-display').textContent = pct + '%';
  document.getElementById('progress-fill').style.width = (total / 500 * 100) + '%';
}

/* ── Collect & validate form ─────────────────────────────────────────────── */
function collectForm() {
  const board    = document.getElementById('board').value;
  const category = document.getElementById('category').value;
  const division = document.getElementById('division').value;
  const pwd      = document.getElementById('pwd').value;
  const streamEl = document.querySelector('input[name="stream"]:checked');

  const ids  = ['m1', 'm2', 'm3', 'm4', 'm5'];
  const marks = [];
  let marksValid = true;

  ids.forEach(id => {
    const v = parseFloat(document.getElementById(id).value);
    if (isNaN(v) || v < 0 || v > 100) { marksValid = false; }
    else marks.push(v);
  });

  if (!board || !category || !division || !streamEl || !marksValid || marks.length !== 5) {
    return null;
  }

  return { board, category, division, pwd, stream: streamEl.value, marks };
}

/* ── Main predict function ───────────────────────────────────────────────── */
async function predict() {
  const payload = collectForm();
  const errEl   = document.getElementById('marks-error');
  const btn     = document.getElementById('predict-btn');

  if (!payload) {
    errEl.style.display = 'block';
    alert('⚠️ Please complete all required fields:\n• SSC Board\n• Category\n• Division\n• All 5 subject marks (0–100)\n• Preferred Stream');
    return;
  }

  errEl.style.display = 'none';

  // Loading state
  btn.disabled    = true;
  btn.textContent = '⏳ Predicting…';

  try {
    const res  = await fetch('/predict', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    const data = await res.json();

    if (!res.ok) {
      alert('Error: ' + (data.error || 'Something went wrong.'));
      return;
    }

    renderResults(data);

  } catch (err) {
    console.error(err);
    alert('Network error. Please try again.');
  } finally {
    btn.disabled    = false;
    btn.textContent = '🔍 Predict My FYJC Rank';
  }
}

/* ── Render results ──────────────────────────────────────────────────────── */
const BOARD_NAMES    = { maharashtra: 'SSC Maharashtra', cbse: 'CBSE', icse: 'ICSE', other: 'Other Board' };
const CAT_NAMES      = { open: 'Open/General', obc: 'OBC', sc: 'SC', st: 'ST', nt: 'NT', vj: 'VJ/DT', sbc: 'SBC', ews: 'EWS' };
const STREAM_NAMES   = { science: 'Science', commerce: 'Commerce', arts: 'Arts/Humanities' };
const CHANCE_LABELS  = { high: '✓ High', moderate: '~ Moderate', borderline: '~ Borderline', low: '✗ Low' };

function fmt(n) {
  return Number(n).toLocaleString('en-IN');
}

function renderResults(d) {
  // Rank hero
  document.getElementById('rank-number').textContent    = fmt(d.rank_low);
  document.getElementById('rank-suffix-text').textContent = `to #${fmt(d.rank_high)}`;
  document.getElementById('result-sub-text').textContent  =
    `Among ~${fmt(d.total_applicants)} applicants in ${capitalize(d.division)} Division`;

  // Pills
  document.getElementById('result-pills').innerHTML = `
    <div class="result-pill"><span class="dot" style="background:#FF6B00"></span>${BOARD_NAMES[d.board] || d.board}</div>
    <div class="result-pill"><span class="dot" style="background:#4CAF50"></span>${CAT_NAMES[d.category] || d.category}</div>
    <div class="result-pill"><span class="dot" style="background:#FFC107"></span>${STREAM_NAMES[d.stream] || d.stream}</div>
    <div class="result-pill"><span class="dot" style="background:#4DB6AC"></span>${d.percentage}%</div>
  `;

  // Stats
  document.getElementById('stat-percentile').textContent = d.percentile + '%';
  document.getElementById('stat-colleges').textContent   = d.eligible_colleges;
  const diff = d.marks_vs_cutoff;
  document.getElementById('stat-cutoff').textContent     = (diff >= 0 ? '+' : '') + diff + '%';

  // College table
  const tbody = document.getElementById('colleges-tbody');
  tbody.innerHTML = '';
  d.colleges.forEach(c => {
    const chance  = c.chance;
    const label   = CHANCE_LABELS[chance] || chance;
    tbody.innerHTML += `
      <tr>
        <td>
          <div class="college-name">${escHtml(c.name)}</div>
          <div class="college-loc">📍 ${escHtml(c.loc)}</div>
        </td>
        <td><strong>${c.cutoff}%</strong></td>
        <td><span class="chance-badge chance-${chance}">${label}</span></td>
      </tr>`;
  });

  // Show section
  const section = document.getElementById('result-section');
  section.style.display = 'block';
  setTimeout(() => section.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
}

/* ── Reset ───────────────────────────────────────────────────────────────── */
function resetForm() {
  document.getElementById('result-section').style.display = 'none';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ── Utilities ───────────────────────────────────────────────────────────── */
function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : '';
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
