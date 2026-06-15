function bracketCrownSvg(kind) {
  const colors = {
    gold: ['#ffd54f', '#a86f00'],
    silver: ['#e6edf3', '#7e8b99'],
    bronze: ['#d99a63', '#7a4021'],
  };
  const [fill, stroke] = colors[kind] || colors.gold;
  return `<svg class="bracket-crown bracket-crown-${kind}" viewBox="0 0 64 42" aria-hidden="true">
    <path d="M7 12l13 10L32 5l12 17 13-10-5 24H12z" fill="${fill}" stroke="${stroke}" stroke-width="3" stroke-linejoin="round"></path>
    <circle cx="7" cy="10" r="4" fill="${fill}"></circle>
    <circle cx="32" cy="5" r="4" fill="${fill}"></circle>
    <circle cx="57" cy="10" r="4" fill="${fill}"></circle>
  </svg>`;
}

function bracketPlayerHtml(participant, nodeId, side, options = {}) {
  const player = participant?.player || participant || null;
  const state = participant?.state || (player ? 'pending' : 'unknown');
  const name = player?.name || '';
  const photo = player?.photo_url || '/img/entre-folhas-logo-transparent.png';
  const crown = options.crown ? bracketCrownSvg(options.crown) : '';
  const photoHtml = player
    ? `<img src="${escapeHtml(photo)}" alt="${escapeHtml(name)}">`
    : '<span class="bracket-question">?</span>';
  const linkStart = player?.profile_url ? `<a href="${escapeHtml(player.profile_url)}">` : '';
  const linkEnd = player?.profile_url ? '</a>' : '';
  return `<div class="bracket-player bracket-player-${escapeHtml(state)} ${options.extraClass || ''}" data-node-id="${escapeHtml(nodeId)}" data-side="${side}" data-slot-state="${escapeHtml(state)}">
    <div class="bracket-photo-wrap">
      ${crown}
      ${linkStart}<div class="bracket-photo">${photoHtml}</div>${linkEnd}
    </div>
    <div class="bracket-player-name">${player ? escapeHtml(name) : '&nbsp;'}</div>
  </div>`;
}

function bracketNodeVisible(node, filterMode) {
  if (filterMode !== 'pending') return true;
  return !['finished', 'bye', 'empty'].includes(node.status);
}

function bracketMatchHtml(node, filterMode = 'all', options = {}) {
  if (!bracketNodeVisible(node, filterMode)) return '';
  const match = node.match || null;
  const score = match?.is_finished
    ? `${Number(match.balls_p1 || 0)} x ${Number(match.balls_p2 || 0)}`
    : 'x';
  const firstCrown = options.isFinal && match?.is_finished
    ? (node.player1?.state === 'winner' ? 'gold' : 'silver')
    : '';
  const secondCrown = options.isFinal && match?.is_finished
    ? (node.player2?.state === 'winner' ? 'gold' : 'silver')
    : '';
  const classes = [
    'bracket-match',
    `bracket-match-${node.status || 'pending'}`,
    options.isBaseRound ? 'bracket-match-base' : 'bracket-match-upper',
    options.isFinal ? 'bracket-match-final' : '',
    firstCrown || secondCrown ? 'bracket-match-awarded' : '',
  ].filter(Boolean).join(' ');
  const gridStyle = [
    options.gridStart && options.gridSpan
      ? `grid-column:${options.gridStart} / span ${options.gridSpan}`
      : '',
    options.matchPhotoSize ? `--match-photo-size:${options.matchPhotoSize}px` : '',
  ].filter(Boolean).join(';');
  return `<div class="${escapeHtml(classes)}" style="${gridStyle}"
      data-bracket-node="${escapeHtml(node.node_id)}"
      data-round-number="${Number(node.round_number || 0)}"
      data-node-index="${Number(node.node_index || 0)}"
      data-source-node-1="${escapeHtml(node.source_node_ids?.[0] || '')}"
      data-source-node-2="${escapeHtml(node.source_node_ids?.[1] || '')}"
      data-node-status="${escapeHtml(node.status || 'pending')}">
    <div class="bracket-players">
      ${bracketPlayerHtml(node.player1, node.node_id, 1, {crown: firstCrown})}
      ${bracketPlayerHtml(node.player2, node.node_id, 2, {crown: secondCrown})}
    </div>
    <div class="bracket-score">${score}</div>
  </div>`;
}

function bracketThirdPlaceHtml(bracket, filterMode = 'all') {
  const thirdPlace = bracket.third_place;
  if (!thirdPlace) return '';
  const match = thirdPlace.match || null;
  if (filterMode === 'pending' && match?.is_finished) return '';
  const player1State = match?.is_finished
    ? (match.winner_id === match.player1_id ? 'winner' : 'loser')
    : (thirdPlace.player1 ? 'pending' : 'unknown');
  const player2State = match?.is_finished
    ? (match.winner_id === match.player2_id ? 'winner' : 'loser')
    : (thirdPlace.player2 ? 'pending' : 'unknown');
  const score = match?.is_finished
    ? `${Number(match.balls_p1 || 0)} x ${Number(match.balls_p2 || 0)}`
    : 'x';
  return `<section class="bracket-third-area">
    <div class="bracket-stage-name">Disputa de 3º lugar</div>
    <div class="bracket-match bracket-match-upper bracket-third-match ${match?.is_finished ? 'bracket-match-awarded' : ''}" data-bracket-node="THIRD" data-node-status="${match?.is_finished ? 'finished' : 'pending'}">
      <div class="bracket-players">
        ${bracketPlayerHtml({player: thirdPlace.player1, state: player1State}, 'THIRD', 1, {
          crown: match?.is_finished && player1State === 'winner' ? 'bronze' : '',
        })}
        ${bracketPlayerHtml({player: thirdPlace.player2, state: player2State}, 'THIRD', 2, {
          crown: match?.is_finished && player2State === 'winner' ? 'bronze' : '',
        })}
      </div>
      <div class="bracket-score">${score}</div>
    </div>
  </section>`;
}

function bracketPodiumPlaceHtml(player, place, crown, label) {
  return `<div class="bracket-podium-place bracket-podium-${place}">
    ${bracketPlayerHtml(
      {player, state: player ? 'winner' : 'unknown'},
      `PODIUM-${place}`,
      1,
      {crown, extraClass: 'bracket-podium-player'},
    )}
    <span class="bracket-podium-label">${escapeHtml(label)}</span>
  </div>`;
}

function bracketFinishedPodiumHtml(bracket) {
  const podium = bracket.podium || {};
  return `<section class="bracket-finished-podium" aria-label="Pódio final">
    ${bracketPodiumPlaceHtml(podium.runner_up, 'second', 'silver', '2º lugar')}
    ${bracketPodiumPlaceHtml(podium.champion, 'first', 'gold', '1º lugar')}
    ${bracketPodiumPlaceHtml(podium.third_place, 'third', 'bronze', '3º lugar')}
  </section>`;
}

function bracketRoundHtml(round, filterMode, totalRounds, basePhotoSize) {
  const gridSpan = 2 ** Math.max(0, Number(round.round_number || 1) - 1);
  const isBaseRound = Number(round.round_number || 1) === 1;
  const isFinal = Number(round.round_number || 1) === Number(totalRounds || 1);
  const matchPhotoSize = Math.min(
    Math.round(basePhotoSize * 1.7),
    basePhotoSize + ((Number(round.round_number || 1) - 1) * 22),
  );
  const nodes = (round.nodes || [])
    .map(node => bracketMatchHtml(node, filterMode, {
      gridStart: (Number(node.node_index || 0) * gridSpan) + 1,
      gridSpan,
      isBaseRound,
      isFinal,
      matchPhotoSize,
    }))
    .filter(Boolean);
  if (!nodes.length) return '';
  return `<section class="bracket-round ${isBaseRound ? 'bracket-round-base' : ''} ${isFinal ? 'bracket-round-final' : ''}" data-bracket-round="${Number(round.round_number)}">
    <div class="bracket-stage-name">${escapeHtml(round.name)}</div>
    <div class="bracket-round-nodes">${nodes.join('')}</div>
  </section>`;
}

function renderKnockoutBracket(bracket, options = {}) {
  if (!bracket) return '<div class="empty">Chaveamento ainda não disponível.</div>';
  const filterMode = options.filterMode === 'pending' ? 'pending' : 'all';
  const rounds = [...(bracket.rounds || [])].reverse();
  const finalRound = rounds[0] || null;
  const remainingRounds = rounds.slice(1);
  const firstRoundNodes = bracket.rounds?.[0]?.nodes?.length || 1;
  const availableTvHeight = Math.max(360, (window.innerHeight || 800) - 140);
  const availableWidth = Math.max(760, (window.innerWidth || 1280) - (options.tv ? 90 : 140));
  const widthBasedPhotoSize = Math.floor((availableWidth / Math.max(1, firstRoundNodes) - 82) / 2);
  const heightBasedPhotoSize = Math.floor(
    (availableTvHeight - 180) / Math.max(2, Number(bracket.total_rounds || 1) * 1.35),
  );
  const basePhotoSize = options.tv
    ? Math.max(64, Math.min(108, widthBasedPhotoSize, heightBasedPhotoSize))
    : Math.max(74, Math.min(112, widthBasedPhotoSize));
  const nodeWidth = Math.max(240, (basePhotoSize * 2) + 120);
  const tvRoundGap = options.tv
    ? Math.max(12, Math.min(34, Math.floor((availableTvHeight - 240) / Math.max(2, Number(bracket.total_rounds || 1) * 2.8))))
    : null;
  const inlineStyle = [
    `--bracket-first-nodes:${Math.max(1, firstRoundNodes)}`,
    `--bracket-photo-size:${basePhotoSize}px`,
    `--bracket-node-width:${nodeWidth}px`,
    tvRoundGap ? `--bracket-round-gap:${tvRoundGap}px` : '',
  ].filter(Boolean).join(';');
  const classes = [
    'knockout-bracket',
    options.tv ? 'knockout-bracket-tv' : '',
    bracket.finished ? 'knockout-bracket-finished' : '',
    `bracket-filter-${filterMode}`,
  ].filter(Boolean).join(' ');
  const filterButtons = options.showFilter ? `<div class="bracket-game-filter" data-bracket-filter>
    <button type="button" data-bracket-filter-mode="pending" class="${filterMode === 'pending' ? 'active' : ''}">Próximos jogos</button>
    <button type="button" data-bracket-filter-mode="all" class="${filterMode === 'all' ? 'active' : ''}">Todos os jogos</button>
  </div>` : '';
  const finalHtml = finalRound
    ? bracketRoundHtml(finalRound, filterMode, bracket.total_rounds, basePhotoSize)
    : '';
  const thirdHtml = bracketThirdPlaceHtml(bracket, filterMode);
  const remainingHtml = remainingRounds
    .map(round => bracketRoundHtml(round, filterMode, bracket.total_rounds, basePhotoSize))
    .filter(Boolean)
    .join('');
  const showFinishedPodium = filterMode === 'pending'
    && bracket.finished
    && !finalHtml
    && !thirdHtml
    && !remainingHtml;
  const noGames = !showFinishedPodium && !finalHtml && !thirdHtml && !remainingHtml
    ? '<div class="empty bracket-empty-filter">Nenhum jogo pendente no chaveamento.</div>'
    : '';
  const finishedPodium = showFinishedPodium ? bracketFinishedPodiumHtml(bracket) : '';

  return `<div class="${classes}" data-knockout-root data-division="${Number(bracket.division || 1)}"
      data-filter-mode="${filterMode}" style="${inlineStyle}">
    <div class="bracket-heading">
      <div>
        <span>Chaveamento</span>
        <h3>${divisionName(bracket.division)}</h3>
      </div>
      <div class="bracket-heading-actions">
        <small>${Number(bracket.participant_count || 0)} classificados${bracket.is_preview ? ' · prévia pelas posições atuais' : ''}</small>
        ${filterButtons}
      </div>
    </div>
    <div class="bracket-scroll">
      <div class="knockout-canvas">
        <svg class="bracket-lines" aria-hidden="true"></svg>
        <div class="bracket-rounds">
          ${finishedPodium}
          ${finalHtml}
          ${thirdHtml}
          ${remainingHtml}
          ${noGames}
        </div>
      </div>
    </div>
  </div>`;
}

function bracketLineColor(state) {
  if (state === 'winner') return '#28d17c';
  if (state === 'loser') return '#ff6464';
  if (state === 'pending') return '#ffd166';
  return '#526476';
}

function bracketSvgPath(svg, pathData, color, width = 3) {
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', pathData);
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', color);
  path.setAttribute('stroke-width', String(width));
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  svg.appendChild(path);
}

function bracketPhotoPoint(photo, canvasRect, edge) {
  const rect = photo.getBoundingClientRect();
  return {
    left: rect.left - canvasRect.left,
    right: rect.right - canvasRect.left,
    top: rect.top - canvasRect.top,
    bottom: rect.bottom - canvasRect.top,
    centerX: rect.left - canvasRect.left + (rect.width / 2),
    centerY: rect.top - canvasRect.top + (rect.height / 2),
    edge,
  };
}

function drawMatchConnector(svg, matchNode, canvasRect) {
  const firstPlayer = matchNode.querySelector(':scope > .bracket-players > .bracket-player[data-side="1"]');
  const secondPlayer = matchNode.querySelector(':scope > .bracket-players > .bracket-player[data-side="2"]');
  const firstPhoto = firstPlayer?.querySelector('.bracket-photo');
  const secondPhoto = secondPlayer?.querySelector('.bracket-photo');
  if (!firstPhoto || !secondPhoto) return null;
  const first = bracketPhotoPoint(firstPhoto, canvasRect, 'right');
  const second = bracketPhotoPoint(secondPhoto, canvasRect, 'left');
  const junctionX = (first.right + second.left) / 2;
  const junctionY = (first.centerY + second.centerY) / 2;
  bracketSvgPath(svg, `M ${first.right} ${first.centerY} H ${junctionX}`, bracketLineColor(firstPlayer.dataset.slotState));
  bracketSvgPath(svg, `M ${second.left} ${second.centerY} H ${junctionX}`, bracketLineColor(secondPlayer.dataset.slotState));
  return {x: junctionX, y: junctionY};
}

function drawKnockoutConnections(root) {
  const canvas = root.querySelector('.knockout-canvas');
  const svg = root.querySelector('.bracket-lines');
  if (!canvas || !svg) return;
  const canvasRect = canvas.getBoundingClientRect();
  const width = Math.max(canvas.scrollWidth, canvas.clientWidth);
  const height = Math.max(canvas.scrollHeight, canvas.clientHeight);
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('width', String(width));
  svg.setAttribute('height', String(height));
  svg.replaceChildren();

  const junctions = new Map();
  root.querySelectorAll('.bracket-match').forEach(matchNode => {
    const junction = drawMatchConnector(svg, matchNode, canvasRect);
    if (junction && matchNode.dataset.bracketNode) {
      junctions.set(matchNode.dataset.bracketNode, junction);
    }
  });

  root.querySelectorAll('.bracket-match[data-round-number]').forEach(sourceNode => {
    const round = Number(sourceNode.dataset.roundNumber || 0);
    const sourceNodeId = sourceNode.dataset.bracketNode || '';
    const sourceJunction = junctions.get(sourceNode.dataset.bracketNode);
    const targetNode = [...root.querySelectorAll(`.bracket-match[data-round-number="${round + 1}"]`)]
      .find(node => (
        node.dataset.sourceNode1 === sourceNodeId
        || node.dataset.sourceNode2 === sourceNodeId
      ));
    if (!sourceJunction || !targetNode) return;
    const targetSide = targetNode.dataset.sourceNode1 === sourceNodeId ? 1 : 2;
    const targetPhoto = targetNode.querySelector(`.bracket-player[data-side="${targetSide}"] .bracket-photo`);
    if (!targetPhoto) return;
    const target = bracketPhotoPoint(targetPhoto, canvasRect, 'bottom');
    const targetY = target.bottom;
    const nodeStatus = sourceNode.dataset.nodeStatus || 'pending';
    const outputColor = nodeStatus === 'finished' || nodeStatus === 'bye'
      ? bracketLineColor('winner')
      : nodeStatus === 'pending' ? bracketLineColor('pending') : bracketLineColor('unknown');
    bracketSvgPath(
      svg,
      `M ${sourceJunction.x} ${sourceJunction.y} V ${targetY}`,
      outputColor,
      4,
    );
  });
}

function alignBracketThirdPlace(root) {
  const finalMatch = root.querySelector('.bracket-round-final .bracket-match');
  const thirdMatch = root.querySelector('.bracket-third-match');
  if (!finalMatch || !thirdMatch) return;
  thirdMatch.style.transform = '';
  const finalRect = finalMatch.getBoundingClientRect();
  const thirdRect = thirdMatch.getBoundingClientRect();
  if (!finalRect.width || !thirdRect.width) return;
  const offset = (finalRect.left + (finalRect.width / 2))
    - (thirdRect.left + (thirdRect.width / 2));
  thirdMatch.style.transform = `translateX(${offset}px)`;
}

function refreshKnockoutConnections(container = document) {
  requestAnimationFrame(() => {
    container.querySelectorAll('[data-knockout-root]').forEach(root => {
      alignBracketThirdPlace(root);
      drawKnockoutConnections(root);
    });
  });
}

function fitKnockoutBrackets(container = document) {
  requestAnimationFrame(() => {
    container.querySelectorAll('.knockout-bracket-tv[data-knockout-root]').forEach(root => {
      const scroll = root.querySelector('.bracket-scroll');
      const canvas = root.querySelector('.knockout-canvas');
      if (!scroll || !canvas) return;
      canvas.style.transform = '';
      alignBracketThirdPlace(root);
      drawKnockoutConnections(root);
      requestAnimationFrame(() => {
        const availableWidth = Math.max(1, scroll.clientWidth - 4);
        const availableHeight = Math.max(1, scroll.clientHeight - 4);
        const scale = Math.min(
          1,
          availableWidth / Math.max(1, canvas.scrollWidth),
          availableHeight / Math.max(1, canvas.scrollHeight),
        );
        const scaledWidth = canvas.scrollWidth * scale;
        const offsetX = Math.max(0, (availableWidth - scaledWidth) / 2);
        canvas.style.transform = `translateX(${offsetX}px) scale(${scale})`;
        canvas.style.transformOrigin = 'top left';
      });
    });
  });
}

let bracketResizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(bracketResizeTimer);
  bracketResizeTimer = setTimeout(() => {
    refreshKnockoutConnections(document);
    fitKnockoutBrackets(document);
  }, 80);
});
