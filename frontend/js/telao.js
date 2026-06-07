let telaoState = null;
const TV_REFRESH_MS = 60000;

function normalizeChaveTv(value) {
  return String(value || 'A').trim().toUpperCase() || 'A';
}

function gatherStandingsTables(state) {
  const cards = [];
  for (let d = 1; d <= (state?.config?.division_count || 0); d++) {
    const chaves = state.standings[String(d)] || {};
    const chaveNames = Object.keys(chaves).sort();
    const showChave = chaveNames.length > 1;
    chaveNames.forEach(ch => {
      cards.push({ division: d, chave: ch, showChave, rows: chaves[ch] || [] });
    });
  }
  return cards.filter(c => c.rows.length);
}

function bestGrid(count, width, height) {
  const gap = 18;
  const header = 110;
  const baseRatio = 0.92; // width / height of one telão card
  let best = { cols: 1, rows: count || 1, score: -1, cardW: width, cardH: height - header };
  for (let cols = 1; cols <= Math.max(1, count); cols++) {
    const rows = Math.ceil(count / cols);
    const availW = width - gap * (cols + 1);
    const availH = height - header - gap * (rows + 1);
    const cellW = availW / cols;
    const cellH = availH / rows;
    const useW = Math.min(cellW, cellH * baseRatio);
    const useH = useW / baseRatio;
    const score = useW * useH;
    if (useW > 0 && useH > 0 && score > best.score) {
      best = { cols, rows, score, cardW: useW, cardH: useH };
    }
  }
  return best;
}

function renderTelaoTable(rows) {
  return `<div class="telao-table-wrap"><table class="telao-table"><thead><tr>
    <th>#</th><th>Jogador</th><th>Pts</th><th>Vit</th><th>Jgs</th><th>B+</th><th>B-</th><th>Saldo</th><th>Situação</th>
  </tr></thead><tbody>
    ${rows.map((row, idx) => {
      const cls = row.rank_status || '';
      const st = row.rank_status === 'promotion' ? 'Classificado' : row.rank_status === 'relegation' ? 'Rebaixado' : '—';
      return `<tr class="${escapeHtml(cls)}"><td>${idx+1}</td><td>${escapeHtml(row.name)}</td><td><strong>${row.points}</strong></td><td>${row.wins}</td><td>${row.played}</td><td>${row.balls_for}</td><td>${row.balls_against}</td><td><strong>${row.balls_balance}</strong></td><td>${st}</td></tr>`;
    }).join('')}
  </tbody></table></div>`;
}

function renderTelao() {
  const grid = document.getElementById('telao-grid');
  const cards = gatherStandingsTables(telaoState);
  if (!cards.length) {
    grid.innerHTML = `<section class="card empty"><h2>Nenhum torneio criado ainda</h2><p>Aguardando cadastros e resultados.</p></section>`;
    return;
  }
  const cfg = bestGrid(cards.length, window.innerWidth, window.innerHeight);
  grid.style.gridTemplateColumns = `repeat(${cfg.cols}, 1fr)`;
  document.documentElement.style.setProperty('--telao-card-height', `${Math.floor(cfg.cardH)}px`);
  grid.innerHTML = cards.map(card => `
    <section class="card standings-card telao-card">
      <div class="section-title telao-title">
        <h2>${divisionName(card.division)}${card.showChave ? ` · Chave ${escapeHtml(normalizeChaveTv(card.chave))}` : ''}</h2>
        <span>${card.rows.length} jogadores</span>
      </div>
      ${renderTelaoTable(card.rows)}
    </section>
  `).join('');
}

async function loadTelaoState() {
  try {
    telaoState = await apiFetch('/state');
    renderTelao();
    const stamp = new Date();
    document.getElementById('telao-last-update').textContent = `Atualizado às ${stamp.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'})}`;
  } catch (err) {
    document.getElementById('telao-grid').innerHTML = `<section class="card empty">${escapeHtml(err.message || 'Falha ao carregar o telão.')}</section>`;
  }
}

window.addEventListener('resize', () => { if (telaoState) renderTelao(); });
window.addEventListener('DOMContentLoaded', () => {
  loadTelaoState();
  setInterval(loadTelaoState, TV_REFRESH_MS);
});
