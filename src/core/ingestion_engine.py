"""
Ingestion Engine for The Universal Library.

Este módulo se encarga de escanear directorios en busca de libros (ej. .epub),
extraer sus metadatos usando EbookLib y pasarlos a la base de datos 
de forma segura usando el Database Manager.
"""

import sys
import os
import logging
import sqlite3
import uuid
import re
import shutil
from pathlib import Path
from typing import Tuple, Optional
import ebooklib
from ebooklib import epub
import fitz

# Añadimos la raíz del proyecto al sys.path para poder importar src
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Directorios de datos definitivos
LIBRARY_DIR = PROJECT_ROOT / "data" / "library"
BOOKS_DIR = LIBRARY_DIR / "books"
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

# Directorio de portadas
COVERS_DIR = LIBRARY_DIR / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)

# Importamos las funciones del database manager
from src.db.database_manager import (
    get_connection,
    insert_book,
    get_or_create_author,
    get_or_create_publisher,
    link_book_author,
    link_book_publisher,
    DB_PATH
)

# Configuración básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_epub_metadata(file_path: Path) -> Tuple[str, str, str, Optional[epub.EpubBook]]:
    """
    Lee un archivo EPUB y extrae título, autor y editorial usando Dublin Core.
    Retorna (title, creator, publisher, epub_book). Si algún dato falta o si hay error, 
    asigna "Desconocido" u otros valores por defecto.
    """
    title = "Desconocido"
    creator = "Desconocido"
    publisher = "Desconocido"
    book = None
    
    try:
        # read_epub puede emitir warnings, idealmente los suprimiríamos, pero 
        # para propósitos de logging está bien dejarlos si son errores.
        book = epub.read_epub(str(file_path))
        
        # Extraer Metadata de Dublin Core
        title_metadata = book.get_metadata('DC', 'title')
        if title_metadata and len(title_metadata) > 0:
            title = title_metadata[0][0]
            
        creator_metadata = book.get_metadata('DC', 'creator')
        if creator_metadata and len(creator_metadata) > 0:
            creator = creator_metadata[0][0]
            
        publisher_metadata = book.get_metadata('DC', 'publisher')
        if publisher_metadata and len(publisher_metadata) > 0:
            publisher = publisher_metadata[0][0]
            
    except Exception as e:
        logger.error(f"Error al extraer metadatos de {file_path.name}: {e}")
        # Intentar al menos usar el nombre del archivo como título
        title = file_path.stem
        
    return title, creator, publisher, book

def extract_cover(epub_book: epub.EpubBook, book_title: str) -> Optional[str]:
    """
    Busca la portada de un libro EPUB, la guarda en data/covers y devuelve su ruta absoluta.
    Si no encuentra portada, devuelve None.
    """
    if not epub_book:
        return None
        
    cover_item = None
    # 1. Buscar ítem de tipo ITEM_COVER explícito
    for item in epub_book.get_items():
        if item.get_type() == ebooklib.ITEM_COVER:
            cover_item = item
            break
            
    # 2. Si no hay, buscar en ítems de imagen por palabras clave en ID o nombre
    if not cover_item:
        for item in epub_book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                name_id = item.get_name() + " " + item.get_id()
                name_id_lower = name_id.lower()
                if "cover" in name_id_lower or "portada" in name_id_lower or "front" in name_id_lower:
                    cover_item = item
                    break
                    
    if cover_item:
        clean_title = re.sub(r'[^A-Za-z0-9]', '_', book_title).strip('_')
        if not clean_title:
            clean_title = "unknown"
            
        ext = ".jpg" # extensión por defecto
        if cover_item.get_name().lower().endswith(".png"):
            ext = ".png"
            
        file_name = f"{clean_title}_{uuid.uuid4().hex[:8]}{ext}"
        cover_path = COVERS_DIR / file_name
        
        try:
            with open(cover_path, "wb") as f:
                f.write(cover_item.get_content())
            return str(cover_path.resolve())
        except Exception as e:
            logger.error(f"Error al guardar portada de {book_title}: {e}")
            
    return None

def extract_comic_metadata(file_path: Path):
    """
    Extrae metadata básica para cómics (.cbz, .cbr o .pdf designados como cómic).
    """
    title = file_path.stem
    if title.lower().endswith('.pdf'):
        title = title[:-4]
    
    # Limpieza de título
    title = title.replace('_', ' ').replace('-', ' ').replace('.', ' ').strip()
    
    author = "Desconocido"
    text = None  # Devolvemos None en el contenido de texto explícitamente
    return title, author, text

def extract_pdf_metadata(file_path: Path):
    doc = fitz.open(str(file_path))
    metadata = doc.metadata
    
    title = metadata.get('title')
    if not title:
        title = file_path.stem
        
    author = metadata.get('author')
    if not author:
        author = "Desconocido"
        
    text_chunks = []
    current_len = 0
    pages_to_read = min(10, len(doc))
    for i in range(pages_to_read):
        page_text = doc[i].get_text()
        if page_text:
            text_chunks.append(page_text)
            current_len += len(page_text)
        if current_len >= 4000:
            break
            
    doc.close()
    
    # Unir texto y limitar a 4000 caracteres
    text = " ".join(text_chunks)[:4000]
    
    return title, author, text

def process_directory(paths_or_directory) -> tuple:
    """
    Recibe una lista de archivos nuevos enviados por dropEvent o un directorio al que escanear.
    Devuelve una tupla con (lista de los IDs de los libros insertados, lista de warnings de duplicados).
    """
    all_files = []
    
    if isinstance(paths_or_directory, list):
        # Flujo directo desde Drag&Drop
        all_files = paths_or_directory
    else:
        directory = Path(paths_or_directory)
        if directory.exists() and directory.is_dir():
             for p in directory.rglob('*'):
                 if p.suffix.lower() in ['.epub', '.pdf', '.cbz', '.cbr', '.pdf_comic']:
                     all_files.append((p, p.name))
                     
    success_count = 0
    error_count = 0
    inserted_book_ids = []
    duplicate_warnings = []
    
    for real_path, virtual_name in all_files:
        logger.info(f"Procesando: {virtual_name}")
        
        conn = None
        try:
            file_path = Path(real_path) # Archivo original en el OS
            file_ext = Path(virtual_name).suffix.lower()
            if file_ext == '.epub':
                title, creator, publisher, book = extract_epub_metadata(file_path)
                format_str = "epub"
            elif file_ext == '.pdf':
                title, creator, text = extract_pdf_metadata(file_path)
                publisher = "Desconocido"
                book = None
                format_str = "pdf"
            elif file_ext in ['.cbz', '.cbr', '.pdf_comic']:
                title, creator, text = extract_comic_metadata(Path(virtual_name))
                publisher = "Desconocido"
                book = None
                format_str = file_ext.strip('.')
            else:
                continue
            
            # Conectar a la base de datos para insertar
            conn = get_connection(DB_PATH)
            if not conn:
                logger.error("No se pudo obtener conexión para insertar.")
                error_count += 1
                continue
                
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Books WHERE title = ?", (title,))
            if cursor.fetchone():
                logger.warning(f"El libro '{title}' ya existe. Ignorando archivo.")
                duplicate_warnings.append(str(file_path))
                continue
                
            # Extraer portada (ahora solo si el libro es nuevo)
            cover_path = extract_cover(book, title) if book else None
            
            # 2. Cálculo de Rutas a Destino Definitivo
            if file_ext == '.pdf_comic':
                destination_path = BOOKS_DIR / Path(virtual_name).with_suffix('.pdf').name
            else:
                destination_path = BOOKS_DIR / virtual_name
            
            # 3. Flujo Directo de Copiado Definitivo (Sin destruir origen)
            try:
                if str(file_path.absolute()) != str(destination_path.absolute()):
                    shutil.copy2(str(file_path), str(destination_path))
            except shutil.SameFileError:
                pass
                
            # 4. Inserción Atómica en BD
            book_id = insert_book(conn, title, str(destination_path), format_str, cover_path)
            
            if book_id is None:
                raise Exception("Fallo al insertar o recuperar el ID del libro.")
                
            # Procesar y vincular autor
            if creator != 'Desconocido':
                author_id = get_or_create_author(conn, creator)
                if author_id:
                    link_book_author(conn, book_id, author_id)
                    
            # Procesar y vincular editorial
            if publisher != 'Desconocido':
                publisher_id = get_or_create_publisher(conn, publisher)
                if publisher_id:
                    link_book_publisher(conn, book_id, publisher_id)
                    
            # Confirmar transacción si todo sale bien
            conn.commit()
            success_count += 1
            inserted_book_ids.append(book_id)
            logger.info(f"Guardado exitosamente y movido a procesados: '{title}' por '{creator}' (Editorial: '{publisher}')")
            
        except sqlite3.Error as e:
            # Revertir cambios en caso de error en base de datos
            if conn:
                conn.rollback()
            error_count += 1
            logger.error(f"Error de DB en transacción para {file_path.name}: {e}")
            print(f"Error procesando {file_path.name}: {e}")
        except Exception as e:
            # Revertir en caso de otros errores no capturados
            if conn:
                conn.rollback()
            error_count += 1
            logger.error(f"Error general en transacción para {file_path.name}: {e}")
            print(f"Error procesando {file_path.name}: {e}")
        finally:
            if conn:
                conn.close()
            
    logger.info(f"Resumen de Ingestión: {success_count} procesados exitosamente, {error_count} errores.")
    return inserted_book_ids, duplicate_warnings

if __name__ == "__main__":
    # Ejemplo de uso buscando una carpeta temporal o argumento
    # Normalmente, aquí se definiría qué directorio procesar
    import sys as sys_local
    if len(sys_local.argv) > 1:
        target_dir = sys_local.argv[1]
    else:
        # Por defecto escanea la ruta "data/ebooks_test"
        target_dir = PROJECT_ROOT / "data" / "ebooks_test"
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Carpeta creada para pruebas: {target_dir}")
            
    inserted_ids, duplicados = process_directory(target_dir)
    print(f"Insertados: {len(inserted_ids)}, Duplicados: {len(duplicados)}")
