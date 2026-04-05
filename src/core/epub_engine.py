import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class EpubError(Exception):
    """Excepción específica para errores de carga o estructura del EPUB."""
    pass

class EpubEngine:
    def __init__(self, file_path):
        self.file_path = file_path
        self.book = None
        self.chapters = []
        self._load_book()

    def _load_book(self):
        try:
            # ignore_ncx asegura que nos enfoquemos en el 'spine' moderno, 
            # aunque los fallbacks internos de ebooklib ayudan con formatos viejos.
            self.book = epub.read_epub(self.file_path, options={'ignore_ncx': True})
        except Exception as e:
            logger.error(f"Error cargando EPUB ({self.file_path}): {e}")
            raise EpubError(f"El archivo EPUB parece estar corrupto o no se puede leer: {e}")

        # Extraer el 'spine' (orden lineal de lectura)
        spine = getattr(self.book, 'spine', [])
        
        for item_id, _ in spine:
            item = self.book.get_item_with_id(item_id)
            if item and item.get_type() == ebooklib.ITEM_DOCUMENT:
                self.chapters.append(item)
                
        if not self.chapters:
            raise EpubError("El EPUB no contiene capítulos válidos o legibles.")

    def get_chapter_html(self, index: int) -> str:
        if 0 <= index < len(self.chapters):
            item = self.chapters[index]
            try:
                # Python 3: try to decode directly if it's bytes
                raw_content = item.get_content().decode('utf-8')
            except AttributeError:
                raw_content = item.get_content()
            except UnicodeDecodeError:
                raw_content = item.get_content().decode('latin-1', 'ignore')
            
            # Parsear con BeautifulSoup
            soup = BeautifulSoup(raw_content, 'html.parser')
            
            # Inyectar CSS de Tema Oscuro para consistencia con la UI
            custom_style = soup.new_tag('style')
            custom_style.string = """
                body, p, div, span, a, li, td {
                    color: #000000 !important;
                    line-height: 1.6 !important;
                    background-color: #ffffff !important;
                }
                h1, h2, h3, h4, h5, h6 {
                    color: #111111 !important;
                    background-color: #ffffff !important;
                }
                img {
                    max-width: 100% !important;
                    height: auto !important;
                    display: block;
                    margin: 10px auto;
                }
            """
            
            if soup.head:
                soup.head.append(custom_style)
            elif soup.body:
                head = soup.new_tag('head')
                head.append(custom_style)
                soup.body.insert_before(head)
            else:
                return str(custom_style) + str(soup)
                
            return str(soup)
            
        raise IndexError("Índice de capítulo/sección de EPUB fuera de rango.")
        
    def __len__(self):
        return len(self.chapters)
