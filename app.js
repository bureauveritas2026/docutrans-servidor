// Elementos UI
const translationPanel = document.getElementById('translationPanel');
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileNameDisplay = document.getElementById('fileName');
const removeFileBtn = document.getElementById('removeFileBtn');
const translateBtn = document.getElementById('translateBtn');
const sourceLang = document.getElementById('sourceLang');
const targetLang = document.getElementById('targetLang');
const statusArea = document.getElementById('statusArea');
const statusText = document.getElementById('statusText');
const progressFill = document.getElementById('progressFill');
const downloadArea = document.getElementById('downloadArea');
const downloadLink = document.getElementById('downloadLink');

let currentFile = null;
let translatedBlobUrl = null;
const API_URL = 'https://docutrans-servidor.onrender.com/translate';

document.addEventListener('DOMContentLoaded', () => {});

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => { dropZone.classList.remove('dragover'); });
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleFile(e.target.files[0]);
});

removeFileBtn.addEventListener('click', () => {
    currentFile = null; fileInput.value = ''; fileInfo.classList.add('hidden');
    dropZone.classList.remove('hidden'); translateBtn.classList.add('disabled');
    downloadArea.classList.add('hidden');
});

function handleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    // CORRECCIÓN: Ahora incluimos 'pdf'
    if (!['txt', 'docx', 'pptx', 'pdf'].includes(ext)) {
        alert('Formato no soportado. Por favor sube un archivo PDF, TXT, DOCX o PPTX.');
        return;
    }
    currentFile = file;
    fileNameDisplay.textContent = file.name;
    const icon = fileInfo.querySelector('.file-icon');
    let iconClass = 'fa-file-lines';
    if (ext === 'docx') iconClass = 'fa-file-word';
    else if (ext === 'pptx') iconClass = 'fa-file-powerpoint';
    else if (ext === 'pdf') iconClass = 'fa-file-pdf';
    icon.className = 'file-icon fa-solid ' + iconClass;
    dropZone.classList.add('hidden');
    fileInfo.classList.remove('hidden');
    translateBtn.classList.remove('disabled');
    downloadArea.classList.add('hidden');
}

translateBtn.addEventListener('click', async () => {
    if (!currentFile) return;
    translateBtn.classList.add('hidden');
    statusArea.classList.remove('hidden');
    updateStatus('Procesando en el servidor...', 20);
    try {
        const formData = new FormData();
        formData.append('file', currentFile);
        formData.append('source_lang', sourceLang.value || 'auto');
        formData.append('target_lang', targetLang.value || 'es');
        const response = await fetch(API_URL, { method: 'POST', body: formData });
        if (!response.ok) throw new Error(`Error: ${response.status}`);
        updateStatus('Descargando...', 90);
        const blob = await response.blob();
        if (translatedBlobUrl) URL.revokeObjectURL(translatedBlobUrl);
        translatedBlobUrl = URL.createObjectURL(blob);
        statusArea.classList.add('hidden');
        downloadArea.classList.remove('hidden');
        const ext = currentFile.name.split('.').pop().toLowerCase();
        const nameParts = currentFile.name.split('.');
        nameParts.pop();
        const finalExt = ext === 'pdf' ? 'docx' : ext;
        downloadLink.href = translatedBlobUrl;
        downloadLink.download = `${nameParts.join('.')}_es.${finalExt}`;
    } catch (error) {
        alert('Error: ' + error.message);
        statusArea.classList.add('hidden');
        translateBtn.classList.remove('hidden');
    }
});

function updateStatus(text, progress) {
    statusText.textContent = text;
    progressFill.style.width = `${progress}%`;
}
