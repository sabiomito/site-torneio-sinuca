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

async function adminFetch(path, options = {}) {
  return apiFetch(path, Object.assign({}, options, {admin: true}));
}

async function login(password) {
  const data = await apiFetch('/admin/login', {
    method: 'POST',
    body: JSON.stringify({password})
  });
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
    const rule = rules[String(d)] || {promotion_count: 0, relegation_count: 0};
    html += `<div class="rule-card" data-division="${d}">
      <h4>${divisionName(d)}</h4>
      <div class="grid-2">
        <label>Sobem
          <input type="number" min="0" class="rule-promotion" value="${d === 1 ? 0 : (rule.promotion_count || 0)}" ${d === 1 ? 'disabled' : ''}>
        </label>
        <label>Caem
          <input type="number" min="0" class="rule-relegation" value="${d === divisionCount ? 0 : (rule.relegation_count || 0)}" ${d === divisionCount ? 'disabled' : ''}>
        </label>
      </div>
    </div>`;
  }
  container.innerHTML = html;
}

function collectRules(containerId) {
  const rules = {};
  document.querySelectorAll(`#${containerId} .rule-card`).forEach(card => {
    const d = card.dataset.division;
    rules[d] = {
      promotion_count: Number(card.querySelector('.rule-promotion')?.value || 0),
      relegation_count: Number(card.querySelector('.rule-relegation')?.value || 0),
    };
  });
  return rules;
}

function buildDateOptions(selectedDate) {
  const current = selectedDate || '';
  let html = '<option value="">Selecione</option>';
  adminState.dates.forEach(d => {
    const value = d.date;
    html += `<option value="${escapeHtml(value)}" ${value === current ? 'selected' : ''}>${fmtDate(value)}</option>`;
  });
  return html;
}

function buildPlaceOptions(selectedPlaceId) {
  const current = selectedPlaceId || '';
  let html = '<option value="">Selecione</option>';
  adminState.places.forEach(p => {
    const value = p.place_id;
    html += `<option value="${escapeHtml(value)}" ${value === current ? 'selected' : ''}>${escapeHtml(p.name)}</option>`;
  });
  return html;
}

function buildSetupPlayerFields() {
  const count = Number(document.getElementById('setup-division-count').value || 2);
  buildRuleFields('rules-fields', count, {});
  const container = document.getElementById('players-fields');
  let html = '<h3>Competidores por divisão</h3><div class="grid-2">';
  for (let d = 1; d <= count; d++) {
    html += `<label>${divisionName(d)} — um jogador por linha
      <textarea class="setup-players" data-division="${d}" rows="6" placeholder="Jogador 1&#10;Jogador 2"></textarea>
    </label>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

function parseSetupDates(text) {
  return text.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    const parts = line.split(/\s+/);
    return {date: parts[0], start_time: parts[1] || '09:00'};
  });
}

function parseSetupPlayers() {
  const players = [];
  document.querySelectorAll('.setup-players').forEach(area => {
    const division = Number(area.dataset.division || 1);
    area.value.split('\n').map(x => x.trim()).filter(Boolean).forEach(name => players.push({name, division}));
  });
  return players;
}

function renderAll() {
  const config = adminState.config;
  document.getElementById('division-count').value = config.division_count;
  document.getElementById('duration-minutes').value = config.duration_minutes;
  buildRuleFields('current-rules-fields', config.division_count, config.rules || {});
  fillDivisionSelect(document.getElementById('player-division'), config.division_count, null);
  fillSelect(document.getElementById('admin-filter-date'), adminState.dates, 'date', d => fmtDate(d.date), 'Todas');
  fillSelect(document.getElementById('admin-filter-place'), adminState.places, 'place_id', 'name', 'Todos');
  fillSelect(document.getElementById('admin-filter-player'), adminState.players, 'player_id', 'name', 'Todos');
  fillDivisionSelect(document.getElementById('admin-filter-division'), config.division_count, 'Todas');
  renderPlayersList();
  renderPlacesList();
  renderDatesList();
  renderAdminMatches();
}

function renderPlayersList() {
  const container = document.getElementById('players-list');
  if (!adminState.players.length) {
    container.innerHTML = '<div class="empty">Nenhum competidor cadastrado.</div>';
    return;
  }
  container.innerHTML = adminState.players.map(p => `<div class="list-item">
    <div><strong>${escapeHtml(p.name)}</strong><div class="match-meta">${divisionName(p.division)}</div></div>
    <button class="small danger" data-delete-player="${escapeHtml(p.player_id)}">Excluir</button>
  </div>`).join('');
  container.querySelectorAll('[data-delete-player]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Excluir este competidor? Depois use Recalcular torneio.')) return;
      await adminFetch('/admin/delete-player', {method: 'POST', body: JSON.stringify({player_id: btn.dataset.deletePlayer})});
      adminState = await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Competidor excluído. Recalcule o calendário.');
    });
  });
}

function renderPlacesList() {
  const container = document.getElementById('places-list');
  if (!adminState.places.length) {
    container.innerHTML = '<div class="empty">Nenhum local cadastrado.</div>';
    return;
  }
  container.innerHTML = adminState.places.map(p => `<div class="list-item">
    <strong>${escapeHtml(p.name)}</strong>
    <button class="small danger" data-delete-place="${escapeHtml(p.place_id)}">Excluir</button>
  </div>`).join('');
  container.querySelectorAll('[data-delete-place]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Excluir este local? Depois use Recalcular torneio.')) return;
      await adminFetch('/admin/delete-place', {method: 'POST', body: JSON.stringify({place_id: btn.dataset.deletePlace})});
      adminState = await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Local excluído. Recalcule o calendário.');
    });
  });
}

function renderDatesList() {
  const container = document.getElementById('dates-list');
  if (!adminState.dates.length) {
    container.innerHTML = '<div class="empty">Nenhuma data cadastrada.</div>';
    return;
  }
  container.innerHTML = adminState.dates.map(d => `<div class="list-item">
    <strong>${fmtDate(d.date)}</strong>
    <span class="match-meta">Início ${escapeHtml(d.start_time || '09:00')}</span>
    <button class="small danger" data-delete-date="${escapeHtml(d.date_id)}">Excluir</button>
  </div>`).join('');
  container.querySelectorAll('[data-delete-date]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Excluir esta data? Depois use Recalcular torneio.')) return;
      await adminFetch('/admin/delete-date', {method: 'POST', body: JSON.stringify({date_id: btn.dataset.deleteDate})});
      adminState = await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Data excluída. Recalcule o calendário.');
    });
  });
}

function renderAdminMatches() {
  const filters = {
    date: document.getElementById('admin-filter-date').value,
    place: document.getElementById('admin-filter-place').value,
    player: document.getElementById('admin-filter-player').value,
    division: document.getElementById('admin-filter-division').value,
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
      <div class="match-meta">${fmtDate(match.date)} · ${escapeHtml(match.time || '--:--')} até ${escapeHtml(match.end_time || '--:--')} · ${escapeHtml(match.place_name || 'Sem local')} · ${divisionName(match.division)} ${match.manual_schedule ? '· agenda manual' : ''}</div>
      <strong>${escapeHtml(match.player1_name)} x ${escapeHtml(match.player2_name)}</strong>

      <div class="manual-schedule">
        <div class="manual-title">Agenda da partida</div>
        <div class="manual-grid">
          <label>Data
            <select name="schedule_date">${buildDateOptions(match.date)}</select>
          </label>
          <label>Horário
            <input type="time" name="schedule_time" value="${escapeHtml(match.time || '')}">
          </label>
          <label>Local
            <select name="schedule_place_id">${buildPlaceOptions(match.place_id)}</select>
          </label>
          <button class="secondary" type="button" data-save-schedule>Salvar agenda</button>
        </div>
        <small>Essa alteração manual será perdida se o torneio for recalculado.</small>
      </div>

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

    form.querySelector('[data-save-schedule]').addEventListener('click', async () => {
      await adminFetch('/admin/match-schedule', {
        method: 'POST',
        body: JSON.stringify({
          match_id: form.dataset.matchId,
          date: form.querySelector('[name="schedule_date"]').value,
          time: form.querySelector('[name="schedule_time"]').value,
          place_id: form.querySelector('[name="schedule_place_id"]').value,
        })
      });
      adminState = await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Agenda da partida salva.');
    });

    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      await adminFetch('/admin/result', {
        method: 'POST',
        body: JSON.stringify({
          match_id: form.dataset.matchId,
          winner_id: winner.value,
          balls_p1: Number(p1.value || 0),
          balls_p2: Number(p2.value || 0),
        })
      });
      adminState = await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Resultado salvo.');
    });
    form.querySelector('[data-clear-result]').addEventListener('click', async () => {
      await adminFetch('/admin/result', {method: 'POST', body: JSON.stringify({match_id: form.dataset.matchId, clear: true})});
      adminState = await adminFetch('/admin/state');
      preserveScroll(renderAll);
      toast('Resultado removido.');
    });
  });
}

function setupEvents() {
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

  els.logout.addEventListener('click', () => {
    clearToken();
    location.reload();
  });

  document.getElementById('build-setup-fields').addEventListener('click', buildSetupPlayerFields);
  document.getElementById('build-rules').addEventListener('click', () => {
    buildRuleFields('current-rules-fields', Number(document.getElementById('division-count').value || 2), adminState?.config?.rules || {});
  });

  document.getElementById('setup-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    if (!confirm('Criar um novo torneio vai apagar os dados atuais. Continuar?')) return;
    const places = document.getElementById('setup-places').value.split('\n').map(x => x.trim()).filter(Boolean);
    const dates = parseSetupDates(document.getElementById('setup-dates').value);
    const players = parseSetupPlayers();
    await adminFetch('/admin/setup', {
      method: 'POST',
      body: JSON.stringify({
        division_count: Number(document.getElementById('setup-division-count').value || 2),
        duration_minutes: Number(document.getElementById('setup-duration').value || 30),
        rules: collectRules('rules-fields'),
        places,
        dates,
        players,
      })
    });
    adminState = await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast('Torneio criado e calendário calculado.');
  });

  document.getElementById('config-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    await adminFetch('/admin/config', {
      method: 'POST',
      body: JSON.stringify({
        division_count: Number(document.getElementById('division-count').value || 2),
        duration_minutes: Number(document.getElementById('duration-minutes').value || 30),
        rules: collectRules('current-rules-fields'),
      })
    });
    adminState = await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast('Configurações salvas. Recalcule o calendário se necessário.');
  });

  document.getElementById('player-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    await adminFetch('/admin/player', {
      method: 'POST',
      body: JSON.stringify({name: document.getElementById('player-name').value, division: Number(document.getElementById('player-division').value)})
    });
    document.getElementById('player-name').value = '';
    adminState = await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast('Competidor adicionado. Recalcule o calendário.');
  });

  document.getElementById('place-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    await adminFetch('/admin/place', {method: 'POST', body: JSON.stringify({name: document.getElementById('place-name').value})});
    document.getElementById('place-name').value = '';
    adminState = await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast('Local adicionado. Recalcule o calendário.');
  });

  document.getElementById('date-form').addEventListener('submit', async ev => {
    ev.preventDefault();
    await adminFetch('/admin/date', {method: 'POST', body: JSON.stringify({date: document.getElementById('date-value').value, start_time: document.getElementById('date-start-time').value || '09:00'})});
    document.getElementById('date-value').value = '';
    adminState = await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast('Data adicionada. Recalcule o calendário.');
  });

  document.getElementById('recalculate').addEventListener('click', async () => {
    const result = await adminFetch('/admin/recalculate', {method: 'POST', body: '{}'});
    adminState = await adminFetch('/admin/state');
    preserveScroll(renderAll);
    toast(result.message || 'Calendário recalculado.');
  });

  ['admin-filter-date','admin-filter-place','admin-filter-player','admin-filter-division'].forEach(id => {
    document.getElementById(id).addEventListener('change', renderAdminMatches);
  });
  document.getElementById('admin-clear-filters').addEventListener('click', () => {
    ['admin-filter-date','admin-filter-place','admin-filter-player','admin-filter-division'].forEach(id => document.getElementById(id).value = '');
    renderAdminMatches();
  });
}

setupEvents();
buildSetupPlayerFields();
if (getToken()) loadAdminState();
