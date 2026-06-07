let telaoState = null;
const TV_REFRESH_MS = 60000;
const TABLES_MS = 120000;
const ADS_MS = 20000;
const RESULT_MS = 20000;
let currentMode = 'tables';
let sponsorShape = 'rect';
let cycleTimer = null;

function normalizeChaveTv(value) {
  return String(value || 'A').trim().toUpperCase() || 'A';
}

function gatherStandingsTables(state) {
  const cards = [];
  for (let d = 1; d <= (state?.config?.division_count || 0); d++) {
    const chaves = state.standings[String(d)] || {};
    const chaveNames = Object.keys(chaves).sort();
    const showChave = chaveNames.length > 1;
    chaveNames.forEach(ch => cards.push({ division: d, chave: ch, showChave, rows: chaves[ch] || [] }));
  }
  return cards.filter(c => c.rows.length);
}

function sponsorImages(shape) {
  const field = shape === 'square' ? 'square_image_url' : 'rect_image_url';
  return (telaoState?.sponsors || [])
    .filter(s => s[field])
    .map(s => ({name: s.name, url: s[field]}));
}

function latestResultMatch() {
  if (telaoState?.latest_result) return telaoState.latest_result;
  const finished = (telaoState?.matches || []).filter(m => m.is_finished);
  return finished.sort((a,b) => String(b.result_saved_at || b.updated_at || b.created_at || '').localeCompare(String(a.result_saved_at || a.updated_at || a.created_at || '')))[0] || null;
}

function bestGrid(count, width, height, baseRatio = 0.92) {
  const gap = 18;
  const header = 110;
  let best = { cols: 1, rows: count || 1, score: -1, cardW: width, cardH: height - header };
  for (let cols = 1; cols <= Math.max(1, count); cols++) {
    const rows = Math.ceil(count / cols);
    const availW = width - gap * (cols + 1);
    const availH = height - header - gap * (rows + 1);
    const cellW = availW / cols;
    const cellH = availH / rows;
    const useW = Math.min(cellW, cellH * baseRatio);
    const useH = useW / baseRatio;
    const score = useW * useH;
    if (useW > 0 && useH > 0 && score > best.score) best = { cols, rows, score, cardW: useW, cardH: useH };
  }
  return best;
}

function renderTelaoTable(rows) {
  return `<div class="telao-table-wrap"><table class="telao-table"><thead><tr>
    <th>#</th><th>Jogador</th><th>Pts</th><th>Vit</th><th>Jgs</th><th>B+</th><th>B-</th><th>Saldo</th><th>Situação</th>
  </tr></thead><tbody>
    ${rows.map((row, idx) => {
      const cls = row.rank_status || '';
      const st = row.rank_status === 'promotion' ? 'Classificado' : row.rank_status === 'relegation' ? 'Rebaixado' : '—';
      return `<tr class="${escapeHtml(cls)}"><td>${idx+1}</td><td>${escapeHtml(row.name)}</td><td><strong>${row.points}</strong></td><td>${row.wins}</td><td>${row.played}</td><td>${row.balls_for}</td><td>${row.balls_against}</td><td><strong>${row.balls_balance}</strong></td><td>${st}</td></tr>`;
    }).join('')}
  </tbody></table></div>`;
}

function renderTables() {
  currentMode = 'tables';
  const grid = document.getElementById('telao-grid');
  grid.className = 'telao-grid';
  const cards = gatherStandingsTables(telaoState);
  if (!cards.length) {
    grid.innerHTML = `<section class="card empty"><h2>Nenhum torneio criado ainda</h2><p>Aguardando cadastros e resultados.</p></section>`;
    return;
  }
  const cfg = bestGrid(cards.length, window.innerWidth, window.innerHeight, 0.92);
  grid.style.gridTemplateColumns = `repeat(${cfg.cols}, 1fr)`;
  document.documentElement.style.setProperty('--telao-card-height', `${Math.floor(cfg.cardH)}px`);
  grid.innerHTML = cards.map(card => `
    <section class="card standings-card telao-card">
      <div class="section-title telao-title">
        <h2>${divisionName(card.division)}${card.showChave ? ` · Chave ${escapeHtml(normalizeChaveTv(card.chave))}` : ''}</h2>
        <span>${card.rows.length} jogadores</span>
      </div>
      ${renderTelaoTable(card.rows)}
    </section>
  `).join('');
}

function renderSponsors() {
  currentMode = 'sponsors';
  const grid = document.getElementById('telao-grid');
  const images = sponsorImages(sponsorShape);
  const ratio = sponsorShape === 'square' ? 1 : 3;
  grid.className = `telao-grid sponsor-screen ${sponsorShape === 'square' ? 'square-sponsors' : 'rect-sponsors'}`;
  if (!images.length) {
    renderLatestResultOrTables();
    return;
  }
  const cfg = bestGrid(images.length, window.innerWidth, window.innerHeight, ratio);
  grid.style.gridTemplateColumns = `repeat(${cfg.cols}, 1fr)`;
  document.documentElement.style.setProperty('--telao-card-height', `${Math.floor(cfg.cardH)}px`);
  grid.innerHTML = images.map(item => `
    <section class="sponsor-tv-card">
      <img src="${escapeHtml(item.url)}" alt="${escapeHtml(item.name)}">
      <strong>${escapeHtml(item.name)}</strong>
    </section>
  `).join('');
  sponsorShape = sponsorShape === 'rect' ? 'square' : 'rect';
}

function playerByIdTv(id) {
  return (telaoState?.players || []).find(p => p.player_id === id) || null;
}

function renderLatestResultOrTables() {
  const match = latestResultMatch();
  if (!match) {
    renderTables();
    return false;
  }
  currentMode = 'result';
  const grid = document.getElementById('telao-grid');
  grid.className = 'telao-grid result-screen';
  grid.style.gridTemplateColumns = '1fr';
  document.documentElement.style.setProperty('--telao-card-height', `${window.innerHeight - 140}px`);
  const p1 = playerByIdTv(match.player1_id) || {name: match.player1_name};
  const p2 = playerByIdTv(match.player2_id) || {name: match.player2_name};
  grid.innerHTML = `
    <section class="latest-result-card">
      <div class="result-player">
        <img src="${escapeHtml(p1.photo_url || '/img/entre-folhas-logo-transparent.png')}" alt="${escapeHtml(p1.name)}">
        <div class="player-score ${match.winner_id === match.player1_id ? 'winner-score' : ''}">${match.balls_p1 || 0}</div>
        <h2>${escapeHtml(p1.name || match.player1_name)}</h2>
        <p>${escapeHtml(p1.short_message || '')}</p>
      </div>
      <div class="result-center">
        <div class="result-kicker">Último resultado</div>
        <div class="big-versus">X</div>
        <div class="result-meta">${fmtDate(match.date)} · ${escapeHtml(match.time || '')} · ${escapeHtml(match.place_name || '')}</div>
      </div>
      <div class="result-player">
        <img src="${escapeHtml(p2.photo_url || '/img/entre-folhas-logo-transparent.png')}" alt="${escapeHtml(p2.name)}">
        <div class="player-score ${match.winner_id === match.player2_id ? 'winner-score' : ''}">${match.balls_p2 || 0}</div>
        <h2>${escapeHtml(p2.name || match.player2_name)}</h2>
        <p>${escapeHtml(p2.short_message || '')}</p>
      </div>
    </section>
  `;
  return true;
}

function renderCurrentMode() {
  if (currentMode === 'sponsors') renderSponsors();
  else if (currentMode === 'result') renderLatestResultOrTables();
  else renderTables();
}

function scheduleNext() {
  clearTimeout(cycleTimer);
  if (currentMode === 'tables') {
    cycleTimer = setTimeout(() => {
      if (sponsorImages('rect').length || sponsorImages('square').length) {
        renderSponsors();
        scheduleNext();
      } else if (renderLatestResultOrTables()) {
        scheduleNext();
      } else {
        renderTables();
        scheduleNext();
      }
    }, TABLES_MS);
  } else if (currentMode === 'sponsors') {
    cycleTimer = setTimeout(() => {
      renderLatestResultOrTables();
      scheduleNext();
    }, ADS_MS);
  } else {
    cycleTimer = setTimeout(() => {
      renderTables();
      scheduleNext();
    }, RESULT_MS);
  }
}

async function loadTelaoState() {
  try {
    telaoState = await apiFetch('/state');
    window.CURRENT_STATE_PLAYERS = telaoState.players || [];
    renderCurrentMode();
    const stamp = new Date();
    document.getElementById('telao-last-update').textContent = `Atualizado às ${stamp.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'})}`;
  } catch (err) {
    document.getElementById('telao-grid').innerHTML = `<section class="card empty">${escapeHtml(err.message || 'Falha ao carregar o telão.')}</section>`;
  }
}

window.addEventListener('resize', () => { if (telaoState) renderCurrentMode(); });
window.addEventListener('DOMContentLoaded', async () => {
  currentMode = 'tables';
  await loadTelaoState();
  scheduleNext();
  setInterval(loadTelaoState, TV_REFRESH_MS);
});
