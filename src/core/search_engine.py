import sqlite3
import re
import logging
import json
import numpy as np
from google import genai
from google.genai import types
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

def cosine_similarity(a, b):
    """Calcula la similitud entre dos vectores."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def execute_vectorial_search(user_query: str, gemini_api_key: str, db_path: str, top_k=15) -> list:
    """
    Vectoriza la consulta del usuario mediante Gemini, 
    y evalúa la similitud del coseno de este vector contra todos los embeddings de libros.
    """
    if not gemini_api_key:
        logger.error("Se requiere la API key de Gemini para la búsqueda vectorial.")
        return []

    try:
        client = genai.Client(api_key=gemini_api_key)
        
        # Vectorizar la consulta del usuario
        response = client.models.embed_content(
            model="gemini-embedding-001", 
            contents=user_query, 
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
        )
        query_vector = response.embeddings[0].values
        
    except Exception as e:
        logger.error(f"Error al vectorizar la consulta con Gemini: {e}")
        return []

    results = []
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Garantizar que la columna embedding existe antes de operar
        try:
            cursor.execute("ALTER TABLE Books ADD COLUMN embedding TEXT;")
            conn.commit()
            logger.info("Migración Forzada: Columna 'embedding' añadida a la tabla Books.")
        except sqlite3.OperationalError:
            pass # La columna ya existe
            
        # Extraer todos los libros con embedding válido
        query = '''
            SELECT 
                b.id as book_id, 
                b.title, 
                COALESCE((SELECT GROUP_CONCAT(a.name, ', ') FROM Authors a JOIN Book_Authors ba ON a.id = ba.author_id WHERE ba.book_id = b.id), 'Desconocido') AS author,
                COALESCE((SELECT GROUP_CONCAT(c.name, ', ') FROM Categories c JOIN Book_Categories bc ON c.id = bc.category_id WHERE bc.book_id = b.id), '') AS categories,
                b.summary,
                b.embedding
            FROM Books b 
            WHERE b.embedding IS NOT NULL AND b.summary IS NOT NULL
        '''
        cursor.execute(query)
        rows = cursor.fetchall()
        
        columns = [col[0] for col in cursor.description]
        
        scored_items = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            book_vector_str = row_dict['embedding']
            if not book_vector_str:
                continue
            book_vector = json.loads(book_vector_str)
            score = cosine_similarity(query_vector, book_vector)
            scored_items.append((row_dict, score))
            
        if not scored_items:
            return []
            
        # 1. Ordenar todos de mayor a menor
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        # 2. Obtener la nota del mejor libro
        top_score = scored_items[0][1]
        logger.info(f"Top Score de la búsqueda: {top_score:.4f}")
        
        # 3. Filtrar dinámicamente: 
        # Debe ser decente (> 0.50) y estar a menos de 0.07 puntos del mejor resultado
        for row_dict, score in scored_items:
            if score >= 0.50 and score >= (top_score - 0.07):
                results.append({
                    'book_id': row_dict['book_id'],
                    'title': row_dict['title'],
                    'author': row_dict['author'],
                    'categories': row_dict['categories'],
                    'summary': row_dict['summary'],
                    'score': score
                })
                
        return results[:top_k]
        
    except sqlite3.Error as e:
        logger.error(f"Error de base de datos durante la búsqueda vectorial: {e}")
        return []
    except Exception as e:
        logger.error(f"Error procesando la búsqueda vectorial: {e}")
        return []
    finally:
        if conn:
            conn.close()
