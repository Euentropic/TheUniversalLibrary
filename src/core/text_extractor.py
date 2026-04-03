"""
Text Extractor
Extrae texto plano de archivos EPUB y PDF para ser analizado por un modelo de IA.
"""

import os
from pathlib import Path
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import logging
import fitz  # PyMuPDF

# Configuración de logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_sample_text(file_path: str | Path, max_chars: int = 4000) -> str:
    """
    Lee un archivo (EPUB o PDF) y extrae el texto puro.
    Concatena el resultado hasta el límite recomendado (max_chars) apto para LLMs.
    """
    try:
        file_path_str = str(file_path)
        ext = os.path.splitext(file_path_str)[1].lower()

        if ext == '.epub':
            book = epub.read_epub(file_path_str)
            extracted_text = []
            current_len = 0
            
            # Iterar sobre los ítems de tipo documento HTML (ITEM_DOCUMENT)
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    content = item.get_content()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Extraer texto limpio, insertando espacios entre etiquetas en lugar de unirlas de golpe
                    text = soup.get_text(separator=' ', strip=True)
                    
                    if text:
                        extracted_text.append(text)
                        current_len += len(text)
                        
                    if current_len >= max_chars:
                        break
                        
            # Unir las partes extraídas
            full_text = " ".join(extracted_text)
            
            # Recortar estrictamente al límite permitido (context window seguro)
            return full_text[:max_chars]

        elif ext == '.pdf':
            doc = fitz.open(file_path_str)
            extracted_text = []
            current_len = 0
            
            # Recorrer las primeras páginas (hasta 10)
            for i in range(min(10, len(doc))):
                text = doc[i].get_text("text").strip()
                if text:
                    extracted_text.append(text)
                    current_len += len(text)
                
                if current_len >= max_chars:
                    break
                    
            doc.close()
            
            full_text = " ".join(extracted_text)
            return full_text[:max_chars]

        else:
            logger.warning(f"Formato no soportado para extracción de texto: {ext} en {file_path_str}")
            return ""
            
    except Exception as e:
        logger.error(f"Error al extraer texto de {file_path}: {e}")
        return ""
