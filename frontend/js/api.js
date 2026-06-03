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

function printableMatchRow(match, idx) {
  const result = matchPlainResult(match);
  const blank = '<span class="blank-score"></span> x <span class="blank-score"></span>';
  return `<tr>
    <td class="col-num">${idx + 1}</td>
    <td>${escapeHtml(fmtDate(match.date))}</td>
    <td>${escapeHtml(match.time || '')}</td>
    <td>${escapeHtml(match.place_name || 'Sem local')}</td>
    <td>${escapeHtml(divisionName(match.division))}${match.chave ? ` / Chave ${escapeHtml(normalizeChaveLabel(match.chave))}` : ''}${match.round_number ? ` / Rodada ${escapeHtml(match.round_number)}` : ''}</td>
    <td><strong>${escapeHtml(match.player1_name)}</strong> x <strong>${escapeHtml(match.player2_name)}</strong></td>
    <td>${result ? escapeHtml(result) : blank}</td>
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
        <div>
          <h1>${escapeHtml(title)}</h1>
          <p>${escapeHtml(subtitle || 'Jogos exibidos no filtro atual')}</p>
        </div>
        <div class="print-page-count">Página ${pageIdx + 1}/${Math.max(1, pages.length)}</div>
      </header>
      <table>
        <thead><tr>
          <th>Nº</th><th>Data</th><th>Hora</th><th>Local</th><th>Div./chave</th><th>Jogo</th><th>Resultado</th>
        </tr></thead>
        <tbody>${page.length ? page.map((m, idx) => printableMatchRow(m, pageIdx * 24 + idx)).join('') : '<tr><td colspan="7" class="empty-print">Nenhum jogo encontrado.</td></tr>'}</tbody>
      </table>
      <footer>2° campeonato municipal de sinuca · vitória = 3 pontos · vencedor recebe 7 bolas</footer>
    </section>
  `).join('');

  const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>
    <style>
      @page { size: A4; margin: 10mm; }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; }
      .print-page { page-break-after: always; min-height: 277mm; display: flex; flex-direction: column; }
      .print-page:last-child { page-break-after: auto; }
      .print-header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #111; padding-bottom: 8px; margin-bottom: 8px; }
      h1 { margin: 0 0 3px; font-size: 22px; text-transform: uppercase; }
      p { margin: 0; font-size: 12px; color: #333; }
      .print-page-count { font-size: 12px; font-weight: 700; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 11.5px; }
      th, td { border: 1px solid #222; padding: 4px 5px; vertical-align: middle; height: 31px; }
      th { background: #e8e8e8; text-transform: uppercase; font-size: 9.5px; }
      .col-num { width: 28px; text-align: center; font-weight: 700; }
      th:nth-child(2), td:nth-child(2) { width: 62px; }
      th:nth-child(3), td:nth-child(3) { width: 42px; text-align: center; }
      th:nth-child(4), td:nth-child(4) { width: 86px; }
      th:nth-child(5), td:nth-child(5) { width: 88px; }
      th:nth-child(7), td:nth-child(7) { width: 96px; text-align: center; }
      .blank-score { display: inline-block; width: 32px; border-bottom: 2px solid #111; height: 14px; }
      footer { margin-top: auto; padding-top: 6px; font-size: 10px; text-align: center; color: #333; }
      .empty-print { text-align: center; padding: 22px; font-size: 14px; }
      @media screen { body { background: #ddd; padding: 18px; } .print-page { background: #fff; margin: 0 auto 18px; padding: 10mm; width: 210mm; min-height: 297mm; box-shadow: 0 4px 28px rgba(0,0,0,.25); } }
    </style></head><body>${pagesHtml}<script>setTimeout(() => window.print(), 350);<\/script></body></html>`;

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
