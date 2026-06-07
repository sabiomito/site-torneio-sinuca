let sponsorState = null;
let sponsor = null;
let squareDataUrl = '';
let rectDataUrl = '';

function getSponsorId() {
  return new URLSearchParams(location.search).get('id') || '';
}

async function loadSponsorEditor() {
  const msg = document.getElementById('sponsor-edit-message');
  if (!getToken()) {
    location.href = '/admin';
    return;
  }
  try {
    sponsorState = await apiFetch('/admin/state', {admin: true});
    sponsor = (sponsorState.sponsors || []).find(s => s.sponsor_id === getSponsorId());
    if (!sponsor) throw new Error('Patrocinador não encontrado.');
    document.getElementById('edit-sponsor-name').value = sponsor.name || '';
    if (sponsor.square_image_url) document.getElementById('sponsor-square-preview').src = sponsor.square_image_url;
    if (sponsor.rect_image_url) document.getElementById('sponsor-rect-preview').src = sponsor.rect_image_url;
  } catch (err) {
    msg.textContent = err.message;
  }
}

document.getElementById('sponsor-square-file').addEventListener('change', async ev => {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  try {
    squareDataUrl = await cropImageFileToJpeg(file, 400, 400, 0.9);
    document.getElementById('sponsor-square-preview').src = squareDataUrl;
  } catch (err) {
    document.getElementById('sponsor-edit-message').textContent = err.message;
  }
});

document.getElementById('sponsor-rect-file').addEventListener('change', async ev => {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  try {
    rectDataUrl = await cropImageFileToJpeg(file, 1200, 400, 0.9);
    document.getElementById('sponsor-rect-preview').src = rectDataUrl;
  } catch (err) {
    document.getElementById('sponsor-edit-message').textContent = err.message;
  }
});

document.getElementById('sponsor-edit-form').addEventListener('submit', async ev => {
  ev.preventDefault();
  const msg = document.getElementById('sponsor-edit-message');
  msg.textContent = 'Salvando...';
  try {
    await apiFetch('/admin/sponsor', {
      method: 'POST',
      admin: true,
      body: JSON.stringify({
        sponsor_id: getSponsorId(),
        name: document.getElementById('edit-sponsor-name').value,
        square_image_data_url: squareDataUrl,
        rect_image_data_url: rectDataUrl,
      })
    });
    msg.textContent = 'Patrocinador salvo com sucesso.';
    setTimeout(() => location.href = '/admin', 900);
  } catch (err) {
    msg.textContent = err.message;
  }
});

loadSponsorEditor();
