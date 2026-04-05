import logging
import zipfile
import io
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString
import re

logger = logging.getLogger(__name__)

class ConverterEngine:
    """Motor de conversión nativo hacia KEPUB."""
    
    def __init__(self):
        pass
        
    def convert_to_kepub(self, input_path: str):
        if not input_path.lower().endswith('.epub') or not zipfile.is_zipfile(input_path):
            raise ValueError(f"Extensión inválida o archivo ilegible/corrupto: {input_path}")
            
        original_path = Path(input_path)
        
        # Evitar crear archivo.kepub.kepub.epub si ya trae la extensión
        if str(original_path).lower().endswith('.kepub.epub'):
            target_path = original_path
        else:
            target_path = original_path.with_suffix('.kepub.epub')
            
        if original_path != target_path:
            import shutil
            # Ética de Formato: Cero perturbación al archivo origen. Se crea una copia integral.
            shutil.copy2(original_path, target_path)
        
        logger.info(f"Iniciando conversión KEPUB operando sobre la copia: {target_path.name}")
        
        # Usamos un buffer de memoria para reempaquetar el ZIP (ya que zipfile no permite in-place)
        buffer = io.BytesIO()
        
        # Abrimos ÚNICAMENTE la copia para leer y enviamos sus piezas procesadas al buffer
        with zipfile.ZipFile(target_path, 'r') as zin, \
             zipfile.ZipFile(buffer, 'w') as zout:
             
            # El archivo mimetype debe ser el primero y estar sin comprimir
            if 'mimetype' in zin.namelist():
                zout.writestr('mimetype', zin.read('mimetype'), compress_type=zipfile.ZIP_STORED)
                
            for item in zin.infolist():
                if item.filename == 'mimetype':
                    continue
                    
                content = zin.read(item.filename)
                
                # Procesar HTMLs inyectando Kobo Spans
                if item.filename.lower().endswith(('.html', '.xhtml', '.htm')):
                    try:
                        content = self._inject_kobo_spans(content, item.filename)
                    except Exception as e:
                        logger.error(f"Error parseando {item.filename}: {e}")
                        
                zout.writestr(item, content, compress_type=zipfile.ZIP_DEFLATED)
                
        # Descargar el payload reempaquetado encima de la copia y cerrar
        with open(target_path, 'wb') as f:
            f.write(buffer.getvalue())
            
        logger.info(f"Conversión KEPUB completada: {target_path.name}")

    def _inject_kobo_spans(self, html_bytes: bytes, filename: str) -> bytes:
        # Detectar el charset o defaultear a utf-8
        try:
            texto = html_bytes.decode('utf-8')
        except UnicodeDecodeError:
            texto = html_bytes.decode('latin-1')
            
        soup = BeautifulSoup(texto, 'html.parser')
        
        if not soup.body:
            return html_bytes
            
        # Generamos un ID base determinista para el capítulo para validación kobo coherente
        chapter_idx = abs(hash(filename)) % 10000
        sentence_idx = 1
        
        # Iteramos los elementos de flujo de texto más probables en un ebook
        for element in soup.body.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'td', 'span', 'a', 'em', 'strong', 'i', 'b']):
            if element.name in ['script', 'style']:
                continue
                
            if 'koboSpan' in element.get('class', []):
                continue
                
            # Procesamos hijas directas de texto
            for child in list(element.children):
                if isinstance(child, NavigableString):
                    text_val = str(child)
                    if not text_val.strip():
                        continue
                        
                    # Romper texto por frases (terminador de punto, signo interr. o exclam.) y atrapar los espacios en blanco
                    parts = re.split(r'(?<=[.!?])(\s+)', text_val)
                    
                    new_nodes = []
                    for part in parts:
                        if not part:
                            continue
                        if part.isspace():
                            new_nodes.append(NavigableString(part))
                        else:
                            # Inyectar tag span nativo de kobo
                            span = soup.new_tag("span", **{"class": "koboSpan", "id": f"kobo.{chapter_idx}.{sentence_idx}"})
                            span.string = part
                            new_nodes.append(span)
                            sentence_idx += 1
                            
                    child.replace_with(*new_nodes)

        return str(soup).encode('utf-8')

    def convert(self, input_path: str, target_format: str):
        """Metodo legacy para soporte anterior"""
        if target_format == '.epub' and input_path.lower().endswith('.pdf'):
            logger.info(f"Conversión legacy simulada iniciada para [{input_path}] a [{target_format}]")
