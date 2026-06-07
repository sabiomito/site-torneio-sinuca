async function readImageFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('Não foi possível ler a imagem.'));
    reader.readAsDataURL(file);
  });
}

async function loadImageElement(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Não foi possível carregar a imagem.'));
    img.src = src;
  });
}

async function cropImageFileToJpeg(file, width, height, quality = 0.9) {
  if (!file) return '';
  const src = await readImageFileAsDataUrl(file);
  const img = await loadImageElement(src);
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');

  const targetRatio = width / height;
  const sourceRatio = img.width / img.height;
  let sx = 0, sy = 0, sw = img.width, sh = img.height;

  if (sourceRatio > targetRatio) {
    sw = img.height * targetRatio;
    sx = (img.width - sw) / 2;
  } else {
    sh = img.width / targetRatio;
    sy = (img.height - sh) / 2;
  }

  ctx.fillStyle = '#0b1117';
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, width, height);
  return canvas.toDataURL('image/jpeg', quality);
}
