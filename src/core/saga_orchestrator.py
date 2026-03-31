import time
import logging

from src.db.database_manager import get_connection, DB_PATH
from src.core.saga_service import get_saga_metadata
from src.db.saga_db_manager import save_saga_metadata

# Configuración básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_saga_analysis_pipeline():
    conn = get_connection(DB_PATH)
    if not conn:
        logger.error("No se pudo conectar a la base de datos.")
        return

    try:
        cursor = conn.cursor()
        # Obtener los libros que aún no han sido analizados (cuyo catalog_entry_id es NULL)
        query = '''
            SELECT 
                b.id, 
                b.title, 
                COALESCE(GROUP_CONCAT(DISTINCT a.name), 'Desconocido') AS author_name
            FROM Books b
            LEFT JOIN Book_Authors ba ON b.id = ba.book_id
            LEFT JOIN Authors a ON ba.author_id = a.id
            WHERE b.catalog_entry_id IS NULL
            GROUP BY b.id
        '''
        cursor.execute(query)
        books_to_analyze = cursor.fetchall()

        if not books_to_analyze:
            logger.info("No hay libros pendientes de análisis de sagas.")
            return

        for book_id, title, author_name in books_to_analyze:
            logger.info(f"Analizando: '{title}' del autor '{author_name}'")

            try:
                saga_json = get_saga_metadata(title, author_name)
                
                if saga_json:
                    save_saga_metadata(conn, book_id, title, saga_json)
                else:
                    logger.warning(f"La API de Gemini no devolvió un JSON válido para '{title}'.")
            except Exception as e:
                logger.error(f"Error al procesar el libro '{title}': {e}")
            
            # Añadir un sleep de 3 segundos para respetar los rate-limits de la API de Gemini
            time.sleep(3)

    except Exception as e:
        logger.error(f"Error general en el pipeline de análisis: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    run_saga_analysis_pipeline()
