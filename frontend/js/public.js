let state = null;

async function loadPublicState() {
  const standingsEl = document.getElementById('standings');
  const matchesEl = document.getElementById('matches');
  try {
    state = await apiFetch('/state');
    setupFilters();
    renderStandings();
    renderFilteredMatches();
  } catch (err) {
    standingsEl.innerHTML = `<section class="card"><div class="empty">${escapeHtml(err.message)}</div></section>`;
    matchesEl.innerHTML = '';
  }
}

function setupFilters() {
  fillSelect(document.getElementById('filter-date'), state.dates, 'date', d => fmtDate(d.date), 'Todas');
  fillSelect(document.getElementById('filter-place'), state.places, 'place_id', 'name', 'Todos');
  fillSelect(document.getElementById('filter-player'), state.players, 'player_id', p => `${p.name} — ${divisionName(p.division)}`, 'Todos');
  fillDivisionSelect(document.getElementById('filter-division'), state.config.division_count, 'Todas');
  ['filter-date','filter-place','filter-player','filter-division'].forEach(id => {
    document.getElementById(id).addEventListener('change', renderFilteredMatches);
  });
  document.getElementById('clear-filters').addEventListener('click', () => {
    ['filter-date','filter-place','filter-player','filter-division'].forEach(id => document.getElementById(id).value = '');
    renderFilteredMatches();
  });
}

function renderStandings() {
  const standingsEl = document.getElementById('standings');
  const hasData = state.players.length || state.matches.length || state.places.length || state.dates.length;
  let html = '';

  if (!hasData) {
    html += `<section class="card empty">
      <h2>Nenhum torneio criado ainda</h2>
      <p>Entre em <a href="/admin">/admin</a>, faça login e crie o torneio informando jogadores, locais, datas e horários iniciais.</p>
    </section>`;
  }

  for (let d = 1; d <= state.config.division_count; d++) {
    const rows = state.standings[String(d)] || [];
    html += `<section class="card">
      <div class="section-title">
        <h2>${divisionName(d)}</h2>
        <span>${rows.length} jogadores</span>
      </div>`;
    if (!rows.length) {
      html += '<p class="muted">Nenhum jogador cadastrado nesta divisão.</p></section>';
      continue;
    }
    html += `<div class="table-wrap"><table><thead><tr>
      <th>#</th><th>Jogador</th><th>Pontos</th><th>Vitórias</th><th>Jogos</th><th>Bolas +</th><th>Bolas -</th><th>Saldo</th><th>Situação</th>
    </tr></thead><tbody>`;
    rows.forEach((row, idx) => {
      const statusLabel = row.rank_status === 'promotion'
        ? '<span class="badge win">Sobe</span>'
        : row.rank_status === 'relegation'
          ? '<span class="badge loss">Cai</span>'
          : '<span class="muted">—</span>';
      html += `<tr class="${escapeHtml(row.rank_status)}">
        <td>${idx + 1}</td>
        <td><a class="player-link" href="/player.html?id=${encodeURIComponent(row.player_id)}">${escapeHtml(row.name)}</a></td>
        <td><strong>${row.points}</strong></td>
        <td>${row.wins}</td>
        <td>${row.played}</td>
        <td>${row.balls_for}</td>
        <td>${row.balls_against}</td>
        <td><strong>${row.balls_balance}</strong></td>
        <td>${statusLabel}</td>
      </tr>`;
    });
    html += '</tbody></table></div></section>';
  }
  standingsEl.innerHTML = html;
}

function renderFilteredMatches() {
  const filters = {
    date: document.getElementById('filter-date').value,
    place: document.getElementById('filter-place').value,
    player: document.getElementById('filter-player').value,
    division: document.getElementById('filter-division').value,
  };
  const filtered = getFilteredMatches(state.matches, filters);
  const count = document.getElementById('matches-count');
  if (count) count.textContent = `${filtered.length} partidas`;
  renderMatches(document.getElementById('matches'), filtered);
}

loadPublicState();
