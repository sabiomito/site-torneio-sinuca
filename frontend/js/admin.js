let adminState = null;

const els = {
  loginCard: document.getElementById('login-card'),
  adminPanel: document.getElementById('admin-panel'),
  logout: document.getElementById('logout'),
  toast: document.getElementById('toast'),
};

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove('hidden');
  setTimeout(() => els.toast.classList.add('hidden'), 3600);
}

function preserveScroll(fn) {
  const x = window.scrollX;
  const y = window.scrollY;
  const result = fn();
  requestAnimationFrame(() => window.scrollTo(x, y));
  return result;
}

function collapseAllAdminCards() {
  document.querySelectorAll('#admin-panel .collapsible').forEach(card => card.classList.add('closed'));
}

function normalizeChave(value) {
  return String(value || 'A').trim().toUpperCase() || 'A';
}

function chavesForDivision(division) {
  const rule = adminState?.config?.rules?.[String(division)] || {key_count: 1};
  const count = Math.max(1, Number(rule.key_count || 1));
  const names = [];
  for (let i = 1; i <= count; i++) names.push(chaveName(i));
  return names;
}

function chaveName(index) {
  let n = Math.max(1, Number(index || 1));
  let s = '';
  while (n) {
    const rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function uniqueChaves() {
  const values = new Set();
  (adminState?.players || []).forEach(p => values.add(normalizeChave(p.chave)));
  (adminState?.rounds || []).forEach(r => values.add(normalizeChave(r.chave)));
  (adminState?.matches || []).forEach(m => values.add(normalizeChave(m.chave)));
  return [...values].sort();
}

function fillChaveSelect(select, division, firstLabel = null) {
  const current = select.value;
  select.innerHTML = firstLabel === null ? '' : `<option value="">${escapeHtml(firstLabel)}</option>`;
  chavesForDivision(division).forEach(chave => select.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(chave)}">${escapeHtml(chave)}</option>`));
  if ([...select.options].some(opt => opt.value === current)) select.value = current;
}

function fillAllChavesFilter(select, firstLabel = 'Todas') {
  const current = select.value;
  select.innerHTML = `<option value="">${escapeHtml(firstLabel)}</option>`;
  uniqueChaves().forEach(chave => select.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(chave)}">${escapeHtml(chave)}</option>`));
  if ([...select.options].some(opt => opt.value === current)) select.value = current;
}

async function adminFetch(path, options = {}) {
  return apiFetch(path, Object.assign({}, options, {admin: true}));
}

async function login(password) {
  const data = await apiFetch('/admin/login', {method: 'POST', body: JSON.stringify({password})});
  setToken(data.token);
  await loadAdminState();
}

async function loadAdminState() {
  try {
    adminState = await adminFetch('/admin/state');
    els.loginCard.classList.add('hidden');
    els.adminPanel.classList.remove('hidden');
    els.logout.classList.remove('hidden');
    renderAll();
    collapseAllAdminCards();
  } catch (err) {
    clearToken();
    els.loginCard.classList.remove('hidden');
    els.adminPanel.classList.add('hidden');
    els.logout.classList.add('hidden');
    document.getElementById('login-message').textContent = err.message;
  }
}

function buildRuleFields(containerId, divisionCount, rules = {}) {
  const container = document.getElementById(containerId);
  let html = '';
  for (let d = 1; d <= divisionCount; d++) {
    const rule = rules[String(d)] || {key_count: 1, promotion_count: 0, relegation_count: 0};
    html += `<div class="rule-card" data-division="${d}">
      <h4>${divisionName(d)}</h4>
      <div class="grid-3">
        <label>Quantidade de chaves
          <input type="number" min="1" max="99" class="rule-key-count" value="${rule.key_count || 1}">
        </label>
        <label>Sobem / marcar verde por chave
          <input type="number" min="0" class="rule-promotion" value="${rule.promotion_count || 0}">
        </label>
        <label>Caem / marcar vermelho por chave
          <input type="number" min="0" class="rule-relegation" value="${rule.relegation_count || 0}">
        </label>
      </div>
      <small>Mesmo sem divisão acima/abaixo, os campos de sobem e caem pintam a classificação.</small>
    </div>`;
  }
  container.innerHTML = html;
}

function collectRules(containerId) {
  const rules = {};
  document.querySelectorAll(`#${containerId} .rule-card`).forEach(card => {
    const d = card.dataset.division;
    rules[d] = {
      key_count: Number(card.querySelector('.rule-key-count')?.value || 1),
      promotion_count: Number(card.querySelector('.rule-promotion')?.value || 0),
      relegation_count: Number(card.querySelector('.rule-relegation')?.value || 0),
    };
  });
  return rules;
}

function fillDivisionAndKeyControls() {
  const count = adminState.config.division_count;
  ['player-division', 'round-division', 'admin-filter-division'].forEach(id => {
    const first = id === 'admin-filter-division' ? 'Todas' : null;
    fillDivisionSelect(document.getElementById(id), count, first);
  });
  fillChaveSelect(document.getElementById('player-chave'), Number(document.getElementById('player-division').value || 1));
  fillChaveSelect(document.getElementById('round-chave'), Number(document.getElementById('round-division').value || 1));
}

function renderTvConfig() {
  const tv = adminState.config.tv_config || {
    table_seconds: 60,
    sponsor_seconds: 30,
    match_seconds: 5,
    filters: {},
  };
  const filters = tv.filters || {};
  document.getElementById('tv-table-seconds').value = tv.table_seconds || 60;
  document.getElementById('tv-sponsor-seconds').value = tv.sponsor_seconds || 30;
  document.getElementById('tv-match-seconds').value = tv.match_seconds || 5;
  fillSelect(document.getElementById('tv-filter-date'), adminState.dates, 'date', d => fmtDate(d.date), 'Todas');
  fillSelect(document.getElementById('tv-filter-place'), adminState.places, 'place_id', 'name', 'Todos');
  fillSelect(document.getElementById('tv-filter-player'), adminState.players, 'player_id', p => `${p.name} — ${divisionName(p.division)} / Chave ${normalizeChave(p.chave)}`, 'Todos');
  fillSelect(document.getElementById('tv-filter-round'), adminState.rounds, 'round_id', r => `${fmtDate(r.date)} · ${r.name} · ${divisionName(r.division)} · Chave ${normalizeChave(r.chave)} · Rodada ${r.round_number || ''}`, 'Todas');
  fillDivisionSelect(document.getElementById('tv-filter-division'), adminState.config.division_count, 'Todas');
  fillAllChavesFilter(document.getElementById('tv-filter-chave'), 'Todas');
  Object.entries({
    'tv-filter-date': filters.date,
    'tv-filter-round': filters.round,
    'tv-filter-place': filters.place,
    'tv-filter-player': filters.player,
    'tv-filter-division': filters.division,
    'tv-filter-chave': filters.chave,
    'tv-filter-status': filters.status,
  }).forEach(([id, value]) => {
    const select = document.getElementById(id);
    if ([...select.options].some(option => option.value === String(value || ''))) {
      select.value = String(value || '');
    }
  });
}

function renderAll() {
  adminState.rounds = adminState.rounds || [];
  adminState.matches = adminState.matches || [];
  adminState.round_requirements = adminState.round_requirements || [];
  adminState.sponsors = adminState.sponsors || [];
  const config = adminState.config;
  document.getElementById('division-count').value = config.division_count;
  document.getElementById('duration-minutes').value = config.duration_minutes;
  buildRuleFields('current-rules-fields', config.division_count, config.rules || {});
  fillDivisionAndKeyControls();
  fillSelect(document.getElementById('admin-filter-date'), adminState.dates, 'date', d => fmtDate(d.date), 'Todas');
  fillSelect(document.getElementById('admin-filter-place'), adminState.places, 'place_id', 'name', 'Todos');
  fillSelect(document.getElementById('admin-filter-player'), adminState.players, 'player_id', p => `${p.name} — ${divisionName(p.division)} / Chave ${normalizeChave(p.chave)}`, 'Todos');
  fillSelect(document.getElementById('admin-filter-round'), adminState.rounds, 'round_id', r => `${fmtDate(r.date)} · ${r.name} · ${divisionName(r.division)} · Chave ${normalizeChave(r.chave)} · Rodada ${r.round_number || ''}`, 'Todas');
  fillAllChavesFilter(document.getElementById('admin-filter-chave'), 'Todas');
  renderTvConfig();
  renderRoundRequirements();
  renderPlayersList();
  renderRoundsList();
  renderAdminMatches();
  renderSponsorsList();
}

function renderRoundRequirements() {
  const container = document.getElementById('round-requirements');
  if (!adminState.round_requirements.length) {
    container.innerHTML = '<div class="empty">Configure as divisões e cadastre competidores para calcular as rodadas faltantes.</div>';
    return;
  }
  container.innerHTML = `<h3>Status de rodadas por divisão/chave</h3><div class="requirement-grid">${adminState.round_requirements.map(req => {
    const cls = req.missing_rounds > 0 ? 'pending-box' : 'done-box';
    const partial = Number(req.partial_round_games || 0);
    const perRound = Number(req.matches_per_round || 0);
    const partialText = partial > 0
      ? `<span>Rodada incompleta pendente: ${partial} de ${perRound} jogo(s). Faltam ${req.games_missing_to_full_round || 0} jogo(s) para uma rodada cheia.</span>`
      : '';
    return `<div class="requirement-card ${cls}">
      <strong>${divisionName(req.division)} · Chave ${escapeHtml(req.chave)}</strong>
      <span>${req.players} jogador(es)</span>
      <span>${req.remaining_pairs} jogo(s)/confronto(s) pendente(s)</span>
      <span>${perRound} jogo(s) por rodada cheia</span>
      <b>Pelo menos ${req.missing_rounds} rodada(s) faltando</b>
      ${partialText}
    </div>`;
  }).join('')}</div>`;
}

function renderPlayersList() {
  const container = document.getElementById('players-list');
  if (!adminState.players.length) {
    container.innerHTML = '<div class="empty">Nenhum competidor cadastrado.</div>';
    return;
  }
  container.innerHTML = adminState.players.map(p => `<div class="list-item">
    <div class="list-main-with-photo">
      <img class="mini-avatar" src="${escapeHtml(p.photo_url || '/img/entre-folhas-logo-transparent.png')}" alt="">
      <div><strong>${escapeHtml(p.name)}</strong><div class="match-meta">${divisionName(p.division)} · Chave ${escapeHtml(normalizeChave(p.chave))}${p.short_message ? ` · ${escapeHtml(p.short_message)}` : ''}</div></div>
    </div>
    <div class="list-actions">
      <a class="small-button ghost" href="/admin/jogador?id=${encodeURIComponent(p.player_id)}">Editar info</a>
      <button class="small danger" data-delete-player="${escapeHtml(p.player_id)}">Excluir</button>
    </div>
  </div>`).join('');
  container.querySelectorAll('[data-delete-player]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Excluir este competidor? Partidas pendentes dele serão removidas. Resultados já salvos ficam preservados.')) return;
      const data = await adminFetch('/admin/delete-player', {method: 'POST', body: JSON.stringify({player_id: btn.dataset.deletePlayer})});
      adminState = data.state || await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Competidor excluído.');
    });
  });
}

function renderRoundsList() {
  const container = document.getElementById('rounds-list');
  const rounds = adminState.rounds || [];
  if (!rounds.length) {
    container.innerHTML = '<div class="empty">Nenhuma rodada cadastrada.</div>';
    return;
  }
  container.innerHTML = rounds.map(r => {
    const matchCount = (adminState.matches || []).filter(m => m.round_id === r.round_id).length;
    return `<div class="list-item round-item">
      <div class="round-main">
        <strong>${escapeHtml(r.name)} · ${fmtDate(r.date)} · ${escapeHtml(r.start_time || '09:00')}</strong>
        <div class="match-meta">${divisionName(r.division)} · Chave ${escapeHtml(normalizeChave(r.chave))} · Rodada ${r.round_number || '-'} · ${r.mode === 'manual' ? 'manual' : 'automática'} · ${matchCount} jogo(s)</div>
        <div class="round-edit-line">
          <input type="text" data-round-name-input="${escapeHtml(r.round_id)}" value="${escapeHtml(r.name)}" aria-label="Novo nome da rodada">
          <button class="small secondary" data-update-round="${escapeHtml(r.round_id)}">Salvar nome</button>
        </div>
      </div>
      <button class="small danger" data-delete-round="${escapeHtml(r.round_id)}">Excluir rodada</button>
    </div>`;
  }).join('');
  container.querySelectorAll('[data-update-round]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const input = container.querySelector(`[data-round-name-input="${btn.dataset.updateRound}"]`);
      const name = input ? input.value : '';
      const data = await adminFetch('/admin/update-round', {method: 'POST', body: JSON.stringify({round_id: btn.dataset.updateRound, name})});
      adminState = data.state || await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Nome da rodada atualizado.');
    });
  });
  container.querySelectorAll('[data-delete-round]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Excluir esta rodada? Partidas pendentes serão removidas. Resultados já salvos ficam preservados.')) return;
      const data = await adminFetch('/admin/delete-round', {method: 'POST', body: JSON.stringify({round_id: btn.dataset.deleteRound})});
      adminState = data.state || await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Rodada excluída.');
    });
  });
}


function renderSponsorsList() {
  const container = document.getElementById('sponsors-list');
  if (!container) return;
  const sponsors = adminState.sponsors || [];
  if (!sponsors.length) {
    container.innerHTML = '<div class="empty">Nenhum patrocinador cadastrado.</div>';
    return;
  }
  container.innerHTML = sponsors.map(s => `<div class="list-item">
    <div class="list-main-with-photo">
      <img class="mini-avatar" src="${escapeHtml(s.square_image_url || s.rect_image_url || '/img/entre-folhas-logo-card.png')}" alt="">
      <div>
        <strong>${escapeHtml(s.name)}</strong>
        <div class="match-meta">${s.square_image_url ? 'Imagem quadrada cadastrada' : 'Sem imagem quadrada'} · ${s.rect_image_url ? 'Imagem retangular cadastrada' : 'Sem imagem retangular'}</div>
      </div>
    </div>
    <div class="list-actions">
      <a class="small-button ghost" href="/admin/patrocinador?id=${encodeURIComponent(s.sponsor_id)}">Editar</a>
      <button class="small danger" data-delete-sponsor="${escapeHtml(s.sponsor_id)}">Excluir</button>
    </div>
  </div>`).join('');

  container.querySelectorAll('[data-delete-sponsor]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Excluir este patrocinador?')) return;
      const data = await adminFetch('/admin/delete-sponsor', {method: 'POST', body: JSON.stringify({sponsor_id: btn.dataset.deleteSponsor})});
      adminState = data.state || await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Patrocinador excluído.');
    });
  });
}

function currentRoundBase() {
  return {
    name: document.getElementById('round-name').value,
    division: Number(document.getElementById('round-division').value || 1),
    chave: normalizeChave(document.getElementById('round-chave').value),
    date: document.getElementById('round-date').value,
    start_time: document.getElementById('round-start-time').value || '09:00',
  };
}

function playersForRoundForm() {
  const base = currentRoundBase();
  return (adminState.players || []).filter(p => Number(p.division) === Number(base.division) && normalizeChave(p.chave) === normalizeChave(base.chave));
}

function validateRoundBaseFields() {
  const base = currentRoundBase();
  if (!base.name.trim()) throw new Error('Informe o nome/local da rodada.');
  if (!base.date) throw new Error('Informe a data da rodada.');
  if (!base.start_time) throw new Error('Informe o horário inicial da rodada.');
  const players = playersForRoundForm();
  if (players.length < 2) throw new Error('Essa divisão/chave precisa ter pelo menos 2 competidores.');
  return {base, players};
}

async function addAutomaticRound() {
  const {base} = validateRoundBaseFields();
  const data = await adminFetch('/admin/round-auto', {method: 'POST', body: JSON.stringify(base)});
  adminState = data.state || await adminFetch('/admin/state');
  document.getElementById('manual-round-editor').classList.add('hidden');
  preserveScroll(renderAll);
  toast(`Rodada automática criada com ${data.created || 0} jogo(s).`);
}

function prepareManualRound() {
  const {players} = validateRoundBaseFields();
  const editor = document.getElementById('manual-round-editor');
  const sortedPlayers = [...players].sort((a, b) => String(a.name).localeCompare(String(b.name), 'pt-BR'));
  const gameCount = Math.floor(sortedPlayers.length / 2);
  const byeText = sortedPlayers.length % 2 === 1 ? 'Como a chave tem quantidade ímpar, 1 jogador ficará de folga nesta rodada.' : 'Todos os jogadores da chave precisam aparecer exatamente uma vez.';

  editor.innerHTML = `<h3>Montar rodada manual</h3>
    <p class="muted">Monte os confrontos da rodada. Cada linha é um jogo: escolha um competidor na esquerda e outro na direita. ${escapeHtml(byeText)}</p>
    <div class="manual-pair-list">${Array.from({length: gameCount}).map((_, idx) => `<div class="manual-game-row" data-game-index="${idx}">
      <span class="manual-game-label">Jogo ${idx + 1}</span>
      <select class="manual-player manual-left" data-side="left"></select>
      <span class="manual-versus">x</span>
      <select class="manual-player manual-right" data-side="right"></select>
    </div>`).join('')}</div>
    <div class="manual-bye-box" id="manual-bye-box"></div>
    <div class="actions-row"><button type="button" id="save-manual-round">Salvar rodada manual</button><button type="button" class="secondary" id="cancel-manual-round">Cancelar</button></div>`;
  editor.classList.remove('hidden');

  const selects = [...editor.querySelectorAll('.manual-player')];

  function selectedIds(exceptSelect = null) {
    return new Set(selects.filter(sel => sel !== exceptSelect).map(sel => sel.value).filter(Boolean));
  }

  function refreshManualOptions() {
    selects.forEach(select => {
      const current = select.value;
      const blocked = selectedIds(select);
      select.innerHTML = '<option value="">Selecione</option>';
      sortedPlayers.forEach(player => {
        if (!blocked.has(player.player_id) || player.player_id === current) {
          const selected = player.player_id === current ? 'selected' : '';
          select.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(player.player_id)}" ${selected}>${escapeHtml(player.name)}</option>`);
        }
      });
      if (current && ![...select.options].some(opt => opt.value === current)) {
        select.value = '';
      }
    });

    const used = new Set(selects.map(sel => sel.value).filter(Boolean));
    const freePlayers = sortedPlayers.filter(player => !used.has(player.player_id));
    const byeBox = document.getElementById('manual-bye-box');
    if (!byeBox) return;
    if (freePlayers.length) {
      byeBox.innerHTML = `<strong>Sem jogo nesta rodada:</strong> ${freePlayers.map(p => escapeHtml(p.name)).join(', ')}`;
    } else {
      byeBox.innerHTML = '<strong>Todos os jogadores já foram usados nesta rodada.</strong>';
    }
  }

  selects.forEach(select => select.addEventListener('change', refreshManualOptions));
  refreshManualOptions();

  document.getElementById('cancel-manual-round').addEventListener('click', () => editor.classList.add('hidden'));
  document.getElementById('save-manual-round').addEventListener('click', async () => {
    try { await saveManualRound(); } catch (err) { toast(err.message); }
  });
}

function manualConflictMessage(conflicts) {
  const lines = (conflicts || []).map((item, idx) => {
    const p1 = item.player1_name || 'Jogador 1';
    const p2 = item.player2_name || 'Jogador 2';
    const status = item.status || 'já aconteceu ou já está cadastrado';
    const detail = [item.round_name, item.date ? fmtDate(item.date) : ''].filter(Boolean).join(' · ');
    return `${idx + 1}. ${p1} x ${p2} — ${status}${detail ? ` (${detail})` : ''}`;
  }).join('\n');
  return `Alguns jogos escolhidos já aconteceram ou já estão cadastrados:\n\n${lines}\n\nDeseja criar a rodada mesmo assim, sem esses jogos?`;
}

async function submitManualRoundPayload(payload) {
  const data = await adminFetch('/admin/round-manual', {method: 'POST', body: JSON.stringify(payload)});
  adminState = data.state || await adminFetch('/admin/state');
  document.getElementById('manual-round-editor').classList.add('hidden');
  preserveScroll(renderAll);
  const skipped = Number(data.skipped || 0);
  toast(`Rodada manual criada com ${data.created || 0} jogo(s)${skipped ? `; ${skipped} jogo(s) ignorado(s)` : ''}.`);
}

async function saveManualRound() {
  const {base, players} = validateRoundBaseFields();
  const playerIds = new Set(players.map(p => p.player_id));
  const pairs = [];
  const used = new Set();

  document.querySelectorAll('.manual-game-row').forEach(row => {
    const left = row.querySelector('.manual-left').value;
    const right = row.querySelector('.manual-right').value;
    if (!left && !right) return;
    if (!left || !right) throw new Error('Preencha os dois lados de cada jogo manual.');
    if (left === right) throw new Error('Um jogador não pode enfrentar ele mesmo.');
    if (!playerIds.has(left) || !playerIds.has(right)) throw new Error('Existe jogador fora da chave selecionada.');
    if (used.has(left) || used.has(right)) throw new Error('Cada jogador só pode aparecer uma vez na rodada.');
    used.add(left);
    used.add(right);
    pairs.push({player1_id: left, player2_id: right});
  });

  const expectedGames = Math.floor(players.length / 2);
  if (pairs.length !== expectedGames) {
    throw new Error(`Esta chave precisa de ${expectedGames} jogo(s) nesta rodada.`);
  }

  const payload = Object.assign({}, base, {pairs});
  try {
    await submitManualRoundPayload(payload);
  } catch (err) {
    if (err.status === 409 && err.data && err.data.requires_confirmation) {
      const conflicts = err.data.conflicts || [];
      if (!confirm(manualConflictMessage(conflicts))) {
        toast('Rodada manual cancelada.');
        return;
      }
      await submitManualRoundPayload(Object.assign({}, payload, {confirm_skip_existing: true}));
      return;
    }
    throw err;
  }
}

function currentAdminMatchFilters() {
  return {
    date: document.getElementById('admin-filter-date').value,
    round: document.getElementById('admin-filter-round').value,
    place: document.getElementById('admin-filter-place').value,
    player: document.getElementById('admin-filter-player').value,
    division: document.getElementById('admin-filter-division').value,
    chave: document.getElementById('admin-filter-chave').value,
    status: document.getElementById('admin-filter-status').value,
  };
}

function adminOptionText(id) {
  const el = document.getElementById(id);
  if (!el || !el.value) return '';
  return el.options[el.selectedIndex]?.textContent || '';
}

function currentAdminFilterDescription() {
  const parts = [
    adminOptionText('admin-filter-date') && `Data: ${adminOptionText('admin-filter-date')}`,
    adminOptionText('admin-filter-round') && `Rodada: ${adminOptionText('admin-filter-round')}`,
    adminOptionText('admin-filter-place') && `Local: ${adminOptionText('admin-filter-place')}`,
    adminOptionText('admin-filter-player') && `Competidor: ${adminOptionText('admin-filter-player')}`,
    adminOptionText('admin-filter-division') && `Divisão: ${adminOptionText('admin-filter-division')}`,
    adminOptionText('admin-filter-chave') && `Chave: ${adminOptionText('admin-filter-chave')}`,
    adminOptionText('admin-filter-status') && `Status: ${adminOptionText('admin-filter-status')}`,
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'Todos os jogos exibidos no filtro atual';
}

function currentAdminFilteredMatches() {
  return getFilteredMatches(adminState.matches || [], currentAdminMatchFilters());
}

function renderAdminMatches() {
  const matches = currentAdminFilteredMatches();
  const container = document.getElementById('admin-matches');
  if (!matches.length) {
    container.innerHTML = '<div class="empty">Nenhuma partida encontrada.</div>';
    return;
  }
  container.innerHTML = matches.map(match => {
    const p1Win = match.winner_id === match.player1_id;
    const p2Win = match.winner_id === match.player2_id;
    const doubleLoss = Boolean(match.double_loss);
    return `<form class="result-form ${match.is_finished ? 'finished' : ''}" data-match-id="${escapeHtml(match.match_id)}">
      <div class="match-meta">${fmtDate(match.date)} · ${escapeHtml(match.time || '--:--')} até ${escapeHtml(match.end_time || '--:--')} · ${escapeHtml(match.place_name || 'Sem local')} · ${divisionName(match.division)} · Chave ${escapeHtml(normalizeChave(match.chave))} · Rodada ${escapeHtml(match.round_number || '-')} ${match.round_deleted ? '· rodada excluída' : ''} ${match.is_finished ? '· finalizada' : ''} ${doubleLoss ? '· derrota para ambos' : ''}</div>
      <strong>${escapeHtml(match.player1_name)} x ${escapeHtml(match.player2_name)}</strong>
      <div class="result-grid">
        <label>Resultado
          <select name="winner_id" required>
            <option value="">Selecione</option>
            <option value="${escapeHtml(match.player1_id)}" ${p1Win ? 'selected' : ''}>${escapeHtml(match.player1_name)}</option>
            <option value="${escapeHtml(match.player2_id)}" ${p2Win ? 'selected' : ''}>${escapeHtml(match.player2_name)}</option>
            <option value="__double_loss__" ${doubleLoss ? 'selected' : ''}>Derrota para ambos (0 x 0)</option>
          </select>
        </label>
        <label>Bolas ${escapeHtml(match.player1_name)}
          <input type="number" name="balls_p1" min="0" max="7" value="${match.balls_p1 || 0}" ${doubleLoss ? 'disabled' : ''}>
        </label>
        <label>Bolas ${escapeHtml(match.player2_name)}
          <input type="number" name="balls_p2" min="0" max="7" value="${match.balls_p2 || 0}" ${doubleLoss ? 'disabled' : ''}>
        </label>
        <button type="submit">Salvar resultado</button>
        <button class="secondary" type="button" data-clear-result>Limpar</button>
      </div>
    </form>`;
  }).join('');

  container.querySelectorAll('.result-form').forEach(form => {
    const winner = form.querySelector('[name="winner_id"]');
    const p1 = form.querySelector('[name="balls_p1"]');
    const p2 = form.querySelector('[name="balls_p2"]');
    const match = matches.find(m => m.match_id === form.dataset.matchId);
    winner.addEventListener('change', () => {
      const doubleLoss = winner.value === '__double_loss__';
      p1.disabled = doubleLoss;
      p2.disabled = doubleLoss;
      if (doubleLoss) {
        p1.value = 0;
        p2.value = 0;
      } else if (winner.value === match.player1_id) {
        p1.value = 7;
      } else if (winner.value === match.player2_id) {
        p2.value = 7;
      }
    });
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const data = await adminFetch('/admin/result', {
        method: 'POST',
        body: JSON.stringify({
          match_id: form.dataset.matchId,
          winner_id: winner.value === '__double_loss__' ? '' : winner.value,
          double_loss: winner.value === '__double_loss__',
          balls_p1: Number(p1.value || 0),
          balls_p2: Number(p2.value || 0),
        })
      });
      adminState = data.state || await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Resultado salvo.');
    });
    form.querySelector('[data-clear-result]').addEventListener('click', async () => {
      const data = await adminFetch('/admin/result', {method: 'POST', body: JSON.stringify({match_id: form.dataset.matchId, clear: true})});
      adminState = data.state || await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Resultado removido.');
    });
  });
}

function setupEvents() {
  document.querySelectorAll('.collapsible').forEach(card => card.classList.add('closed'));
  document.querySelectorAll('.collapse-title').forEach(btn => {
    btn.addEventListener('click', () => btn.closest('.collapsible').classList.toggle('closed'));
  });

  document.getElementById('login-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    const msg = document.getElementById('login-message');
    msg.textContent = '';
    try {
      await login(document.getElementById('admin-password').value);
      toast('Login realizado.');
    } catch (err) {
      msg.textContent = err.message;
    }
  });

  els.logout.addEventListener('click', () => { clearToken(); location.reload(); });

  document.getElementById('build-rules').addEventListener('click', () => {
    buildRuleFields('current-rules-fields', Number(document.getElementById('division-count').value || 2), adminState?.config?.rules || {});
  });

  document.getElementById('config-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    const data = await adminFetch('/admin/config', {
      method: 'POST',
      body: JSON.stringify({
        division_count: Number(document.getElementById('division-count').value || 2),
        duration_minutes: Number(document.getElementById('duration-minutes').value || 30),
        rules: collectRules('current-rules-fields'),
      })
    });
    adminState = data.state || await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast('Configurações salvas.');
  });

  document.getElementById('tv-config-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    const data = await adminFetch('/admin/tv-config', {
      method: 'POST',
      body: JSON.stringify({
        table_seconds: Number(document.getElementById('tv-table-seconds').value || 60),
        sponsor_seconds: Number(document.getElementById('tv-sponsor-seconds').value || 30),
        match_seconds: Number(document.getElementById('tv-match-seconds').value || 5),
        filters: {
          date: document.getElementById('tv-filter-date').value,
          round: document.getElementById('tv-filter-round').value,
          place: document.getElementById('tv-filter-place').value,
          player: document.getElementById('tv-filter-player').value,
          division: document.getElementById('tv-filter-division').value,
          chave: document.getElementById('tv-filter-chave').value,
          status: document.getElementById('tv-filter-status').value,
        },
      }),
    });
    adminState = data.state || await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast('Configurações do telão salvas.');
  });

  document.getElementById('player-division').addEventListener('change', ev => fillChaveSelect(document.getElementById('player-chave'), Number(ev.target.value || 1)));
  document.getElementById('round-division').addEventListener('change', ev => fillChaveSelect(document.getElementById('round-chave'), Number(ev.target.value || 1)));

  document.getElementById('player-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    const data = await adminFetch('/admin/player', {
      method: 'POST',
      body: JSON.stringify({
        name: document.getElementById('player-name').value,
        division: Number(document.getElementById('player-division').value),
        chave: normalizeChave(document.getElementById('player-chave').value),
      })
    });
    document.getElementById('player-name').value = '';
    adminState = data.state || await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast('Competidor adicionado.');
  });

  document.getElementById('add-round-auto').addEventListener('click', async () => {
    try { await addAutomaticRound(); } catch (err) { toast(err.message); }
  });
  document.getElementById('prepare-round-manual').addEventListener('click', () => {
    try { prepareManualRound(); } catch (err) { toast(err.message); }
  });

  ['admin-filter-date','admin-filter-round','admin-filter-place','admin-filter-player','admin-filter-division','admin-filter-chave','admin-filter-status'].forEach(id => {
    document.getElementById(id).addEventListener('change', renderAdminMatches);
  });
  document.getElementById('admin-clear-filters').addEventListener('click', () => {
    ['admin-filter-date','admin-filter-round','admin-filter-place','admin-filter-player','admin-filter-division','admin-filter-chave','admin-filter-status'].forEach(id => document.getElementById(id).value = '');
    renderAdminMatches();
  });
  const adminPrintButton = document.getElementById('admin-print-filtered-matches');
  if (adminPrintButton) {
    adminPrintButton.addEventListener('click', () => {
      openMatchesPrintWindow(currentAdminFilteredMatches(), 'Lista de jogos do torneio', currentAdminFilterDescription());
    });
  }

  const sponsorForm = document.getElementById('sponsor-form');
  if (sponsorForm) {
    sponsorForm.addEventListener('submit', async ev => {
      ev.preventDefault();
      const nameInput = document.getElementById('sponsor-name');
      const data = await adminFetch('/admin/sponsor', {
        method: 'POST',
        body: JSON.stringify({name: nameInput.value})
      });
      nameInput.value = '';
      adminState = data.state || await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Patrocinador adicionado.');
    });
  }

  document.getElementById('clear-database').addEventListener('click', async () => {
    if (!confirm('Tem certeza que deseja limpar TODO o banco do torneio? Isso apaga tudo e não tem volta.')) return;
    const confirmText = prompt('Para confirmar, digite exatamente: LIMPAR');
    if (String(confirmText || '').trim().toUpperCase() !== 'LIMPAR') {
      toast('Limpeza cancelada.');
      return;
    }
    const data = await adminFetch('/admin/clear-database', {method: 'POST', body: JSON.stringify({confirm_text: 'LIMPAR'})});
    adminState = data.state || await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast('Banco de dados limpo.');
  });
}

setupEvents();
if (getToken()) loadAdminState();
