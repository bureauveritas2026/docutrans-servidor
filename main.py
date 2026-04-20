import os
import shutil
import tempfile
import zipfile
import re
import time
from lxml import etree
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pdf2docx import Converter
from deep_translator import GoogleTranslator

# ─────────────────────────────────────────────
#  Namespaces OOXML
# ─────────────────────────────────────────────
WORD_NS  = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAW_NS  = "http://schemas.openxmlformats.org/drawingml/2006/main"
PPTX_NS  = "http://schemas.openxmlformats.org/presentationml/2006/main"

# Tags que contienen texto en Word / PowerPoint
TEXT_TAGS = {
    f"{{{WORD_NS}}}t",   # Word: <w:t>
    f"{{{DRAW_NS}}}t",   # DrawingML: <a:t> (shapes en DOCX y PPTX)
}

app = FastAPI(title="DocuTransPro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
#  Servir archivos estáticos del frontend
# ─────────────────────────────────────────────
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Sirve la interfaz web directamente desde Render."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>DocuTransPro API - Online ✅</h1><p>Sube archivos a /translate</p>")

@app.get("/health")
async def health():
    return {"status": "ok"}

# ─────────────────────────────────────────────
#  Motor de traducción
# ─────────────────────────────────────────────
def translate_batch(texts: list[str], source: str, target: str) -> list[str]:
    """Traduce una lista de textos en lotes respetando el límite de la API."""
    if not texts:
        return []

    src = source.lower() if source and source != "auto" else "auto"
    tgt = target.lower()

    translator = GoogleTranslator(source=src, target=tgt)
    results = []

    # Máximo ~4500 chars por llamada para no superar el límite de URL
    MAX_CHARS = 4500
    batch: list[str] = []
    batch_chars = 0
    indices: list[int] = []          # índices en 'texts' que forman el batch actual
    translated: dict[int, str] = {}  # mapa índice → traducción

    def flush_batch():
        if not batch:
            return
        combined = "\n||||\n".join(batch)
        try:
            result = translator.translate(combined)
            parts = result.split("\n||||\n") if result else []
            for j, idx in enumerate(indices):
                translated[idx] = parts[j].strip() if j < len(parts) else texts[idx]
        except Exception:
            for idx in indices:
                translated[idx] = texts[idx]
        batch.clear()
        indices.clear()

    for i, text in enumerate(texts):
        if not text or not text.strip():
            translated[i] = text
            continue
        # Si el texto solo tiene números/símbolos, no traducir
        if not re.search(r'[a-zA-ZÀ-ÿ]', text):
            translated[i] = text
            continue

        t_len = len(text)
        if batch_chars + t_len + 6 > MAX_CHARS:
            flush_batch()
            batch_chars = 0
            time.sleep(0.3)   # pausa cortés con la API gratuita

        batch.append(text)
        indices.append(i)
        batch_chars += t_len + 6

    flush_batch()

    return [translated.get(i, texts[i]) for i in range(len(texts))]


# ─────────────────────────────────────────────
#  Procesador DOCX / PPTX
# ─────────────────────────────────────────────
def _collect_and_replace_xml(xml_bytes: bytes, source: str, target: str) -> bytes:
    """Parsea el XML de un archivo interno, reemplaza el texto y devuelve los bytes modificados."""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return xml_bytes

    nodes = [elem for elem in root.iter() if elem.tag in TEXT_TAGS and elem.text and elem.text.strip()]
    if not nodes:
        return xml_bytes

    originals = [n.text for n in nodes]
    translated = translate_batch(originals, source, target)

    for node, new_text in zip(nodes, translated):
        if new_text:
            node.text = new_text

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def process_office_document(input_path: str, output_path: str, ext: str, source: str, target: str):
    """Lee el DOCX/PPTX como ZIP, traduce solo los XML con texto y reconstruye el archivo."""
    with zipfile.ZipFile(input_path, "r") as zin, \
         zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:

        for item in zin.infolist():
            raw = zin.read(item.filename)

            should_translate = False
            if ext == "docx":
                # Documento principal + headers/footers + cuadros de texto
                if (item.filename == "word/document.xml"
                        or item.filename.startswith("word/header")
                        or item.filename.startswith("word/footer")
                        or (item.filename.startswith("word/") and item.filename.endswith(".xml")
                            and "drawing" not in item.filename)):
                    should_translate = True
            elif ext == "pptx":
                # Todas las diapositivas y notas
                if (item.filename.startswith("ppt/slides/") and item.filename.endswith(".xml")) \
                        or (item.filename.startswith("ppt/notesSlides/") and item.filename.endswith(".xml")):
                    should_translate = True

            if should_translate:
                try:
                    new_raw = _collect_and_replace_xml(raw, source, target)
                    zout.writestr(item, new_raw)
                except Exception:
                    zout.writestr(item, raw)
            else:
                zout.writestr(item, raw)


# ─────────────────────────────────────────────
#  Endpoint de traducción
# ─────────────────────────────────────────────
@app.post("/translate")
async def translate_document(
    file: UploadFile = File(...),
    source_lang: str = Form("auto"),
    target_lang: str = Form("es"),
):
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("pdf", "docx", "pptx"):
        raise HTTPException(status_code=400, detail=f"Formato '{ext}' no soportado. Usa PDF, DOCX o PPTX.")

    temp_dir = tempfile.mkdtemp()
    try:
        # Guardar archivo subido
        input_path = os.path.join(temp_dir, file.filename)
        with open(input_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        # Nombre del archivo de salida
        base_name = file.filename.rsplit(".", 1)[0]
        final_ext  = "docx" if ext == "pdf" else ext
        output_filename = f"{base_name}_traducido.{final_ext}"
        output_path     = os.path.join(temp_dir, output_filename)

        if ext == "pdf":
            # 1. PDF → DOCX (conserva imágenes y layout)
            temp_docx = os.path.join(temp_dir, "converted.docx")
            cv = Converter(input_path)
            cv.convert(temp_docx, start=0, end=None)
            cv.close()
            # 2. Traducir el DOCX generado
            process_office_document(temp_docx, output_path, "docx", source_lang, target_lang)
        else:
            process_office_document(input_path, output_path, ext, source_lang, target_lang)

        return FileResponse(
            path=output_path,
            filename=output_filename,
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    # Nota: no eliminamos temp_dir aquí porque FileResponse aún necesita el archivo.
    # Render limpiará el /tmp automáticamente.
