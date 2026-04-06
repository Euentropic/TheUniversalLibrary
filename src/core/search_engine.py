import sqlite3
import re
import logging
from groq import Groq

# Configuración básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_fts_query_from_ai(user_query: str, groq_api_key: str) -> str:
    """
    Traduce la consulta natural del usuario a sintaxis FTS5 booleana usando Groq.
    """
    if not groq_api_key:
        logger.error("Se requiere la API key de Groq para la búsqueda.")
        return ""
        
    try:
        # Instanciar el cliente de Groq
        client = Groq(api_key=groq_api_key)
        
        system_prompt = (
            "Eres un bibliotecario experto. Extrae de 2 a 4 palabras clave esenciales de la consulta. "
            "Devuelve SOLO las palabras separadas por espacios. Mantén las tildes. NO uses comodines ni operadores. "
            "Ejemplo: 'libros del espacio y romance' -> espacio romance"
        )
        
        # Llamada a la API
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0.0,
            max_tokens=50
        )
        
        raw_output = completion.choices[0].message.content.strip()
        
        # Limpieza suave: solo quitamos puntuación básica, mantenemos letras (con tildes) y números
        clean_words = re.findall(r'\w+', raw_output, re.UNICODE)
        
        # Construimos la query FTS5: palabra1* AND palabra2*
        fts_query = " AND ".join([f"{word}*" for word in clean_words if word])
        
        logger.info(f"FTS5 Query generada: '{fts_query}'")
        return fts_query
        
    except Exception as e:
        logger.error(f"Error generando consulta FTS5 con Groq: {e}")
        return ""

def execute_semantic_search(user_query: str, groq_api_key: str, db_path: str) -> list:
    """
    Obtiene la consulta FTS5 de Groq y evalúa un MATCH directamente en SQLite.
    """
    fts_query = get_fts_query_from_ai(user_query, groq_api_key)
    
    if not fts_query.strip():
        logger.warning("FTS query vacío, abortando búsqueda.")
        return []
        
    results = []
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Ejecutar la búsqueda MATCH en FTS5
        query = "SELECT book_id, title, author, categories, summary FROM books_fts WHERE books_fts MATCH ? ORDER BY rank"
        cursor.execute(query, (fts_query,))
        
        # Mapear las columnas en una lista de diccionarios
        columns = [col[0] for col in cursor.description]
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
            
    except sqlite3.OperationalError as e:
        logger.error(f"Error operativo de SQLite (posible sintaxis FTS5 inválida): {e}")
        return [] # En caso de que la query fts siga conteniendo sintaxis extraña devuelta por Groq
    except sqlite3.Error as e:
        logger.error(f"Error de base de datos durante la búsqueda: {e}")
        return []
    finally:
        if conn:
            conn.close()
            
    return results
