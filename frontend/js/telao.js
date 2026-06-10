let telaoState = null;

const TV_REFRESH_MS = 60000;
const DEFAULT_TV_CONFIG = {
  table_seconds: 60,
  sponsor_seconds: 30,
  match_seconds: 5,
  filters: {},
};
const RADIO_STATIONS = [
  {id: 'groove-salad', name: 'SomaFM Groove Salad', url: 'https://ice1.somafm.com/groovesalad-128-mp3'},
  {id: 'secret-agent', name: 'SomaFM Secret Agent', url: 'https://ice1.somafm.com/secretagent-128-mp3'},
  {id: 'drone-zone', name: 'SomaFM Drone Zone', url: 'https://ice1.somafm.com/dronezone-128-mp3'},
];

let currentMode = 'tables';
let currentMatchIndex = 0;
let sponsorPass = 0;
let activeSponsorShape = 'rect';
let cycleTimer = null;
let countdownTimer = null;
let phaseEndsAt = 0;
let telaoZoom = Number(localStorage.getItem('sinuca_telao_zoom') || 1);

function normalizeChaveTv(value) {
  return String(value || 'A').trim().toUpperCase() || 'A';
}

function tvConfig() {
  const saved = telaoState?.config?.tv_config || {};
  return {
    table_seconds: Math.max(1, Number(saved.table_seconds || DEFAULT_TV_CONFIG.table_seconds)),
    sponsor_seconds: Math.max(1, Number(saved.sponsor_seconds || DEFAULT_TV_CONFIG.sponsor_seconds)),
    match_seconds: Math.max(1, Number(saved.match_seconds || DEFAULT_TV_CONFIG.match_seconds)),
    filters: saved.filters || {},
  };
}

function cycleMatches() {
  return telaoState?.tv_matches || [];
}

function gatherStandingsTables(state) {
  const cards = [];
  for (let division = 1; division <= (state?.config?.division_count || 0); division++) {
    const chaves = state.standings[String(division)] || {};
    const chaveNames = Object.keys(chaves).sort();
    const showChave = chaveNames.length > 1;
    chaveNames.forEach(chave => cards.push({
      division,
      chave,
      showChave,
      rows: chaves[chave] || [],
    }));
  }
  return cards.filter(card => card.rows.length);
}

function sponsorImages(shape) {
  const field = shape === 'square' ? 'square_image_url' : 'rect_image_url';
  return (telaoState?.sponsors || [])
    .filter(sponsor => sponsor[field])
    .map(sponsor => ({name: sponsor.name, url: sponsor[field]}));
}

function bestGrid(count, width, height, baseRatio = 0.92) {
  const gap = 18;
  const header = document.querySelector('.telao-header')?.getBoundingClientRect().height || 100;
  let best = {cols: 1, rows: count || 1, score: -1, cardW: width, cardH: height - header};
  for (let cols = 1; cols <= Math.max(1, count); cols++) {
    const rows = Math.ceil(count / cols);
    const availW = width - gap * (cols + 1);
    const availH = height - header - gap * (rows + 1);
    const cellW = availW / cols;
    const cellH = availH / rows;
    const useW = Math.min(cellW, cellH * baseRatio);
    const useH = useW / baseRatio;
    const score = useW * useH;
    if (useW > 0 && useH > 0 && score > best.score) {
      best = {cols, rows, score, cardW: useW, cardH: useH};
    }
  }
  return best;
}

function renderTelaoTable(rows) {
  return `<div class="telao-table-wrap"><table class="telao-table"><thead><tr>
    <th>#</th><th>Jogador</th><th>Pts</th><th>Vit</th><th>Jgs</th><th>B+</th><th>B-</th><th>Saldo</th><th>Situação</th>
  </tr></thead><tbody>
    ${rows.map((row, index) => {
      const status = row.rank_status === 'promotion'
        ? 'Classificado'
        : row.rank_status === 'relegation' ? 'Rebaixado' : '—';
      return `<tr class="${escapeHtml(row.rank_status || '')}">
        <td>${index + 1}</td>
        <td>${escapeHtml(row.name)}</td>
        <td><strong>${row.points}</strong></td>
        <td>${row.wins}</td>
        <td>${row.played}</td>
        <td>${row.balls_for}</td>
        <td>${row.balls_against}</td>
        <td><strong>${row.balls_balance}</strong></td>
        <td>${status}</td>
      </tr>`;
    }).join('')}
  </tbody></table></div>`;
}

function renderTables() {
  currentMode = 'tables';
  const grid = document.getElementById('telao-grid');
  grid.className = 'telao-grid';
  const cards = gatherStandingsTables(telaoState);
  if (!cards.length) {
    grid.innerHTML = '<section class="card empty"><h2>Nenhum torneio criado ainda</h2><p>Aguardando cadastros e resultados.</p></section>';
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

function chooseSponsorShape() {
  const preferred = sponsorPass % 2 === 0 ? 'rect' : 'square';
  const alternate = preferred === 'rect' ? 'square' : 'rect';
  activeSponsorShape = sponsorImages(preferred).length ? preferred : alternate;
  sponsorPass += 1;
}

function renderSponsors() {
  currentMode = 'sponsors';
  const grid = document.getElementById('telao-grid');
  const images = sponsorImages(activeSponsorShape);
  const ratio = activeSponsorShape === 'square' ? 1 : 3;
  grid.className = `telao-grid sponsor-screen ${activeSponsorShape === 'square' ? 'square-sponsors' : 'rect-sponsors'}`;
  if (!images.length) {
    grid.innerHTML = '<section class="card empty">Nenhum patrocinador com imagem para este formato.</section>';
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
}

function playerByIdTv(id) {
  return (telaoState?.players || []).find(player => player.player_id === id) || null;
}

function renderMatch(match) {
  currentMode = 'matches';
  const grid = document.getElementById('telao-grid');
  grid.className = `telao-grid result-screen ${match.is_finished ? 'finished-match' : 'pending-match'}`;
  grid.style.gridTemplateColumns = '1fr';
  const headerHeight = document.querySelector('.telao-header')?.getBoundingClientRect().height || 100;
  document.documentElement.style.setProperty('--telao-card-height', `${Math.max(220, window.innerHeight - headerHeight - 18)}px`);
  const player1 = playerByIdTv(match.player1_id) || {name: match.player1_name};
  const player2 = playerByIdTv(match.player2_id) || {name: match.player2_name};
  const score1 = match.is_finished ? Number(match.balls_p1 || 0) : '–';
  const score2 = match.is_finished ? Number(match.balls_p2 || 0) : '–';
  const position = Math.min(currentMatchIndex + 1, cycleMatches().length);
  grid.innerHTML = `
    <section class="latest-result-card">
      <div class="result-player">
        <div class="result-player-photo">
          <img src="${escapeHtml(player1.photo_url || '/img/entre-folhas-logo-transparent.png')}" alt="${escapeHtml(player1.name)}">
          <div class="player-score ${match.winner_id === match.player1_id ? 'winner-score' : ''}">${score1}</div>
        </div>
        <h2>${escapeHtml(player1.name || match.player1_name)}</h2>
        <p>${escapeHtml(player1.short_message || '')}</p>
      </div>
      <div class="result-center">
        <div class="result-kicker">${match.is_finished ? 'Partida finalizada' : 'Partida pendente'}</div>
        <div class="big-versus">X</div>
        <div class="result-meta">${fmtDate(match.date)} · ${escapeHtml(match.time || '')} · ${escapeHtml(match.place_name || '')}</div>
        <div class="result-position">${position} de ${cycleMatches().length}</div>
      </div>
      <div class="result-player">
        <div class="result-player-photo">
          <img src="${escapeHtml(player2.photo_url || '/img/entre-folhas-logo-transparent.png')}" alt="${escapeHtml(player2.name)}">
          <div class="player-score ${match.winner_id === match.player2_id ? 'winner-score' : ''}">${score2}</div>
        </div>
        <h2>${escapeHtml(player2.name || match.player2_name)}</h2>
        <p>${escapeHtml(player2.short_message || '')}</p>
      </div>
    </section>
  `;
}

function renderCurrentMode() {
  if (!telaoState) return;
  if (currentMode === 'sponsors') {
    renderSponsors();
  } else if (currentMode === 'matches') {
    const matches = cycleMatches();
    if (matches.length) {
      currentMatchIndex = Math.min(currentMatchIndex, matches.length - 1);
      renderMatch(matches[currentMatchIndex]);
    } else {
      renderTables();
    }
  } else {
    renderTables();
  }
}

function updateCountdown() {
  const element = document.getElementById('telao-countdown');
  if (!phaseEndsAt) {
    element.textContent = 'Preparando próxima visualização';
    return;
  }
  const seconds = Math.max(0, Math.ceil((phaseEndsAt - Date.now()) / 1000));
  element.textContent = `Próxima visualização em ${seconds}s`;
}

function schedulePhase(seconds, callback) {
  clearTimeout(cycleTimer);
  clearInterval(countdownTimer);
  phaseEndsAt = Date.now() + seconds * 1000;
  updateCountdown();
  countdownTimer = setInterval(updateCountdown, 250);
  cycleTimer = setTimeout(() => {
    clearInterval(countdownTimer);
    phaseEndsAt = 0;
    callback();
  }, seconds * 1000);
}

function startTablesPhase() {
  renderTables();
  schedulePhase(tvConfig().table_seconds, startSponsorsPhase);
}

function startSponsorsPhase() {
  if (!sponsorImages('rect').length && !sponsorImages('square').length) {
    startMatchesPhase();
    return;
  }
  chooseSponsorShape();
  renderSponsors();
  schedulePhase(tvConfig().sponsor_seconds, startMatchesPhase);
}

function startMatchesPhase() {
  const matches = cycleMatches();
  if (!matches.length) {
    startTablesPhase();
    return;
  }
  currentMatchIndex = 0;
  showCurrentMatch();
}

function showCurrentMatch() {
  const matches = cycleMatches();
  if (!matches.length || currentMatchIndex >= matches.length) {
    startTablesPhase();
    return;
  }
  renderMatch(matches[currentMatchIndex]);
  schedulePhase(tvConfig().match_seconds, () => {
    currentMatchIndex += 1;
    showCurrentMatch();
  });
}

function renderRadioMenu() {
  const selected = localStorage.getItem('sinuca_telao_radio') || RADIO_STATIONS[0].id;
  const menu = document.getElementById('telao-radio-menu');
  menu.innerHTML = RADIO_STATIONS.map(station => `
    <button type="button" role="menuitemradio" aria-checked="${station.id === selected ? 'true' : 'false'}" data-radio-id="${station.id}">
      ${escapeHtml(station.name)}
    </button>
  `).join('');
  menu.querySelectorAll('[data-radio-id]').forEach(button => {
    button.addEventListener('click', () => {
      selectRadio(button.dataset.radioId, true);
      setRadioMenuOpen(false);
    });
  });
}

function selectedStation() {
  const selected = localStorage.getItem('sinuca_telao_radio') || RADIO_STATIONS[0].id;
  return RADIO_STATIONS.find(station => station.id === selected) || RADIO_STATIONS[0];
}

function updateRadioButton() {
  const audio = document.getElementById('telao-radio-audio');
  const button = document.getElementById('telao-radio-toggle');
  const playing = !audio.paused && !audio.muted;
  button.textContent = playing ? '🔊' : '🔇';
  button.title = playing ? 'Desligar rádio' : 'Ligar rádio';
  button.setAttribute('aria-label', button.title);
  button.classList.toggle('active', playing);
}

function selectRadio(stationId, autoplay = false) {
  const station = RADIO_STATIONS.find(item => item.id === stationId) || RADIO_STATIONS[0];
  const audio = document.getElementById('telao-radio-audio');
  localStorage.setItem('sinuca_telao_radio', station.id);
  if (audio.src !== station.url) {
    audio.src = station.url;
    audio.load();
  }
  renderRadioMenu();
  if (autoplay) {
    audio.muted = false;
    audio.play().catch(() => updateRadioButton());
  }
  updateRadioButton();
}

function toggleRadio() {
  const audio = document.getElementById('telao-radio-audio');
  if (!audio.src) selectRadio(selectedStation().id);
  if (audio.paused) {
    audio.muted = false;
    audio.play().catch(() => updateRadioButton());
  } else {
    audio.pause();
  }
  updateRadioButton();
}

function setRadioMenuOpen(open) {
  const menu = document.getElementById('telao-radio-menu');
  const button = document.getElementById('telao-radio-menu-button');
  menu.classList.toggle('hidden', !open);
  button.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function applyTelaoZoom(value) {
  telaoZoom = Math.min(1.3, Math.max(0.7, Math.round(value * 10) / 10));
  localStorage.setItem('sinuca_telao_zoom', String(telaoZoom));
  document.documentElement.style.zoom = telaoZoom;
  document.getElementById('telao-zoom-out').disabled = telaoZoom <= 0.7;
  document.getElementById('telao-zoom-in').disabled = telaoZoom >= 1.3;
  requestAnimationFrame(renderCurrentMode);
}

function setupTelaoControls() {
  renderRadioMenu();
  selectRadio(selectedStation().id);
  applyTelaoZoom(telaoZoom);
  document.getElementById('telao-zoom-out').addEventListener('click', () => applyTelaoZoom(telaoZoom - 0.1));
  document.getElementById('telao-zoom-in').addEventListener('click', () => applyTelaoZoom(telaoZoom + 0.1));
  document.getElementById('telao-radio-toggle').addEventListener('click', toggleRadio);
  document.getElementById('telao-radio-menu-button').addEventListener('click', event => {
    event.stopPropagation();
    const menu = document.getElementById('telao-radio-menu');
    setRadioMenuOpen(menu.classList.contains('hidden'));
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.telao-radio-picker')) setRadioMenuOpen(false);
  });
  const audio = document.getElementById('telao-radio-audio');
  ['play', 'pause', 'volumechange', 'error'].forEach(name => audio.addEventListener(name, updateRadioButton));
}

async function loadTelaoState() {
  try {
    telaoState = await apiFetch('/state');
    window.CURRENT_STATE_PLAYERS = telaoState.players || [];
    renderCurrentMode();
  } catch (err) {
    document.getElementById('telao-grid').innerHTML = `<section class="card empty">${escapeHtml(err.message || 'Falha ao carregar o telão.')}</section>`;
  }
}

window.addEventListener('resize', () => {
  if (telaoState) renderCurrentMode();
});

window.addEventListener('DOMContentLoaded', async () => {
  setupTelaoControls();
  await loadTelaoState();
  if (telaoState) startTablesPhase();
  setInterval(loadTelaoState, TV_REFRESH_MS);
});
