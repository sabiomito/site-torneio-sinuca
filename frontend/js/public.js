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
  fillSelect(document.getElementById('filter-player'), state.players, 'player_id', 'name', 'Todos');
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
  let html = '';
  for (let d = 1; d <= state.config.division_count; d++) {
    const rows = state.standings[String(d)] || [];
    html += `<section class="card">
      <div class="section-title">
        <div><h2>${divisionName(d)}</h2><p>Vitória vale 3 pontos. Saldo de bolas é critério de desempate.</p></div>
      </div>`;
    if (!rows.length) {
      html += '<div class="empty">Nenhum jogador cadastrado nesta divisão.</div></section>';
      continue;
    }
    html += `<div class="table-wrap"><table><thead><tr>
      <th>Pos.</th><th>Jogador</th><th>Pontos</th><th>Jogos</th><th>Vitórias</th><th>Bolas +</th><th>Bolas -</th><th>Saldo</th>
    </tr></thead><tbody>`;
    rows.forEach((row, idx) => {
      const statusLabel = row.rank_status === 'promotion' ? ' <span class="badge done">Sobe</span>' : row.rank_status === 'relegation' ? ' <span class="badge danger">Cai</span>' : '';
      html += `<tr class="${escapeHtml(row.rank_status)}">
        <td>${idx + 1}</td>
        <td><a href="player.html?id=${encodeURIComponent(row.player_id)}">${escapeHtml(row.name)}</a>${statusLabel}</td>
        <td><strong>${row.points}</strong></td>
        <td>${row.played}</td>
        <td>${row.wins}</td>
        <td>${row.balls_for}</td>
        <td>${row.balls_against}</td>
        <td>${row.balls_balance}</td>
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
  renderMatches(document.getElementById('matches'), getFilteredMatches(state.matches, filters));
}

loadPublicState();
