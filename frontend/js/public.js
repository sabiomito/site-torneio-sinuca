let state = null;
let matchesRequestId = 0;

function normalizeChave(value) {
  return String(value || 'A').trim().toUpperCase() || 'A';
}

function uniqueChaves() {
  const values = new Set();
  (state?.players || []).forEach(p => values.add(normalizeChave(p.chave)));
  (state?.matches || []).forEach(m => values.add(normalizeChave(m.chave)));
  return [...values].sort();
}

function fillChaveSelect(select, firstLabel = 'Todas') {
  const current = select.value;
  select.innerHTML = `<option value="">${escapeHtml(firstLabel)}</option>`;
  uniqueChaves().forEach(chave => select.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(chave)}">${escapeHtml(chave)}</option>`));
  if ([...select.options].some(opt => opt.value === current)) select.value = current;
}

async function loadPublicState() {
  const standingsEl = document.getElementById('standings');
  const matchesEl = document.getElementById('matches');
  try {
    state = await apiFetch('/state?include_matches=0');
    window.CURRENT_STATE_PLAYERS = state.players || [];
    setupFilters();
    renderStandings();
    renderMatchesPrompt();
  } catch (err) {
    standingsEl.innerHTML = `<section class="card"><div class="empty">${escapeHtml(err.message)}</div></section>`;
    matchesEl.innerHTML = '';
  }
}

function setupFilters() {
  fillSelect(document.getElementById('filter-date'), state.dates, 'date', d => fmtDate(d.date), 'Todas');
  fillSelect(document.getElementById('filter-place'), state.places, 'place_id', 'name', 'Todos');
  fillSelect(document.getElementById('filter-player'), state.players, 'player_id', p => `${p.name} — ${divisionName(p.division)} / Chave ${normalizeChave(p.chave)}`, 'Todos');
  fillDivisionSelect(document.getElementById('filter-division'), state.config.division_count, 'Todas');
  fillChaveSelect(document.getElementById('filter-chave'), 'Todas');
  ['filter-date','filter-place','filter-player','filter-division','filter-chave','filter-status'].forEach(id => {
    document.getElementById(id).addEventListener('change', loadFilteredMatches);
  });
  document.getElementById('clear-filters').addEventListener('click', () => {
    ['filter-date','filter-place','filter-player','filter-division','filter-chave','filter-status'].forEach(id => document.getElementById(id).value = '');
    state.matches = [];
    matchesRequestId += 1;
    renderMatchesPrompt();
  });
  const printButton = document.getElementById('print-filtered-matches');
  if (printButton) {
    printButton.addEventListener('click', () => {
      const matches = currentFilteredMatches();
      openMatchesPrintWindow(matches, 'Lista de jogos do torneio', currentFilterDescription());
    });
  }
}

function currentFilters() {
  return {
    date: document.getElementById('filter-date').value,
    place: document.getElementById('filter-place').value,
    player: document.getElementById('filter-player').value,
    division: document.getElementById('filter-division').value,
    chave: document.getElementById('filter-chave').value,
    status: document.getElementById('filter-status').value,
  };
}

function currentFilteredMatches() {
  return state.matches || [];
}

function hasActiveMatchFilters(filters) {
  return Object.values(filters).some(Boolean);
}

async function loadFilteredMatches() {
  const filters = currentFilters();
  if (!hasActiveMatchFilters(filters)) {
    state.matches = [];
    matchesRequestId += 1;
    renderMatchesPrompt();
    return;
  }
  const requestId = ++matchesRequestId;
  const count = document.getElementById('matches-count');
  const container = document.getElementById('matches');
  count.textContent = 'Carregando...';
  container.innerHTML = '<div class="empty">Buscando partidas...</div>';
  try {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    const data = await apiFetch(`/matches?${query.toString()}`);
    if (requestId !== matchesRequestId) return;
    state.matches = data.matches || [];
    renderFilteredMatches();
  } catch (err) {
    if (requestId !== matchesRequestId) return;
    count.textContent = '';
    container.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
  }
}

function optionText(id) {
  const el = document.getElementById(id);
  if (!el || !el.value) return '';
  return el.options[el.selectedIndex]?.textContent || '';
}

function currentFilterDescription() {
  const parts = [
    optionText('filter-date') && `Data: ${optionText('filter-date')}`,
    optionText('filter-place') && `Local: ${optionText('filter-place')}`,
    optionText('filter-player') && `Competidor: ${optionText('filter-player')}`,
    optionText('filter-division') && `Divisão: ${optionText('filter-division')}`,
    optionText('filter-chave') && `Chave: ${optionText('filter-chave')}`,
    optionText('filter-status') && `Status: ${optionText('filter-status')}`,
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'Todos os jogos exibidos no filtro atual';
}

function renderStandingsTable(rows) {
  if (!rows.length) return '<p class="muted">Nenhum jogador cadastrado nesta chave.</p>';
  let html = `<div class="table-wrap"><table><thead><tr>
    <th>#</th><th>Jogador</th><th>Pontos</th><th>Vitórias</th><th>Jogos</th><th>Bolas +</th><th>Bolas -</th><th>Saldo</th><th>Situação</th>
  </tr></thead><tbody>`;
  rows.forEach((row, idx) => {
    const statusLabel = row.rank_status === 'promotion'
      ? '<span class="badge win">Classificado</span>'
      : row.rank_status === 'relegation'
        ? '<span class="badge loss">Rebaixado</span>'
        : '<span class="muted">—</span>';
    html += `<tr class="${escapeHtml(row.rank_status)}">
      <td>${idx + 1}</td>
      <td>${playerLinkHtml(row.player_id, row.name)}</td>
      <td><strong>${row.points}</strong></td>
      <td>${row.wins}</td>
      <td>${row.played}</td>
      <td>${row.balls_for}</td>
      <td>${row.balls_against}</td>
      <td><strong>${row.balls_balance}</strong></td>
      <td>${statusLabel}</td>
    </tr>`;
  });
  html += '</tbody></table></div>';
  return html;
}

function renderStandings() {
  const standingsEl = document.getElementById('standings');
  const hasData = state.players.length || state.matches.length || state.places.length || state.dates.length;
  let html = '';

  if (!hasData) {
    html += `<section class="card empty">
      <h2>Nenhum torneio criado ainda</h2>
      <p>Entre em <a href="/admin">/admin</a>, faça login e crie o torneio informando jogadores, rodadas e chaves.</p>
    </section>`;
  }

  for (let d = 1; d <= state.config.division_count; d++) {
    const chaves = state.standings[String(d)] || {};
    const chaveNames = Object.keys(chaves).sort();
    const divisionPlayers = chaveNames.reduce((total, chave) => total + (chaves[chave] || []).length, 0);
    html += `<section class="card standings-card">
      <div class="section-title">
        <h2>${divisionName(d)}</h2>
        <span>${divisionPlayers} jogadores</span>
      </div>`;
    if (!chaveNames.length) {
      html += '<p class="muted">Nenhum jogador cadastrado nesta divisão.</p></section>';
      continue;
    }
    const showChaveInShare = chaveNames.length > 1;
    chaveNames.forEach(chave => {
      const rows = chaves[chave] || [];
      html += `<div class="chave-block">
        <div class="section-subtitle standings-subtitle">
          <h3>${showChaveInShare ? `Chave ${escapeHtml(chave)}` : 'Classificação'}</h3>
          <div class="table-actions">
            <span>${rows.length} jogadores</span>
            <button class="small share-table-button" type="button" data-share-division="${d}" data-share-chave="${escapeHtml(chave)}" data-share-show-chave="${showChaveInShare ? '1' : '0'}">Compartilhar</button>
          </div>
        </div>
        ${renderStandingsTable(rows)}
      </div>`;
    });
    html += '</section>';
  }
  standingsEl.innerHTML = html;
  standingsEl.querySelectorAll('[data-share-division]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const division = Number(btn.dataset.shareDivision || 1);
      const chave = normalizeChave(btn.dataset.shareChave || 'A');
      const showChave = btn.dataset.shareShowChave === '1';
      try {
        await generateShareImage(division, chave, showChave);
      } catch (err) {
        alert(err.message || 'Não foi possível gerar a imagem.');
      }
    });
  });
}


function drawRoundedRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function loadCanvasImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Falha ao carregar imagem: ${src}`));
    img.src = src;
  });
}

function drawImageCover(ctx, img, x, y, w, h) {
  const scale = Math.max(w / img.width, h / img.height);
  const sw = w / scale;
  const sh = h / scale;
  const sx = (img.width - sw) / 2;
  const sy = (img.height - sh) / 2;
  ctx.drawImage(img, sx, sy, sw, sh, x, y, w, h);
}

async function drawShareBackground(ctx, width, height) {
  try {
    const bg = await loadCanvasImage('/img/share-bg-base.png');
    drawImageCover(ctx, bg, 0, 0, width, height);
  } catch (_) {
    const grad = ctx.createLinearGradient(0, 0, width, height);
    grad.addColorStop(0, '#0a1710');
    grad.addColorStop(1, '#031009');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);
  }

  const darkOverlay = ctx.createLinearGradient(0, 0, 0, height);
  darkOverlay.addColorStop(0, 'rgba(0,0,0,.20)');
  darkOverlay.addColorStop(.3, 'rgba(0,0,0,.12)');
  darkOverlay.addColorStop(1, 'rgba(0,0,0,.28)');
  ctx.fillStyle = darkOverlay;
  ctx.fillRect(0, 0, width, height);

  ctx.save();
  const vignette = ctx.createRadialGradient(width / 2, height / 2, 120, width / 2, height / 2, height * .75);
  vignette.addColorStop(0, 'rgba(255,255,255,0)');
  vignette.addColorStop(1, 'rgba(0,0,0,.35)');
  ctx.fillStyle = vignette;
  ctx.fillRect(0, 0, width, height);
  ctx.restore();
}

function fitText(ctx, text, x, y, maxWidth, fontBase, minSize = 24, family = 'Georgia, Times New Roman, serif', weight = 700) {
  let size = fontBase;
  do {
    ctx.font = `${weight} ${size}px ${family}`;
    if (ctx.measureText(text).width <= maxWidth) break;
    size -= 2;
  } while (size >= minSize);
  ctx.fillText(text, x, y);
}

function drawDecorativeLine(ctx, x1, x2, y) {
  ctx.save();
  ctx.strokeStyle = 'rgba(214,177,84,.85)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x1, y);
  ctx.lineTo(x2, y);
  ctx.stroke();
  ctx.fillStyle = 'rgba(239,212,130,.95)';
  ctx.beginPath();
  ctx.arc((x1 + x2) / 2, y, 4, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawCornerOrnament(ctx, x, y, size, flipX = false, flipY = false) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(flipX ? -1 : 1, flipY ? -1 : 1);
  ctx.strokeStyle = 'rgba(215,178,84,.95)';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(0, size * .45);
  ctx.quadraticCurveTo(0, 0, size * .45, 0);
  ctx.lineTo(size * .82, 0);
  ctx.moveTo(0, size * .68);
  ctx.quadraticCurveTo(size * .12, size * .18, size * .68, 0);
  ctx.moveTo(size * .18, size * .18);
  ctx.quadraticCurveTo(size * .22, size * .04, size * .37, size * .04);
  ctx.stroke();
  ctx.restore();
}

function drawOrnateFrame(ctx, x, y, w, h) {
  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,.35)';
  ctx.shadowBlur = 14;
  drawRoundedRect(ctx, x, y, w, h, 26);
  ctx.fillStyle = 'rgba(9,32,18,.76)';
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.lineWidth = 3;
  ctx.strokeStyle = 'rgba(214,177,84,.92)';
  ctx.stroke();
  drawRoundedRect(ctx, x + 10, y + 10, w - 20, h - 20, 18);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = 'rgba(237,219,150,.65)';
  ctx.stroke();
  drawCornerOrnament(ctx, x + 16, y + 16, 48, false, false);
  drawCornerOrnament(ctx, x + w - 16, y + 16, 48, true, false);
  drawCornerOrnament(ctx, x + 16, y + h - 16, 48, false, true);
  drawCornerOrnament(ctx, x + w - 16, y + h - 16, 48, true, true);
  ctx.restore();
}

function drawShareTable(ctx, rows, division, chave, showChave, width, height) {
  const titleColor = '#e7c46b';
  const titleGlow = '#5f4716';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  ctx.save();
  ctx.shadowColor = titleGlow;
  ctx.shadowBlur = 22;
  ctx.fillStyle = titleColor;
  ctx.font = '700 62px Georgia, Times New Roman, serif';
  ctx.fillText('2° CAMPEONATO DE', width / 2, 150);
  ctx.font = '700 98px Georgia, Times New Roman, serif';
  fitText(ctx, 'SINUCA DE', width / 2, 240, width - 160, 98, 56, 'Georgia, Times New Roman, serif', 700);
  fitText(ctx, 'ENTRE FOLHAS', width / 2, 350, width - 120, 104, 60, 'Georgia, Times New Roman, serif', 700);
  ctx.shadowBlur = 0;
  ctx.restore();

  ctx.fillStyle = '#f0d98a';
  ctx.font = '700 56px Georgia, Times New Roman, serif';
  ctx.fillText(divisionName(division).toUpperCase(), width / 2, 450);
  if (showChave) {
    drawDecorativeLine(ctx, width * .18, width * .82, 495);
    ctx.font = '700 62px Georgia, Times New Roman, serif';
    ctx.fillText(`CHAVE ${String(chave).toUpperCase()}`, width / 2, 535);
  }

  const tableX = 102;
  const tableY = showChave ? 620 : 540;
  const tableW = width - 204;
  const availableH = height - tableY - 120;
  const headerH = 64;
  const rowH = Math.max(44, Math.min(72, Math.floor((availableH - headerH - 16) / Math.max(1, rows.length))));
  const tableH = headerH + rowH * rows.length + 20;

  drawOrnateFrame(ctx, tableX, tableY, tableW, tableH);

  const innerX = tableX + 24;
  const innerY = tableY + 20;
  const innerW = tableW - 48;

  const cols = [
    { label: 'POS', width: 0.12, align: 'center' },
    { label: 'NOME', width: 0.36, align: 'left' },
    { label: 'PTS', width: 0.13, align: 'center' },
    { label: 'VIT', width: 0.12, align: 'center' },
    { label: 'JGS', width: 0.12, align: 'center' },
    { label: 'SB',  width: 0.15, align: 'center' },
  ];
  let accX = innerX;
  cols.forEach(c => {
    c.x = accX;
    c.w = Math.round(innerW * c.width);
    accX += c.w;
  });
  cols[cols.length - 1].w = innerX + innerW - cols[cols.length - 1].x;

  ctx.fillStyle = 'rgba(15,53,28,.72)';
  ctx.fillRect(innerX, innerY, innerW, headerH);
  ctx.strokeStyle = 'rgba(214,177,84,.55)';
  ctx.lineWidth = 1.2;
  ctx.strokeRect(innerX, innerY, innerW, headerH);

  ctx.fillStyle = '#f0d98a';
  ctx.font = '700 23px Georgia, Times New Roman, serif';
  cols.forEach(c => {
    ctx.textAlign = c.align;
    const tx = c.align === 'left' ? c.x + 18 : c.x + c.w / 2;
    ctx.fillText(c.label, tx, innerY + headerH / 2 + 1);
  });

  rows.forEach((row, idx) => {
    const y = innerY + headerH + idx * rowH;
    const isPromotion = row.rank_status === 'promotion';
    const isRelegation = row.rank_status === 'relegation';
    let bg = idx % 2 ? 'rgba(255,255,255,.025)' : 'rgba(255,255,255,.012)';
    if (isPromotion) bg = 'rgba(34,177,76,.28)';
    if (isRelegation) bg = 'rgba(190,48,35,.30)';
    ctx.fillStyle = bg;
    ctx.fillRect(innerX, y, innerW, rowH);

    ctx.strokeStyle = 'rgba(214,177,84,.22)';
    ctx.beginPath();
    ctx.moveTo(innerX, y + rowH);
    ctx.lineTo(innerX + innerW, y + rowH);
    ctx.stroke();
    cols.slice(1).forEach(c => {
      ctx.beginPath();
      ctx.moveTo(c.x, y);
      ctx.lineTo(c.x, y + rowH);
      ctx.stroke();
    });

    ctx.fillStyle = '#f5ecd1';
    const fontSize = Math.max(18, Math.floor(rowH * .44));
    const nameSize = Math.max(17, Math.floor(rowH * .42));
    ctx.font = `700 ${fontSize}px Georgia, Times New Roman, serif`;
    ctx.textAlign = 'center';
    ctx.fillText(String(idx + 1), cols[0].x + cols[0].w / 2, y + rowH / 2 + 1);
    ctx.textAlign = 'left';
    ctx.font = `700 ${nameSize}px Georgia, Times New Roman, serif`;
    ctx.fillText(abbreviateName(row.name, rows.length > 14 ? 16 : 22), cols[1].x + 12, y + rowH / 2 + 1);
    ctx.textAlign = 'center';
    ctx.font = `700 ${fontSize}px Georgia, Times New Roman, serif`;
    [row.points, row.wins, row.played, (row.balls_balance > 0 ? '+' : '') + row.balls_balance].forEach((val, i) => {
      const c = cols[i + 2];
      ctx.fillText(String(val), c.x + c.w / 2, y + rowH / 2 + 1);
    });
  });
}

async function generateShareImage(division, chave, showChave) {
  const rows = (((state.standings || {})[String(division)] || {})[chave] || []);
  if (!rows.length) throw new Error('Não há jogadores nesta tabela para compartilhar.');
  const canvas = document.createElement('canvas');
  canvas.width = 1080;
  canvas.height = 1920;
  const ctx = canvas.getContext('2d');
  await drawShareBackground(ctx, canvas.width, canvas.height);
  drawShareTable(ctx, rows, division, chave, showChave, canvas.width, canvas.height);
  const filename = `classificacao-${division}div${showChave ? '-chave-' + chave : ''}.png`.toLowerCase();
  canvas.toBlob(async blob => {
    if (!blob) throw new Error('Não foi possível gerar a imagem.');
    try {
      const file = new File([blob], filename, {type: 'image/png'});
      if (navigator.canShare && navigator.canShare({files: [file]})) {
        await navigator.share({files: [file], title: 'Classificação do torneio'});
        return;
      }
    } catch (_) {}
    downloadBlob(blob, filename);
  }, 'image/png');
}

function renderFilteredMatches() {
  const filtered = currentFilteredMatches();
  const count = document.getElementById('matches-count');
  if (count) count.textContent = `${filtered.length} partidas`;
  const printButton = document.getElementById('print-filtered-matches');
  if (printButton) printButton.disabled = false;
  renderMatches(document.getElementById('matches'), filtered);
}

function renderMatchesPrompt() {
  const count = document.getElementById('matches-count');
  if (count) count.textContent = '';
  const printButton = document.getElementById('print-filtered-matches');
  if (printButton) printButton.disabled = true;
  document.getElementById('matches').innerHTML = '<div class="empty">Selecione ao menos um filtro para carregar as partidas.</div>';
}

loadPublicState();
