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

function renderAll() {
  adminState.rounds = adminState.rounds || [];
  adminState.matches = adminState.matches || [];
  adminState.round_requirements = adminState.round_requirements || [];
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
  renderRoundRequirements();
  renderPlayersList();
  renderRoundsList();
  renderAdminMatches();
}

function renderRoundRequirements() {
  const container = document.getElementById('round-requirements');
  if (!adminState.round_requirements.length) {
    container.innerHTML = '<div class="empty">Configure as divisões e cadastre competidores para calcular as rodadas faltantes.</div>';
    return;
  }
  container.innerHTML = `<h3>Rodadas faltantes por divisão/chave</h3><div class="requirement-grid">${adminState.round_requirements.map(req => {
    const cls = req.missing_rounds > 0 ? 'pending-box' : 'done-box';
    return `<div class="requirement-card ${cls}">
      <strong>${divisionName(req.division)} · Chave ${escapeHtml(req.chave)}</strong>
      <span>${req.players} jogador(es)</span>
      <span>${req.remaining_pairs} confronto(s) restante(s)</span>
      <b>${req.missing_rounds} rodada(s) faltando</b>
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
    <div><strong>${escapeHtml(p.name)}</strong><div class="match-meta">${divisionName(p.division)} · Chave ${escapeHtml(normalizeChave(p.chave))}</div></div>
    <button class="small danger" data-delete-player="${escapeHtml(p.player_id)}">Excluir</button>
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
      <div>
        <strong>${escapeHtml(r.name)} · ${fmtDate(r.date)} · ${escapeHtml(r.start_time || '09:00')}</strong>
        <div class="match-meta">${divisionName(r.division)} · Chave ${escapeHtml(normalizeChave(r.chave))} · Rodada ${r.round_number || '-'} · ${r.mode === 'manual' ? 'manual' : 'automática'} · ${matchCount} jogo(s)</div>
      </div>
      <button class="small danger" data-delete-round="${escapeHtml(r.round_id)}">Excluir rodada</button>
    </div>`;
  }).join('');
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
  const options = players.map(p => `<option value="${escapeHtml(p.player_id)}">${escapeHtml(p.name)}</option>`).join('');
  editor.innerHTML = `<h3>Montar rodada manual</h3>
    <p class="muted">Escolha o adversário de cada jogador. Cada jogador só pode aparecer em um confronto. Se a chave tiver quantidade ímpar, um jogador ficará de folga.</p>
    <div class="manual-pair-list">${players.map(p => `<div class="manual-pair-row" data-player-id="${escapeHtml(p.player_id)}">
      <strong>${escapeHtml(p.name)}</strong>
      <select class="manual-opponent"><option value="">Folga / já escolhido</option>${options}</select>
    </div>`).join('')}</div>
    <div class="actions-row"><button type="button" id="save-manual-round">Salvar rodada manual</button><button type="button" class="secondary" id="cancel-manual-round">Cancelar</button></div>`;
  editor.classList.remove('hidden');
  editor.querySelectorAll('.manual-pair-row').forEach(row => {
    const select = row.querySelector('select');
    [...select.options].forEach(opt => {
      if (opt.value === row.dataset.playerId) opt.remove();
    });
  });
  document.getElementById('cancel-manual-round').addEventListener('click', () => editor.classList.add('hidden'));
  document.getElementById('save-manual-round').addEventListener('click', saveManualRound);
}

async function saveManualRound() {
  const {base} = validateRoundBaseFields();
  const pairs = [];
  const seenPairs = new Set();
  document.querySelectorAll('.manual-pair-row').forEach(row => {
    const p1 = row.dataset.playerId;
    const p2 = row.querySelector('.manual-opponent').value;
    if (!p1 || !p2 || p1 === p2) return;
    const key = [p1, p2].sort().join('#');
    if (seenPairs.has(key)) return;
    seenPairs.add(key);
    pairs.push({player1_id: p1, player2_id: p2});
  });
  const data = await adminFetch('/admin/round-manual', {method: 'POST', body: JSON.stringify(Object.assign({}, base, {pairs}))});
  adminState = data.state || await adminFetch('/admin/state');
  document.getElementById('manual-round-editor').classList.add('hidden');
  preserveScroll(renderAll);
  toast(`Rodada manual criada com ${data.created || 0} jogo(s).`);
}

function renderAdminMatches() {
  const filters = {
    date: document.getElementById('admin-filter-date').value,
    round: document.getElementById('admin-filter-round').value,
    place: document.getElementById('admin-filter-place').value,
    player: document.getElementById('admin-filter-player').value,
    division: document.getElementById('admin-filter-division').value,
    chave: document.getElementById('admin-filter-chave').value,
  };
  const matches = getFilteredMatches(adminState.matches, filters);
  const container = document.getElementById('admin-matches');
  if (!matches.length) {
    container.innerHTML = '<div class="empty">Nenhuma partida encontrada.</div>';
    return;
  }
  container.innerHTML = matches.map(match => {
    const p1Win = match.winner_id === match.player1_id;
    const p2Win = match.winner_id === match.player2_id;
    return `<form class="result-form ${match.is_finished ? 'finished' : ''}" data-match-id="${escapeHtml(match.match_id)}">
      <div class="match-meta">${fmtDate(match.date)} · ${escapeHtml(match.time || '--:--')} até ${escapeHtml(match.end_time || '--:--')} · ${escapeHtml(match.place_name || 'Sem local')} · ${divisionName(match.division)} · Chave ${escapeHtml(normalizeChave(match.chave))} · Rodada ${escapeHtml(match.round_number || '-')} ${match.round_deleted ? '· rodada excluída' : ''} ${match.is_finished ? '· finalizada' : ''}</div>
      <strong>${escapeHtml(match.player1_name)} x ${escapeHtml(match.player2_name)}</strong>
      <div class="result-grid">
        <label>Vencedor
          <select name="winner_id" required>
            <option value="">Selecione</option>
            <option value="${escapeHtml(match.player1_id)}" ${p1Win ? 'selected' : ''}>${escapeHtml(match.player1_name)}</option>
            <option value="${escapeHtml(match.player2_id)}" ${p2Win ? 'selected' : ''}>${escapeHtml(match.player2_name)}</option>
          </select>
        </label>
        <label>Bolas ${escapeHtml(match.player1_name)}
          <input type="number" name="balls_p1" min="0" max="7" value="${match.balls_p1 || 0}">
        </label>
        <label>Bolas ${escapeHtml(match.player2_name)}
          <input type="number" name="balls_p2" min="0" max="7" value="${match.balls_p2 || 0}">
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
      if (winner.value === match.player1_id) p1.value = 7;
      if (winner.value === match.player2_id) p2.value = 7;
    });
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const data = await adminFetch('/admin/result', {
        method: 'POST',
        body: JSON.stringify({
          match_id: form.dataset.matchId,
          winner_id: winner.value,
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

  ['admin-filter-date','admin-filter-round','admin-filter-place','admin-filter-player','admin-filter-division','admin-filter-chave'].forEach(id => {
    document.getElementById(id).addEventListener('change', renderAdminMatches);
  });
  document.getElementById('admin-clear-filters').addEventListener('click', () => {
    ['admin-filter-date','admin-filter-round','admin-filter-place','admin-filter-player','admin-filter-division','admin-filter-chave'].forEach(id => document.getElementById(id).value = '');
    renderAdminMatches();
  });

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
