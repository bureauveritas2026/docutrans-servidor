import os
import shutil
import tempfile
import zipfile
import re
from xml.etree import ElementTree as ET
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pdf2docx import Converter
from deep_translator import GoogleTranslator

app = FastAPI(title="DocuTransPro API")

# Configuración de CORS para que tu web en GitHub pueda hablar con Render
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Ruta de bienvenida para confirmar que el servidor está vivo"""
    return {
        "status": "online",
        "message": "Servidor DocuTransPro listo. Envía archivos a /translate para procesar."
    }

def translate_texts_batch(texts, source_lang, target_lang, batch_size=40):
    """Motor de traducción por lotes usando Google Translate gratuito"""
    if not texts:
        return []
    
    # CORRECCIÓN: Convertimos a minúsculas para que la librería no falle
    translator = GoogleTranslator(source=source_lang.lower(), target=target_lang.lower())
    translated_texts = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        batch_translated = []
        for t in batch:
            if t and t.strip() and re.search('[a-zA-Z]', t):
                try:
                    res = translator.translate(t)
                    batch_translated.append(res if res else t)
                except Exception:
                    batch_translated.append(t)
            else:
                batch_translated.append(t)
        translated_texts.extend(batch_translated)
        
    return translated_texts

def process_xml_file(zip_ref, xml_path, target_tag, source_lang, target_lang):
    """Procesa los archivos XML internos de Word y PowerPoint para traducir el texto sin romper el diseño"""
    with zip_ref.open(xml_path) as xml_file:
        xml_content = xml_file.read()
    
    # Registramos namespaces comunes para evitar errores de formato
    ET.register_namespace('w', 'http://schemas.openxmlformats.org/wordprocessingml/2006/main')
    ET.register_namespace('a', 'http://schemas.openxmlformats.org/drawingml/2006/main')
    
    root = ET.fromstring(xml_content)
    valid_nodes = []
    texts_to_translate = []
    
    for elem in root.iter():
        if elem.tag.endswith(target_tag) and elem.text:
            valid_nodes.append(elem)
            texts_to_translate.append(elem.text)
            
    if texts_to_translate:
        translated_texts = translate_texts_batch(texts_to_translate, source_lang, target_lang)
        for i, node in enumerate(valid_nodes):
            if i < len(translated_texts):
                node.text = translated_texts[i]
                
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def process_office_document(input_path, output_path, ext, source_lang, target_lang):
    """Maneja la apertura y reconstrucción del archivo DOCX o PPTX (archivos ZIP)"""
    shutil.copy2(input_path, output_path)
    
    with zipfile.ZipFile(input_path, 'r') as zin:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                # Procesar Word
                if ext == 'docx' and item.filename == 'word/document.xml':
                    modified_xml = process_xml_file(zin, item.filename, 't', source_lang, target_lang)
                    zout.writestr(item, modified_xml)
                # Procesar PowerPoint (diapositivas)
                elif ext == 'pptx' and item.filename.startswith('ppt/slides/slide') and item.filename.endswith('.xml'):
                    modified_xml = process_xml_file(zin, item.filename, 't', source_lang, target_lang)
                    zout.writestr(item, modified_xml)
                else:
                    zout.writestr(item, zin.read(item.filename))

@app.post("/translate")
async def translate_document(
    file: UploadFile = File(...),
    source_lang: str = Form("auto"),
    target_lang: str = Form("es")
):
    """Endpoint principal que recibe PDF, Word o PPT y los traduce"""
    ext = file.filename.split('.')[-1].lower()
    temp_dir = tempfile.mkdtemp()
    
    try:
        input_path = os.path.join(temp_dir, file.filename)
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        final_ext = 'docx' if ext == 'pdf' else ext
        output_filename = f"traducido_{file.filename.rsplit('.', 1)[0]}.{final_ext}"
        output_path = os.path.join(temp_dir, output_filename)
        
        # LÓGICA ESPECIAL PARA PDF
        if ext == 'pdf':
            temp_docx_path = os.path.join(temp_dir, "temp.docx")
            # Convertimos el PDF a Word manteniendo todo el diseño
            cv = Converter(input_path)
            cv.convert(temp_docx_path, start=0, end=None)
            cv.close()
            # Ahora traducimos ese Word resultante
            process_office_document(temp_docx_path, output_path, 'docx', source_lang, target_lang)
        else:
            # Procesar directamente si ya es Word o PowerPoint
            process_office_document(input_path, output_path, ext, source_lang, target_lang)
            
        return FileResponse(
            path=output_path, 
            filename=output_filename,
            media_type='application/octet-stream'
        )

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
