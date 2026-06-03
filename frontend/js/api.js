const API_BASE_URL = (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL || '').replace(/\/$/, '');

function getToken() {
  return localStorage.getItem('sinuca_admin_token') || '';
}

function setToken(token) {
  localStorage.setItem('sinuca_admin_token', token);
}

function clearToken() {
  localStorage.removeItem('sinuca_admin_token');
}

function apiUrl(path, isAdmin = false) {
  if (!API_BASE_URL) {
    throw new Error('API_BASE_URL não configurada. No deploy, o GitHub Actions cria o frontend/config.js automaticamente.');
  }
  const base = API_BASE_URL.startsWith('http') ? API_BASE_URL : `${location.origin}${API_BASE_URL}`;
  const url = new URL(`${base}${path}`);
  if (isAdmin) {
    const token = getToken();
    if (token) url.searchParams.set('token', token);
  }
  return url.toString();
}

async function apiFetch(path, options = {}) {
  const isAdmin = Boolean(options.admin);
  const fetchOptions = Object.assign({}, options);
  delete fetchOptions.admin;

  // Não enviamos Content-Type e Authorization por padrão para evitar preflight/CORS
  // quando o navegador acessa diretamente a Lambda Function URL.
  fetchOptions.headers = Object.assign({}, options.headers || {});

  try {
    const resp = await fetch(apiUrl(path, isAdmin), fetchOptions);
    const text = await resp.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch (_) { data = {}; }
    if (!resp.ok) {
      const error = new Error(data.error || `Erro ${resp.status}`);
      error.status = resp.status;
      error.data = data;
      throw error;
    }
    return data;
  } catch (err) {
    if (err instanceof TypeError && String(err.message).toLowerCase().includes('fetch')) {
      throw new Error('Não consegui acessar a API. Verifique se o deploy terminou, se o config.js aponta para /api ou para a URL da Lambda, e se a distribuição do CloudFront já atualizou.');
    }
    throw err;
  }
}

function fmtDate(value) {
  if (!value) return 'Sem data';
  const [y, m, d] = value.split('-');
  if (!y || !m || !d) return value;
  return `${d}/${m}/${y}`;
}

function divisionName(number) {
  return `${number}ª Divisão`;
}

function normalizeChaveLabel(value) {
  return String(value || 'A').trim().toUpperCase() || 'A';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function groupBy(items, keyFn) {
  return items.reduce((acc, item) => {
    const key = keyFn(item);
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});
}

function matchResultText(match) {
  if (!match.is_finished) return '<span class="badge pending">Pendente</span>';
  const p1Winner = match.winner_id === match.player1_id;
  const p2Winner = match.winner_id === match.player2_id;
  return `<span class="score"><span class="${p1Winner ? 'winner' : ''}">${escapeHtml(match.player1_name)} ${match.balls_p1 || 0}</span> x <span class="${p2Winner ? 'winner' : ''}">${match.balls_p2 || 0} ${escapeHtml(match.player2_name)}</span></span>`;
}

function getFilteredMatches(matches, filters) {
  return matches.filter(match => {
    if (filters.date && match.date !== filters.date) return false;
    if (filters.place && match.place_id !== filters.place) return false;
    if (filters.player && match.player1_id !== filters.player && match.player2_id !== filters.player) return false;
    if (filters.division && String(match.division) !== String(filters.division)) return false;
    if (filters.chave && normalizeChaveLabel(match.chave) !== normalizeChaveLabel(filters.chave)) return false;
    if (filters.round && match.round_id !== filters.round) return false;
    return true;
  });
}


function statusText(rankStatus) {
  if (rankStatus === 'promotion') return 'Classificado';
  if (rankStatus === 'relegation') return 'Rebaixado';
  return '';
}

function abbreviateName(name, maxLen = 22) {
  const cleaned = String(name || '').replace(/\s+/g, ' ').trim();
  if (cleaned.length <= maxLen) return cleaned;
  const parts = cleaned.split(' ');
  if (parts.length === 1) return cleaned.slice(0, Math.max(3, maxLen - 1)) + '…';
  const first = parts[0];
  const last = parts[parts.length - 1];
  const middle = parts.slice(1, -1).map(p => p[0] ? `${p[0].toUpperCase()}.` : '').join(' ');
  let compact = [first, middle, last].filter(Boolean).join(' ');
  if (compact.length <= maxLen) return compact;
  compact = [first, last].filter(Boolean).join(' ');
  if (compact.length <= maxLen) return compact;
  return compact.slice(0, Math.max(3, maxLen - 1)) + '…';
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1200);
}

function matchPlainResult(match) {
  if (!match.is_finished) return '';
  const p1 = `${match.player1_name || ''} ${match.balls_p1 || 0}`;
  const p2 = `${match.balls_p2 || 0} ${match.player2_name || ''}`;
  return `${p1} x ${p2}`;
}


function printableMatchRow(match) {
  const result = matchPlainResult(match);
  const blank = '<span class="blank-score"></span> x <span class="blank-score"></span>';
  const roundText = `${divisionName(match.division)}${match.chave ? ` / Chave ${escapeHtml(normalizeChaveLabel(match.chave))}` : ''}${match.round_number ? ` / Rodada ${escapeHtml(match.round_number)}` : ''}`;
  return `<tr>
    <td class="col-date">${escapeHtml(fmtDate(match.date))}</td>
    <td class="col-time">${escapeHtml(match.time || '')}</td>
    <td class="col-local">${escapeHtml(match.place_name || 'Sem local')}</td>
    <td class="col-round">${roundText}</td>
    <td class="col-player player-left"><strong>${escapeHtml(match.player1_name)}</strong></td>
    <td class="col-result">${result ? escapeHtml(result.replace(/^.*? /,'')) : blank}</td>
    <td class="col-player player-right"><strong>${escapeHtml(match.player2_name)}</strong></td>
  </tr>`;
}

function openMatchesPrintWindow(matches, title = 'Lista de jogos', subtitle = '') {
  const list = [...(matches || [])].sort((a, b) =>
    String(a.date || '').localeCompare(String(b.date || '')) ||
    String(a.time || '').localeCompare(String(b.time || '')) ||
    String(a.place_name || '').localeCompare(String(b.place_name || '')) ||
    String(a.round_number || '').localeCompare(String(b.round_number || ''))
  );
  const pages = [];
  for (let i = 0; i < list.length; i += 24) pages.push(list.slice(i, i + 24));
  const pagesHtml = (pages.length ? pages : [[]]).map((page, pageIdx) => `
    <section class="print-page">
      <header class="print-header">
        <h1>${escapeHtml(title)}</h1>
        <p>${escapeHtml(subtitle || 'Jogos exibidos no filtro atual')}</p>
      </header>
      <table>
        <thead><tr>
          <th class="col-date">Data</th>
          <th class="col-time">Hora</th>
          <th class="col-local">Local</th>
          <th class="col-round">Divisão / chave / rodada</th>
          <th class="col-player">Jogador 1</th>
          <th class="col-result">Resultado</th>
          <th class="col-player">Jogador 2</th>
        </tr></thead>
        <tbody>${page.length ? page.map((m) => printableMatchRow(m)).join('') : '<tr><td colspan="7" class="empty-print">Nenhum jogo encontrado.</td></tr>'}</tbody>
      </table>
      <footer>
        <div>2° campeonato municipal de sinuca · Lista de jogos · Página ${pageIdx + 1}/${Math.max(1, pages.length)}</div>
        <div>Vitória = 3 pontos · vencedor recebe 7 bolas</div>
      </footer>
    </section>
  `).join('');

  const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>
    <style>
      @page { size: A4 portrait; margin: 8mm; }
      * { box-sizing: border-box; }
      html, body { margin: 0; padding: 0; background: #fff; color: #111; font-family: Arial, Helvetica, sans-serif; }
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .print-page { page-break-after: always; break-after: page; width: 100%; overflow: hidden; }
      .print-page:last-child { page-break-after: auto; break-after: auto; }
      .print-header { border-bottom: 2px solid #111; padding-bottom: 5px; margin-bottom: 6px; }
      h1 { margin: 0 0 2px; font-size: 18px; text-transform: uppercase; letter-spacing: .4px; }
      p { margin: 0; font-size: 10px; color: #333; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 10px; }
      th, td { border: 1px solid #222; padding: 3px 4px; vertical-align: middle; height: 10.2mm; }
      th { background: #efefef; text-transform: uppercase; font-size: 8.6px; line-height: 1.1; }
      .col-date { width: 14%; }
      .col-time { width: 8%; text-align: center; }
      .col-local { width: 18%; }
      .col-round { width: 18%; }
      .col-player { width: 17%; }
      .col-result { width: 8%; text-align: center; white-space: nowrap; }
      .player-left { text-align: right; }
      .player-right { text-align: left; }
      .blank-score { display: inline-block; width: 16px; border-bottom: 1.8px solid #111; height: 10px; vertical-align: middle; margin: 0 1px; }
      footer { display: flex; justify-content: space-between; gap: 8px; margin-top: 4px; font-size: 9px; color: #333; }
      .empty-print { text-align: center; padding: 22px; font-size: 12px; }
      @media screen {
        body { background: #d9d9d9; padding: 16px; }
        .print-page { background: #fff; width: 194mm; min-height: 281mm; margin: 0 auto 14px; padding: 0; box-shadow: 0 4px 22px rgba(0,0,0,.22); }
      }
      @media print {
        body { background: #fff; padding: 0; }
        .print-page { margin: 0; box-shadow: none; }
      }
    </style></head><body>${pagesHtml}<script>setTimeout(() => window.print(), 250);<\/script></body></html>`;

  const win = window.open('', '_blank');
  if (!win) {
    alert('O navegador bloqueou a janela de impressão. Permita pop-ups para gerar o PDF/lista de impressão.');
    return;
  }
  win.document.open();
  win.document.write(html);
  win.document.close();
}

function fillSelect(select, items, valueKey, labelKey, firstLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${escapeHtml(firstLabel)}</option>`;
  items.forEach(item => {
    const value = item[valueKey];
    const label = typeof labelKey === 'function' ? labelKey(item) : item[labelKey];
    select.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`);
  });
  if ([...select.options].some(opt => opt.value === current)) select.value = current;
}

function fillDivisionSelect(select, count, firstLabel = null) {
  select.innerHTML = firstLabel === null ? '' : `<option value="">${escapeHtml(firstLabel)}</option>`;
  for (let i = 1; i <= count; i++) {
    select.insertAdjacentHTML('beforeend', `<option value="${i}">${i}ª Divisão</option>`);
  }
}

function renderMatches(container, matches) {
  if (!matches.length) {
    container.innerHTML = '<div class="empty">Nenhuma partida encontrada.</div>';
    return;
  }
  const byDate = groupBy(matches, m => m.date || 'Sem data');
  const html = Object.keys(byDate).sort().map(date => {
    const dayMatches = byDate[date];
    const byPlace = groupBy(dayMatches, m => m.place_name || 'Sem local');
    const placesHtml = Object.keys(byPlace).sort().map(place => {
      const rows = byPlace[place].sort((a,b) => String(a.time).localeCompare(String(b.time))).map(match => `
        <div class="match-row ${match.is_finished ? 'finished' : ''}">
          <div class="match-main">
            <span class="pill">${divisionName(match.division)} · Chave ${escapeHtml(normalizeChaveLabel(match.chave))} · Rodada ${escapeHtml(match.round_number || '-')}</span>
            <span class="time">${escapeHtml(match.time || '--:--')}</span>
            <strong>${escapeHtml(match.player1_name)}</strong>
            <span class="versus">x</span>
            <strong>${escapeHtml(match.player2_name)}</strong>
          </div>
          <div class="match-status">${matchResultText(match)}</div>
        </div>
      `).join('');
      return `<article class="match-group"><h3>${fmtDate(date)} · ${escapeHtml(place)}</h3><div class="matches-list">${rows}</div></article>`;
    }).join('');
    return placesHtml;
  }).join('');
  container.innerHTML = `<div class="match-groups">${html}</div>`;
}
