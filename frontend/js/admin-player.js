let editState = null;
let editPlayer = null;
let photoDataUrl = '';

function getPlayerId() {
  return new URLSearchParams(location.search).get('id') || '';
}

function chaveName(index) {
  let n = Math.max(1, Number(index || 1));
  let s = '';
  while (n) {
    const rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function fillChavesForDivision(select, division) {
  const rule = editState?.config?.rules?.[String(division)] || {key_count: 1};
  const count = Math.max(1, Number(rule.key_count || 1));
  select.innerHTML = '';
  for (let i = 1; i <= count; i++) {
    const ch = chaveName(i);
    select.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(ch)}">${escapeHtml(ch)}</option>`);
  }
}

function fillDivisions() {
  const div = document.getElementById('edit-player-division');
  fillDivisionSelect(div, editState.config.division_count, null);
  div.value = String(editPlayer.division || 1);
  fillChavesForDivision(document.getElementById('edit-player-chave'), div.value);
  document.getElementById('edit-player-chave').value = editPlayer.chave || 'A';
}

async function loadEditor() {
  const msg = document.getElementById('player-edit-message');
  if (!getToken()) {
    location.href = '/admin';
    return;
  }
  try {
    editState = await apiFetch('/admin/state', {admin: true});
    editPlayer = (editState.players || []).find(p => p.player_id === getPlayerId());
    if (!editPlayer) throw new Error('Jogador não encontrado.');
    document.getElementById('edit-player-name').value = editPlayer.name || '';
    document.getElementById('edit-player-message').value = editPlayer.short_message || '';
    document.getElementById('player-photo-preview').src = editPlayer.photo_url || '/img/entre-folhas-logo-transparent.png';
    fillDivisions();
  } catch (err) {
    msg.textContent = err.message;
  }
}

document.getElementById('edit-player-division').addEventListener('change', ev => {
  fillChavesForDivision(document.getElementById('edit-player-chave'), Number(ev.target.value || 1));
});

document.getElementById('player-photo-file').addEventListener('change', async ev => {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  try {
    photoDataUrl = await cropImageFileToJpeg(file, 400, 400, 0.9);
    document.getElementById('player-photo-preview').src = photoDataUrl;
  } catch (err) {
    document.getElementById('player-edit-message').textContent = err.message;
  }
});

document.getElementById('player-edit-form').addEventListener('submit', async ev => {
  ev.preventDefault();
  const msg = document.getElementById('player-edit-message');
  msg.textContent = 'Salvando...';
  try {
    await apiFetch('/admin/update-player', {
      method: 'POST',
      admin: true,
      body: JSON.stringify({
        player_id: getPlayerId(),
        name: document.getElementById('edit-player-name').value,
        short_message: document.getElementById('edit-player-message').value,
        division: Number(document.getElementById('edit-player-division').value || 1),
        chave: document.getElementById('edit-player-chave').value,
        photo_data_url: photoDataUrl,
      })
    });
    msg.textContent = 'Jogador salvo com sucesso.';
    setTimeout(() => location.href = '/admin', 900);
  } catch (err) {
    msg.textContent = err.message;
  }
});

loadEditor();
