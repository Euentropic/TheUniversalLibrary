"""
Text Extractor
Extrae texto plano de archivos EPUB para ser analizado por un modelo de IA.
"""

from pathlib import Path
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import logging

# Configuración de logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_sample_text(epub_path: str | Path, max_chars: int = 4000) -> str:
    """
    Lee un archivo EPUB y extrae el texto puro de sus documentos HTML usando BeautifulSoup.
    Concatena el resultado hasta el límite recomendado (max_chars) apto para LLMs.
    """
    try:
        book = epub.read_epub(str(epub_path))
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
        
    except Exception as e:
        logger.error(f"Error al extraer texto de {epub_path}: {e}")
        return ""
