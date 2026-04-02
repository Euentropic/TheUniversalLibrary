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

# Directorios de datos
PROCESADOS_DIR = PROJECT_ROOT / "data" / "Procesados"
PROCESADOS_DIR.mkdir(parents=True, exist_ok=True)

# Directorio de portadas
COVERS_DIR = PROJECT_ROOT / "data" / "covers"
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

def process_directory(directory_path: str | Path) -> list:
    """
    Escanea un directorio buscando archivos .epub, extrae sus metadatos e
    inserta los registros en la base de datos de manera transaccional.
    Devuelve la lista de los IDs de los libros insertados/procesados.
    """
    directory = Path(directory_path)
    if not directory.exists() or not directory.is_dir():
        logger.error(f"El directorio especificado no es válido: {directory}")
        return

    epub_files = list(directory.rglob('*.epub'))
    pdf_files = list(directory.rglob('*.pdf'))
    all_files = epub_files + pdf_files
    logger.info(f"Encontrados {len(all_files)} archivos ({len(epub_files)} epub, {len(pdf_files)} pdf) en {directory}")

    success_count = 0
    error_count = 0
    inserted_book_ids = []
    
    for file_path in all_files:
        logger.info(f"Procesando: {file_path.name}")
        
        file_ext = file_path.suffix.lower()
        if file_ext == '.epub':
            title, creator, publisher, book = extract_epub_metadata(file_path)
            format_str = "epub"
        elif file_ext == '.pdf':
            title, creator, text = extract_pdf_metadata(file_path)
            publisher = "Desconocido"
            book = None
            format_str = "pdf"
        else:
            continue
        
        # Conectar a la base de datos para insertar
        conn = get_connection(DB_PATH)
        if not conn:
            logger.error("No se pudo obtener conexión para insertar.")
            error_count += 1
            continue
            
        try:
            # 1. Bloqueo Absoluto de Duplicados
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Books WHERE title = ?", (title,))
            if cursor.fetchone():
                logger.warning(f"El libro '{title}' ya existe. Ignorando archivo.")
                try:
                    os.remove(str(file_path))
                except OSError as e:
                    logger.error(f"Error borrando archivo duplicado: {e}")
                continue
                
            # Extraer portada (ahora solo si el libro es nuevo)
            cover_path = extract_cover(book, title) if book else None
            
            # 2. Cálculo de Rutas
            destination_path = PROCESADOS_DIR / file_path.name
            
            # 3. Movimiento Físico
            try:
                shutil.move(str(file_path), str(destination_path))
            except shutil.Error:
                # Si falla porque ya existía el archivo con el mismo nombre en destino
                shutil.copy(str(file_path), str(destination_path))
                os.remove(str(file_path))
                
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
            conn.rollback()
            error_count += 1
            logger.error(f"Error de DB en transacción para {file_path.name}: {e}")
        except Exception as e:
            # Revertir en caso de otros errores no capturados
            conn.rollback()
            error_count += 1
            logger.error(f"Error general en transacción para {file_path.name}: {e}")
        finally:
            conn.close()
            
    logger.info(f"Resumen de Ingestión: {success_count} procesados exitosamente, {error_count} errores.")
    return inserted_book_ids

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
            
    process_directory(target_dir)
