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

# Configurar CORS para permitir solicitudes desde el frontend (GitHub Pages o Local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, reemplazar "*" con la URL de GitHub Pages
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def register_namespaces(xml_content):
    """Extrae y registra los namespaces del XML para evitar perderlos al guardar"""
    namespaces = dict([node for _, node in ET.iterparse(open(xml_content, 'r', encoding='utf-8') if isinstance(xml_content, str) else xml_content, events=['start-ns'])])
    for key, value in namespaces.items():
        ET.register_namespace(key, value)
    return namespaces

def translate_texts_batch(texts, source_lang, target_lang, batch_size=40):
    if not texts:
        return []
    
    translator = GoogleTranslator(source=source_lang, target=target_lang)
    translated_texts = []
    
    # deep-translator puede manejar listas, pero tiene un límite de 5000 caracteres por petición
    # Así que lo enviamos uno a uno o en lotes pequeños si lo soportara
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        # Por seguridad y límites, traducimos uno a uno dentro del batch en Python
        # deep-translator maneja el límite automáticamente en peticiones individuales
        batch_translated = []
        for t in batch:
            if t and t.strip() and re.search('[a-zA-Z]', t):
                try:
                    res = translator.translate(t)
                    batch_translated.append(res if res else t)
                except Exception as e:
                    print(f"Error traduciendo '{t}': {e}")
                    batch_translated.append(t)
            else:
                batch_translated.append(t)
                
        translated_texts.extend(batch_translated)
        
    return translated_texts

def process_xml_file(zip_ref, xml_path, target_tag, source_lang, target_lang):
    """Extrae, traduce y devuelve el contenido XML modificado"""
    with zip_ref.open(xml_path) as xml_file:
        xml_content = xml_file.read()
        
    # Necesitamos registrar namespaces globales comunes de Office
    ET.register_namespace('w', 'http://schemas.openxmlformats.org/wordprocessingml/2006/main')
    ET.register_namespace('a', 'http://schemas.openxmlformats.org/drawingml/2006/main')
    
    root = ET.fromstring(xml_content)
    
    # Encontrar todos los nodos de texto
    # namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    #               'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
    
    # ElementTree findall necesita el namespace explícito en el tag si usamos la búsqueda estándar,
    # pero podemos iterar sobre todos los elementos y verificar la etiqueta terminada en la etiqueta objetivo.
    
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
    # Copiar el archivo original al destino
    shutil.copy2(input_path, output_path)
    
    # Modificar el archivo ZIP (DOCX/PPTX) en su lugar temporalmente
    temp_dir = tempfile.mkdtemp()
    
    try:
        with zipfile.ZipFile(input_path, 'r') as zin:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if ext == 'docx' and item.filename == 'word/document.xml':
                        modified_xml = process_xml_file(zin, item.filename, 't', source_lang, target_lang) # <w:t>
                        zout.writestr(item, modified_xml)
                    elif ext == 'pptx' and item.filename.startswith('ppt/slides/slide') and item.filename.endswith('.xml'):
                        modified_xml = process_xml_file(zin, item.filename, 't', source_lang, target_lang) # <a:t>
                        zout.writestr(item, modified_xml)
                    else:
                        zout.writestr(item, zin.read(item.filename))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.post("/translate")
async def translate_document(
    file: UploadFile = File(...),
    source_lang: str = Form("auto"),
    target_lang: str = Form("es")
):
    ext = file.filename.split('.')[-1].lower()
    if ext not in ['pdf', 'docx', 'pptx']:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa PDF, DOCX o PPTX.")
        
    # Crear directorio temporal
    temp_dir = tempfile.mkdtemp()
    
    try:
        input_path = os.path.join(temp_dir, file.filename)
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        final_ext = 'docx' if ext == 'pdf' else ext
        output_filename = f"traducido_{file.filename.rsplit('.', 1)[0]}.{final_ext}"
        output_path = os.path.join(temp_dir, output_filename)
        
        if ext == 'pdf':
            # 1. Convertir PDF a DOCX
            temp_docx_path = os.path.join(temp_dir, "temp.docx")
            cv = Converter(input_path)
            cv.convert(temp_docx_path, start=0, end=None)
            cv.close()
            # 2. Traducir el DOCX resultante
            process_office_document(temp_docx_path, output_path, 'docx', source_lang, target_lang)
        else:
            # Traducir DOCX o PPTX directamente
            process_office_document(input_path, output_path, ext, source_lang, target_lang)
            
        # Devolver el archivo. FastAPI FileResponse se encarga de servirlo.
        # En Render.com, necesitamos asegurarnos de que el archivo temporal no se borre antes de ser enviado.
        # FileResponse maneja la limpieza si usamos background tasks, pero para simplicidad, lo dejaremos en el temp.
        # El SO limpiará /tmp periódicamente.
        
        return FileResponse(
            path=output_path, 
            filename=output_filename,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document' if final_ext == 'docx' else 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )

    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))
