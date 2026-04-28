const API_BASE_URL = (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL || '').replace(/\/$/, '');

function getToken() {
  return localStorage.getItem('sinuca_admin_token') || '';
}

function setToken(token) {
  localStorage.setItem('sinuca_admin_token', token);
}

function clearToken() {
  localStorage.removeItem('sinuca_admin_token');
}

async function apiFetch(path, options = {}) {
  if (!API_BASE_URL) {
    throw new Error('API_BASE_URL não configurada. No deploy, o GitHub Actions cria o frontend/config.js automaticamente.');
  }
  const headers = Object.assign({'Content-Type': 'application/json'}, options.headers || {});
  if (options.admin) {
    headers.Authorization = `Bearer ${getToken()}`;
  }
  const resp = await fetch(`${API_BASE_URL}${path}`, Object.assign({}, options, {headers}));
  const text = await resp.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch (_) { data = {}; }
  if (!resp.ok) {
    throw new Error(data.error || `Erro ${resp.status}`);
  }
  return data;
}

function fmtDate(value) {
  if (!value) return 'Sem data';
  const [y, m, d] = value.split('-');
  return `${d}/${m}/${y}`;
}

function divisionName(number) {
  return `${number}ª Divisão`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function groupBy(items, keyFn) {
  return items.reduce((acc, item) => {
    const key = keyFn(item);
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});
}

function matchResultText(match) {
  if (!match.is_finished) return '<span class="badge pending">Pendente</span>';
  const p1Winner = match.winner_id === match.player1_id;
  const p2Winner = match.winner_id === match.player2_id;
  return `<span class="score"><span class="${p1Winner ? 'winner' : ''}">${escapeHtml(match.player1_name)} ${match.balls_p1 || 0}</span> x <span class="${p2Winner ? 'winner' : ''}">${match.balls_p2 || 0} ${escapeHtml(match.player2_name)}</span></span>`;
}

function getFilteredMatches(matches, filters) {
  return matches.filter(match => {
    if (filters.date && match.date !== filters.date) return false;
    if (filters.place && match.place_id !== filters.place) return false;
    if (filters.player && match.player1_id !== filters.player && match.player2_id !== filters.player) return false;
    if (filters.division && String(match.division) !== String(filters.division)) return false;
    return true;
  });
}

function fillSelect(select, items, valueKey, labelKey, firstLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${escapeHtml(firstLabel)}</option>`;
  items.forEach(item => {
    const value = item[valueKey];
    const label = typeof labelKey === 'function' ? labelKey(item) : item[labelKey];
    select.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`);
  });
  if ([...select.options].some(opt => opt.value === current)) select.value = current;
}

function fillDivisionSelect(select, count, firstLabel = null) {
  select.innerHTML = firstLabel === null ? '' : `<option value="">${escapeHtml(firstLabel)}</option>`;
  for (let i = 1; i <= count; i++) {
    select.insertAdjacentHTML('beforeend', `<option value="${i}">${i}ª Divisão</option>`);
  }
}

function renderMatches(container, matches) {
  if (!matches.length) {
    container.innerHTML = '<div class="empty">Nenhuma partida encontrada.</div>';
    return;
  }
  const byDate = groupBy(matches, m => m.date || 'Sem data');
  const html = Object.keys(byDate).sort().map(date => {
    const dayMatches = byDate[date];
    const byPlace = groupBy(dayMatches, m => m.place_name || 'Sem local');
    const placesHtml = Object.keys(byPlace).sort().map(place => {
      const cards = byPlace[place].sort((a,b) => String(a.time).localeCompare(String(b.time))).map(match => `
        <div class="match-card">
          <div><span class="badge">${escapeHtml(match.time || '--:--')}</span><div class="match-meta">até ${escapeHtml(match.end_time || '--:--')}</div></div>
          <div>
            <strong>${escapeHtml(match.player1_name)} x ${escapeHtml(match.player2_name)}</strong>
            <div class="match-meta">${divisionName(match.division)} · ${escapeHtml(place)}</div>
          </div>
          <div>${matchResultText(match)}</div>
        </div>
      `).join('');
      return `<div class="match-group"><h3>${escapeHtml(place)}</h3>${cards}</div>`;
    }).join('');
    return `<div class="match-group"><h2>${fmtDate(date)}</h2>${placesHtml}</div>`;
  }).join('');
  container.innerHTML = html;
}
