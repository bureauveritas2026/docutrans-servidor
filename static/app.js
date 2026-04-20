/* ═══════════════════════════════════════
   DocuTransPro — Frontend Logic
═══════════════════════════════════════ */

// ── API endpoint (mismo servidor que sirve la web) ──
const API_URL = '/translate';

// ── DOM refs ──
const dropZone        = document.getElementById('dropZone');
const fileInput       = document.getElementById('fileInput');
const dropContent     = document.getElementById('dropContent');
const fileInfo        = document.getElementById('fileInfo');
const fileIconWrap    = document.getElementById('fileIconWrap');
const fileTypeIcon    = document.getElementById('fileTypeIcon');
const fileNameDisplay = document.getElementById('fileName');
const fileSizeDisplay = document.getElementById('fileSize');
const removeFileBtn   = document.getElementById('removeFileBtn');
const translateBtn    = document.getElementById('translateBtn');
const sourceLang      = document.getElementById('sourceLang');
const targetLang      = document.getElementById('targetLang');
const swapLangs       = document.getElementById('swapLangs');
const statusArea      = document.getElementById('statusArea');
const statusText      = document.getElementById('statusText');
const progressFill    = document.getElementById('progressFill');
const downloadArea    = document.getElementById('downloadArea');
const downloadLink    = document.getElementById('downloadLink');
const downloadLabel   = document.getElementById('downloadLabel');
const newTranslationBtn = document.getElementById('newTranslationBtn');

// ── State ──
let currentFile      = null;
let blobUrl          = null;

// ── Helpers ──
function formatBytes(bytes) {
  if (bytes < 1024)        return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

function setProgress(pct, msg) {
  progressFill.style.width = pct + '%';
  if (msg) statusText.textContent = msg;
}

function resetUI() {
  currentFile = null;
  fileInput.value = '';
  fileInfo.classList.add('hidden');
  dropZone.classList.remove('hidden');
  statusArea.classList.add('hidden');
  downloadArea.classList.add('hidden');
  translateBtn.disabled = true;
  translateBtn.classList.remove('hidden');
  if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
}

// ── File icon helpers ──
const EXT_META = {
  pdf:  { cls: 'pdf',  icon: 'fa-file-pdf',        color: '#ef4444' },
  docx: { cls: 'word', icon: 'fa-file-word',        color: '#2563eb' },
  pptx: { cls: 'ppt',  icon: 'fa-file-powerpoint',  color: '#ea580c' },
};

function applyFileUI(file) {
  const ext  = file.name.split('.').pop().toLowerCase();
  const meta = EXT_META[ext] || { cls: '', icon: 'fa-file', color: '#94a3b8' };

  // Reset classes
  fileIconWrap.className = 'file-icon-wrap ' + meta.cls;
  fileTypeIcon.className = 'fa-solid ' + meta.icon;

  fileNameDisplay.textContent = file.name;
  fileSizeDisplay.textContent = formatBytes(file.size);

  dropZone.classList.add('hidden');
  fileInfo.classList.remove('hidden');
  translateBtn.disabled = false;
  downloadArea.classList.add('hidden');
  statusArea.classList.add('hidden');
}

// ── Handle incoming file ──
function handleFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['pdf', 'docx', 'pptx'].includes(ext)) {
    showToast('Formato no compatible. Usa PDF, DOCX o PPTX.', 'error');
    return;
  }
  currentFile = file;
  applyFileUI(file);
}

// ── Drop zone events ──
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('dragover');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener('change', e => {
  if (e.target.files.length) handleFile(e.target.files[0]);
});

removeFileBtn.addEventListener('click', resetUI);
newTranslationBtn.addEventListener('click', resetUI);

// ── Swap languages ──
swapLangs.addEventListener('click', () => {
  const srcVal = sourceLang.value;
  const tgtVal = targetLang.value;
  // Only swap if source is not "auto"
  if (srcVal === 'auto') return;
  // Set target to source (if option exists)
  const srcOption = [...targetLang.options].find(o => o.value === srcVal);
  const tgtOption = [...sourceLang.options].find(o => o.value === tgtVal);
  if (srcOption) targetLang.value = srcVal;
  if (tgtOption) sourceLang.value = tgtVal;
});

// ── Translation ──
translateBtn.addEventListener('click', async () => {
  if (!currentFile) return;

  // Switch UI to progress mode
  translateBtn.classList.add('hidden');
  downloadArea.classList.add('hidden');
  statusArea.classList.remove('hidden');
  setProgress(5, 'Preparando el documento…');

  // Animate progress while waiting
  const stages = [
    { pct: 15, msg: 'Subiendo archivo al servidor…',      delay: 600  },
    { pct: 30, msg: 'Analizando estructura del documento…', delay: 1800 },
    { pct: 50, msg: 'Extrayendo textos…',                   delay: 3500 },
    { pct: 68, msg: 'Traduciendo contenido…',               delay: 6000 },
    { pct: 85, msg: 'Reconstruyendo el documento…',         delay: 10000 },
  ];
  let stageTimers = stages.map(s => setTimeout(() => setProgress(s.pct, s.msg), s.delay));

  try {
    const formData = new FormData();
    formData.append('file',        currentFile);
    formData.append('source_lang', sourceLang.value || 'auto');
    formData.append('target_lang', targetLang.value || 'es');

    const response = await fetch(API_URL, { method: 'POST', body: formData });

    // Clear fake progress timers
    stageTimers.forEach(clearTimeout);
    setProgress(95, 'Descargando resultado…');

    if (!response.ok) {
      let errMsg = `Error ${response.status}`;
      try { const j = await response.json(); errMsg = j.detail || errMsg; } catch {}
      throw new Error(errMsg);
    }

    const blob = await response.blob();
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    blobUrl = URL.createObjectURL(blob);

    // Determine output filename
    const ext       = currentFile.name.split('.').pop().toLowerCase();
    const baseName  = currentFile.name.slice(0, -(ext.length + 1));
    const finalExt  = ext === 'pdf' ? 'docx' : ext;
    const outName   = `${baseName}_traducido.${finalExt}`;

    downloadLink.href     = blobUrl;
    downloadLink.download = outName;
    downloadLabel.textContent = `Descargar "${outName}"`;

    setProgress(100, '¡Listo!');
    await sleep(350);

    statusArea.classList.add('hidden');
    downloadArea.classList.remove('hidden');
    translateBtn.classList.remove('hidden');
    translateBtn.disabled = false;

  } catch (err) {
    stageTimers.forEach(clearTimeout);
    statusArea.classList.add('hidden');
    translateBtn.classList.remove('hidden');
    translateBtn.disabled = false;
    showToast('Error: ' + err.message, 'error');
    console.error(err);
  }
});

// ── Tiny helpers ──
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function showToast(msg, type = 'info') {
  const t = document.createElement('div');
  t.textContent = msg;
  Object.assign(t.style, {
    position:     'fixed',
    bottom:       '24px',
    left:         '50%',
    transform:    'translateX(-50%)',
    background:   type === 'error' ? '#ef4444' : '#3b82f6',
    color:        '#fff',
    padding:      '12px 24px',
    borderRadius: '12px',
    fontFamily:   'Inter, sans-serif',
    fontSize:     '0.9rem',
    fontWeight:   '600',
    zIndex:       '9999',
    boxShadow:    '0 8px 30px rgba(0,0,0,.4)',
    maxWidth:     '90vw',
    textAlign:    'center',
    transition:   'opacity .3s',
  });
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 350); }, 4000);
}
