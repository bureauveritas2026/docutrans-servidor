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

// Estado
let currentFile = null;
let translatedBlobUrl = null;

// ¡AQUÍ ESTÁ LA URL DE TU BACKEND EN RENDER!
const API_URL = 'https://docutrans-servidor.onrender.com/translate';
// Inicialización
document.addEventListener('DOMContentLoaded', () => {
    // La UI carga directamente el panel de traducción
});


// Event Listeners Archivos
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
});

removeFileBtn.addEventListener('click', () => {
    currentFile = null;
    fileInput.value = '';
    fileInfo.classList.add('hidden');
    dropZone.classList.remove('hidden');
    translateBtn.classList.add('disabled');
    downloadArea.classList.add('hidden');
});

function handleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['txt', 'docx', 'pptx', 'pdf'].includes(ext)) {
        alert('Formato no soportado. Por favor sube un archivo PDF, TXT, DOCX o PPTX.');
        return;
    }
    
    currentFile = file;
    fileNameDisplay.textContent = file.name;
    
    // Cambiar icono según tipo
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

// Traducción
translateBtn.addEventListener('click', async () => {
    if (!currentFile) return;

    // UI Updates
    translateBtn.classList.add('hidden');
    statusArea.classList.remove('hidden');
    updateStatus('Subiendo documento al servidor y procesando...', 20);

    try {
        const formData = new FormData();
        formData.append('file', currentFile);
        formData.append('source_lang', sourceLang.value || 'auto');
        formData.append('target_lang', targetLang.value || 'es');

        const response = await fetch(API_URL, {
            method: 'POST',
            body: formData
            // No establecemos Content-Type, fetch lo hace automáticamente con el boundary de FormData
        });

        if (!response.ok) {
            const errBody = await response.text();
            throw new Error(`Error del servidor: ${response.status} - ${errBody}`);
        }

        updateStatus('Descargando documento traducido...', 90);
        
        const blob = await response.blob();
        
        // Limpiar URL anterior si existe
        if (translatedBlobUrl) {
            URL.revokeObjectURL(translatedBlobUrl);
        }
        
        translatedBlobUrl = URL.createObjectURL(blob);

        // Éxito
        statusArea.classList.add('hidden');
        downloadArea.classList.remove('hidden');
        
        // Configurar enlace de descarga
        const ext = currentFile.name.split('.').pop().toLowerCase();
        const nameParts = currentFile.name.split('.');
        nameParts.pop(); // quitar extension original
        
        // Si subió un PDF, el backend devuelve un DOCX
        const finalExt = ext === 'pdf' ? 'docx' : ext;
        
        downloadLink.href = translatedBlobUrl;
        downloadLink.download = `${nameParts.join('.')}_es.${finalExt}`;
        
    } catch (error) {
        console.error(error);
        alert('Error durante la traducción: ' + error.message);
        statusArea.classList.add('hidden');
        translateBtn.classList.remove('hidden');
    }
});

function updateStatus(text, progress) {
    statusText.textContent = text;
    progressFill.style.width = `${progress}%`;
}


