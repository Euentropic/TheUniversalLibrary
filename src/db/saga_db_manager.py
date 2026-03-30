import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def save_saga_metadata(conn: sqlite3.Connection, book_id: int, local_title: str, saga_json: dict):
    """
    Inserta o actualiza los metadatos de sagas y universos de un libro.
    """
    if not saga_json.get("is_part_of_saga", False):
        return
        
    try:
        cursor = conn.cursor()
        
        # 1. Recuperar o insertar Universe
        universe_name = saga_json.get("universe") or "Universo Desconocido"
        universe_desc = saga_json.get("universe_description") or ""
        
        cursor.execute("""
            INSERT OR IGNORE INTO universes (name, description) VALUES (?, ?)
        """, (universe_name, universe_desc))
        
        # Extraer el id del universo
        cursor.execute("SELECT id FROM universes WHERE name = ?", (universe_name,))
        row = cursor.fetchone()
        if not row:
            raise Exception("No se pudo obtener el ID del universo.")
        universe_id = row[0]
        
        # 2. Recuperar o insertar Saga
        saga_name = saga_json.get("saga_name") or "Saga Desconocida"
        total_books = saga_json.get("total_books_in_saga")
        
        cursor.execute("""
            INSERT OR IGNORE INTO sagas (universe_id, name, total_books) VALUES (?, ?, ?)
        """, (universe_id, saga_name, total_books))
        
        # Extraer el id de la saga
        cursor.execute("SELECT id FROM sagas WHERE name = ? AND universe_id = ?", (saga_name, universe_id))
        row = cursor.fetchone()
        if not row:
            raise Exception("No se pudo obtener el ID de la saga.")
        saga_id = row[0]
        
        # 3. Iterar sobre el catálogo e insertar cada libro
        matched_catalog_entry_id = None
        lower_local_title = local_title.lower()
        
        catalog = saga_json.get("catalog", [])
        for entry in catalog:
            entry_title = entry.get("title", "")
            entry_author = entry.get("author", "")
            reading_order = entry.get("reading_order")
            chrono_order = entry.get("chronological_order")
            spanish_pub = entry.get("spanish_published", False)
            
            cursor.execute("""
                INSERT INTO catalog_entries 
                (saga_id, title, author, reading_order, chronological_order, spanish_published)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (saga_id, entry_title, entry_author, reading_order, chrono_order, spanish_pub))
            
            current_entry_id = cursor.lastrowid
            
            # Comparar para ver si es el libro actual
            # Usamos contención bidireccional simple para mayor tolerancia
            entry_title_lower = entry_title.lower()
            if entry_title_lower in lower_local_title or lower_local_title in entry_title_lower:
                matched_catalog_entry_id = current_entry_id
                
        # 4. Actualizar el libro local con el catalog_entry_id del catálogo que hizo match
        if matched_catalog_entry_id:
            cursor.execute("UPDATE Books SET catalog_entry_id = ? WHERE id = ?", (matched_catalog_entry_id, book_id))
            logger.info(f"Libro '{local_title}' (id:{book_id}) vinculado correctamente a su saga con entrada {matched_catalog_entry_id}.")
        else:
            logger.warning(f"No se encontró un match perfecto en el catálogo para el título local: '{local_title}'.")
            
        conn.commit()
        
    except Exception as e:
        logger.error(f"Error procesando JSON de saga para el libro ID {book_id}: {e}")
        conn.rollback()
