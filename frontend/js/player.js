async function loadPlayer() {
  const params = new URLSearchParams(location.search);
  const playerId = params.get('id');
  const container = document.getElementById('player-matches');
  if (!playerId) {
    container.innerHTML = '<div class="empty">Jogador não informado.</div>';
    return;
  }
  try {
    const data = await apiFetch(`/player/${encodeURIComponent(playerId)}`);
    document.getElementById('player-title').textContent = data.player.name;
    document.getElementById('player-subtitle').textContent = `${divisionName(data.player.division)} · Todas as partidas`;
    renderMatches(container, data.matches);
  } catch (err) {
    container.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
  }
}
loadPlayer();
