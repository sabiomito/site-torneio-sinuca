let profileState = null;

function currentProfileSlug() {
  const parts = location.pathname.split('/').filter(Boolean);
  return decodeURIComponent(parts[1] || new URLSearchParams(location.search).get('nome') || '').trim();
}

function normalizeSlug(value) {
  return slugifyPlayerName(value || '');
}

function findPlayerBySlug(players, slug) {
  const target = normalizeSlug(slug);
  return (players || []).find(p => normalizeSlug(p.name) === target || p.slug === target);
}

function allRowsFromStandings(standings) {
  const rows = [];
  Object.values(standings || {}).forEach(chaves => {
    Object.values(chaves || {}).forEach(list => list.forEach((row, idx) => rows.push({...row, rank_position: idx + 1})));
  });
  return rows;
}

function matchDateTimeValue(match) {
  return `${match.date || '9999-99-99'}T${match.time || '99:99'}`;
}

function photoUrl(player) {
  return player?.photo_url || '/img/entre-folhas-logo-transparent.png';
}

function matchResultForPlayer(match, player) {
  if (!match.is_finished) return '<span class="badge pending">Pendente</span>';
  const myBalls = match.player1_id === player.player_id ? match.balls_p1 : match.balls_p2;
  const otherBalls = match.player1_id === player.player_id ? match.balls_p2 : match.balls_p1;
  const won = match.winner_id === player.player_id;
  return `<span class="badge ${won ? 'win' : 'loss'}">${won ? 'Vitória' : 'Derrota'} · ${myBalls || 0} x ${otherBalls || 0}</span>`;
}

function renderProfile(player, state) {
  const rows = allRowsFromStandings(state.standings);
  const row = rows.find(r => r.player_id === player.player_id) || {};
  const matches = (state.matches || [])
    .filter(m => m.player1_id === player.player_id || m.player2_id === player.player_id)
    .sort((a,b) => matchDateTimeValue(a).localeCompare(matchDateTimeValue(b)));
  const nextMatch = matches.find(m => !m.is_finished && matchDateTimeValue(m) >= new Date().toISOString().slice(0,16)) || matches.find(m => !m.is_finished);
  const opponentId = nextMatch ? (nextMatch.player1_id === player.player_id ? nextMatch.player2_id : nextMatch.player1_id) : '';
  const opponent = (state.players || []).find(p => p.player_id === opponentId);
  const ballsFor = Number(row.balls_for || 0);

  document.title = `${player.name} - Perfil do jogador`;
  document.getElementById('profile-root').innerHTML = `
    <section class="card profile-hero">
      <div class="profile-left">
        <img class="profile-photo" src="${escapeHtml(photoUrl(player))}" alt="Foto de ${escapeHtml(player.name)}">
        <div>
          <p class="eyebrow">Perfil do jogador</p>
          <h1>${escapeHtml(player.name)}</h1>
          <p class="profile-message">${escapeHtml(player.short_message || 'Jogador do campeonato de sinuca de Entre Folhas.')}</p>
        </div>
      </div>
      <div class="profile-stats">
        <div class="big-rank"><span>Posição</span><strong>${row.rank_position || '—'}º</strong></div>
        <div class="stat-box"><span>Divisão</span><strong>${divisionName(player.division)}</strong></div>
        <div class="stat-box"><span>Chave</span><strong>${escapeHtml(player.chave || 'A')}</strong></div>
        <div class="stat-box"><span>Jogos</span><strong>${row.played || 0}</strong></div>
        <div class="stat-box"><span>Vitórias</span><strong>${row.wins || 0}</strong></div>
        <div class="stat-box"><span>Derrotas</span><strong>${row.losses || 0}</strong></div>
        <div class="stat-box"><span>Bolas encaçapadas</span><strong>${ballsFor}</strong></div>
        <div class="stat-box"><span>Saldo</span><strong>${row.balls_balance || 0}</strong></div>
      </div>
    </section>

    <section class="card">
      <div class="section-title"><h2>Próximo jogo</h2><span>destaque</span></div>
      ${nextMatch ? `
        <div class="next-match-card">
          <img class="opponent-photo" src="${escapeHtml(photoUrl(opponent))}" alt="Foto do adversário">
          <div>
            <span class="pill">${fmtDate(nextMatch.date)} · ${escapeHtml(nextMatch.time || '--:--')} · ${escapeHtml(nextMatch.place_name || '')}</span>
            <h3>${playerLinkHtml(opponent?.player_id, opponent?.name || 'Adversário')}</h3>
            <p class="muted">${escapeHtml(opponent?.short_message || 'Adversário do próximo confronto.')}</p>
          </div>
        </div>` : '<div class="empty">Nenhum próximo jogo pendente encontrado.</div>'}
    </section>

    <section class="card">
      <div class="section-title"><h2>Todos os jogos</h2><span>${matches.length} partidas</span></div>
      <div class="matches-list">${matches.length ? matches.map(match => {
        const opponentId = match.player1_id === player.player_id ? match.player2_id : match.player1_id;
        const opponentName = match.player1_id === player.player_id ? match.player2_name : match.player1_name;
        return `<div class="match-row ${match.is_finished ? 'finished' : ''}">
          <div class="match-main">
            <span class="pill">${fmtDate(match.date)} · ${escapeHtml(match.time || '--:--')}</span>
            <span>${escapeHtml(match.place_name || '')}</span>
            <strong>${playerLinkHtml(opponentId, opponentName)}</strong>
          </div>
          <div class="match-status">${matchResultForPlayer(match, player)}</div>
        </div>`;
      }).join('') : '<div class="empty">Nenhuma partida encontrada.</div>'}</div>
    </section>
  `;
}

async function loadProfile() {
  const root = document.getElementById('profile-root');
  try {
    profileState = await apiFetch('/state');
    window.CURRENT_STATE_PLAYERS = profileState.players || [];
    const slug = currentProfileSlug();
    const player = findPlayerBySlug(profileState.players || [], slug);
    if (!player) {
      root.innerHTML = '<section class="card empty">Jogador não encontrado.</section>';
      return;
    }
    renderProfile(player, profileState);
  } catch (err) {
    root.innerHTML = `<section class="card empty">${escapeHtml(err.message)}</section>`;
  }
}

loadProfile();
