let state = null;

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
  fillSelect(document.getElementById('filter-player'), state.players, 'player_id', p => `${p.name} — ${divisionName(p.division)} / Chave ${normalizeChave(p.chave)}`, 'Todos');
  fillDivisionSelect(document.getElementById('filter-division'), state.config.division_count, 'Todas');
  fillChaveSelect(document.getElementById('filter-chave'), 'Todas');
  ['filter-date','filter-place','filter-player','filter-division','filter-chave'].forEach(id => {
    document.getElementById(id).addEventListener('change', renderFilteredMatches);
  });
  document.getElementById('clear-filters').addEventListener('click', () => {
    ['filter-date','filter-place','filter-player','filter-division','filter-chave'].forEach(id => document.getElementById(id).value = '');
    renderFilteredMatches();
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
  };
}

function currentFilteredMatches() {
  return getFilteredMatches(state.matches, currentFilters());
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

function drawShareBackground(ctx, width, height) {
  const grad = ctx.createLinearGradient(0, 0, width, height);
  grad.addColorStop(0, '#020803');
  grad.addColorStop(0.35, '#0b2e16');
  grad.addColorStop(0.68, '#07140e');
  grad.addColorStop(1, '#000000');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, width, height);

  for (let i = 0; i < 24; i++) {
    ctx.save();
    ctx.globalAlpha = 0.10 + Math.random() * 0.10;
    ctx.strokeStyle = i % 3 === 0 ? '#88ff00' : '#18d26b';
    ctx.lineWidth = 4 + Math.random() * 8;
    const y = 130 + Math.random() * (height - 300);
    ctx.beginPath();
    ctx.moveTo(-80, y);
    ctx.lineTo(width + 100, y - 260 + Math.random() * 160);
    ctx.stroke();
    ctx.restore();
  }

  ctx.save();
  ctx.globalAlpha = 0.16;
  ctx.strokeStyle = '#d7a64a';
  ctx.lineWidth = 18;
  ctx.beginPath();
  ctx.moveTo(width * 0.08, height * 0.90);
  ctx.lineTo(width * 0.92, height * 0.15);
  ctx.stroke();
  ctx.restore();

  const balls = [
    [110, 1720, 48, '#f6d34d', '1'], [210, 1780, 48, '#255fe8', '2'], [310, 1715, 48, '#d12e2e', '3'],
    [940, 210, 52, '#111', '8'], [840, 300, 42, '#f3f3f3', ''], [120, 260, 34, '#2fa557', '6']
  ];
  balls.forEach(([x, y, r, color, num]) => {
    const bgrad = ctx.createRadialGradient(x - r * .35, y - r * .45, r * .1, x, y, r);
    bgrad.addColorStop(0, '#ffffff');
    bgrad.addColorStop(.22, color);
    bgrad.addColorStop(1, '#020202');
    ctx.fillStyle = bgrad;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    if (num) {
      ctx.fillStyle = color === '#111' ? '#fff' : '#111';
      ctx.font = `900 ${Math.round(r * .75)}px Arial`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(num, x, y + 1);
    }
  });

  ctx.save();
  ctx.globalAlpha = .55;
  const vignette = ctx.createRadialGradient(width / 2, height * .48, 200, width / 2, height / 2, height * .75);
  vignette.addColorStop(0, 'rgba(0,0,0,0)');
  vignette.addColorStop(1, 'rgba(0,0,0,.78)');
  ctx.fillStyle = vignette;
  ctx.fillRect(0, 0, width, height);
  ctx.restore();
}

function fitText(ctx, text, x, y, maxWidth, fontBase, minSize = 24) {
  let size = fontBase;
  do {
    ctx.font = `900 ${size}px Arial, Helvetica, sans-serif`;
    if (ctx.measureText(text).width <= maxWidth) break;
    size -= 2;
  } while (size >= minSize);
  ctx.fillText(text, x, y);
}

function drawShareTable(ctx, rows, division, chave, showChave, width, height) {
  const margin = 64;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#f5f7f4';
  ctx.shadowColor = 'rgba(0,0,0,.75)';
  ctx.shadowBlur = 18;
  fitText(ctx, '2° CAMPEONATO MUNICIPAL DE SINUCA', width / 2, 100, width - 100, 54, 34);
  ctx.shadowBlur = 0;

  ctx.fillStyle = '#93ff16';
  ctx.font = '900 44px Arial, Helvetica, sans-serif';
  const subtitle = `${divisionName(division).toUpperCase()}${showChave ? ` · CHAVE ${chave}` : ''}`;
  ctx.fillText(subtitle, width / 2, 166);

  const tableX = margin;
  const tableY = 230;
  const tableW = width - margin * 2;
  const footerH = 88;
  const headerH = 58;
  const maxTableH = height - tableY - footerH - 64;
  const rowH = Math.max(36, Math.min(58, Math.floor((maxTableH - headerH) / Math.max(1, rows.length))));
  const actualTableH = headerH + rowH * rows.length;

  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,.65)';
  ctx.shadowBlur = 26;
  drawRoundedRect(ctx, tableX, tableY, tableW, actualTableH, 28);
  ctx.fillStyle = 'rgba(2, 10, 7, .82)';
  ctx.fill();
  ctx.lineWidth = 3;
  ctx.strokeStyle = 'rgba(147,255,22,.45)';
  ctx.stroke();
  ctx.restore();

  const cols = [
    {label: 'POS', x: tableX + 35, w: 70, align: 'center'},
    {label: 'JOGADOR', x: tableX + 100, w: tableW - 410, align: 'left'},
    {label: 'PTS', x: tableX + tableW - 300, w: 62, align: 'center'},
    {label: 'VIT', x: tableX + tableW - 238, w: 62, align: 'center'},
    {label: 'JOG', x: tableX + tableW - 176, w: 62, align: 'center'},
    {label: 'SALDO', x: tableX + tableW - 104, w: 90, align: 'center'},
  ];
  ctx.fillStyle = 'rgba(147,255,22,.22)';
  drawRoundedRect(ctx, tableX, tableY, tableW, headerH, 28);
  ctx.fill();
  ctx.fillStyle = '#cfff71';
  ctx.font = '900 22px Arial, Helvetica, sans-serif';
  cols.forEach(c => {
    ctx.textAlign = c.align;
    ctx.fillText(c.label, c.align === 'left' ? c.x : c.x + c.w / 2, tableY + headerH / 2);
  });

  rows.forEach((row, idx) => {
    const y = tableY + headerH + idx * rowH;
    if (row.rank_status === 'promotion') ctx.fillStyle = 'rgba(34, 214, 112, .36)';
    else if (row.rank_status === 'relegation') ctx.fillStyle = 'rgba(255, 70, 70, .34)';
    else ctx.fillStyle = idx % 2 ? 'rgba(255,255,255,.045)' : 'rgba(255,255,255,.02)';
    ctx.fillRect(tableX + 8, y, tableW - 16, rowH);
    ctx.strokeStyle = 'rgba(255,255,255,.09)';
    ctx.beginPath();
    ctx.moveTo(tableX + 18, y + rowH);
    ctx.lineTo(tableX + tableW - 18, y + rowH);
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.font = `900 ${Math.max(20, Math.floor(rowH * .42))}px Arial, Helvetica, sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText(String(idx + 1), cols[0].x + cols[0].w / 2, y + rowH / 2);

    ctx.textAlign = 'left';
    ctx.font = `900 ${Math.max(19, Math.floor(rowH * .40))}px Arial, Helvetica, sans-serif`;
    ctx.fillText(abbreviateName(row.name, rows.length > 22 ? 18 : 24).toUpperCase(), cols[1].x, y + rowH / 2);

    const vals = [row.points, row.wins, row.played, row.balls_balance];
    ctx.textAlign = 'center';
    vals.forEach((val, i) => ctx.fillText(String(val), cols[i + 2].x + cols[i + 2].w / 2, y + rowH / 2));
  });

  ctx.textAlign = 'center';
  ctx.fillStyle = '#f1f1f1';
  ctx.font = '800 22px Arial, Helvetica, sans-serif';
  ctx.fillText('Verde: classificados · Vermelho: rebaixados · Vitória = 3 pontos · Saldo de bolas como desempate', width / 2, height - 58);
}

async function generateShareImage(division, chave, showChave) {
  const rows = (((state.standings || {})[String(division)] || {})[chave] || []);
  if (!rows.length) throw new Error('Não há jogadores nesta tabela para compartilhar.');
  const canvas = document.createElement('canvas');
  canvas.width = 1080;
  canvas.height = 1920;
  const ctx = canvas.getContext('2d');
  drawShareBackground(ctx, canvas.width, canvas.height);
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
  renderMatches(document.getElementById('matches'), filtered);
}

loadPublicState();
