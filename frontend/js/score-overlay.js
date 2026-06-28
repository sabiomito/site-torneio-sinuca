const SCORE_OVERLAY_REFRESH_MS = 30000;
const SCORE_OVERLAY_FALLBACK_PHOTO = '/img/entre-folhas-logo-transparent.png';

let currentScoreOverlayVersion = null;
let scoreOverlayTimer = null;

function scoreOverlayPlayerPartsHtml(player, side, winnerId) {
  const isWinner = player?.player_id && player.player_id === winnerId;
  const photo = player?.photo_url || SCORE_OVERLAY_FALLBACK_PHOTO;
  const fallbackName = side === 'left' ? 'Jogador 1' : 'Jogador 2';
  return `
    <div class="score-overlay-photo-wrap score-overlay-photo-${side} ${isWinner ? 'winner' : ''}">
      <img src="${escapeHtml(photo)}" alt="${escapeHtml(player?.name || '')}">
    </div>
    <h2 class="score-overlay-player-name score-overlay-name-${side}">${escapeHtml(player?.name || fallbackName)}</h2>
    ${player?.short_message ? `<p class="score-overlay-player-message score-overlay-message-${side}">${escapeHtml(player.short_message)}</p>` : ''}`;
}

function scoreOverlayHeadingHtml(state) {
  const title = String(state.title || '').trim();
  const description = String(state.description || '').trim();
  if (!title && !description) return '';
  return `<div class="score-overlay-heading">
    ${title ? `<h1>${escapeHtml(title)}</h1>` : ''}
    ${description ? `<p>${escapeHtml(description)}</p>` : ''}
  </div>`;
}

function renderScoreOverlay(state) {
  const root = document.getElementById('score-overlay-root');
  const player1 = state.player1 || {};
  const player2 = state.player2 || {};
  const score1 = Number(state.score1 || 0);
  const score2 = Number(state.score2 || 0);
  const hasMatch = Boolean(state.match_id);
  root.className = `score-overlay-card${hasMatch ? '' : ' empty'}`;
  if (!hasMatch) {
    root.innerHTML = scoreOverlayHeadingHtml(state);
    return;
  }
  root.innerHTML = `
    ${scoreOverlayHeadingHtml(state)}
    <div class="score-overlay-board">
      ${scoreOverlayPlayerPartsHtml(player1, 'left', state.winner_id)}
      <span class="score-overlay-score-number score-overlay-score-left">${score1}</span>
      <strong class="score-overlay-score-separator">x</strong>
      <span class="score-overlay-score-number score-overlay-score-right">${score2}</span>
      ${scoreOverlayPlayerPartsHtml(player2, 'right', state.winner_id)}
    </div>
  `;
  root.classList.remove('score-overlay-updated');
  requestAnimationFrame(() => {
    root.classList.add('score-overlay-updated');
    setTimeout(() => root.classList.remove('score-overlay-updated'), 650);
  });
}

async function loadScoreOverlay() {
  try {
    const state = await apiFetch('/score-overlay/state');
    if (currentScoreOverlayVersion !== state.version) {
      currentScoreOverlayVersion = state.version;
      renderScoreOverlay(state);
    }
  } catch (err) {
    document.getElementById('score-overlay-root').innerHTML = `
      <div class="score-overlay-heading">
        <h1>Falha ao carregar</h1>
        <p>${escapeHtml(err.message || 'Nao foi possivel carregar o placar.')}</p>
      </div>
    `;
  }
}

function applyScoreOverlayMode() {
  const mode = new URLSearchParams(window.location.search).get('mode');
  if (String(mode || '').toLowerCase() === 'transparent') {
    document.documentElement.classList.add('score-overlay-transparent-root');
    document.body.classList.add('score-overlay-transparent');
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  applyScoreOverlayMode();
  await loadScoreOverlay();
  scoreOverlayTimer = setInterval(loadScoreOverlay, SCORE_OVERLAY_REFRESH_MS);
});

window.addEventListener('beforeunload', () => {
  if (scoreOverlayTimer) clearInterval(scoreOverlayTimer);
});
