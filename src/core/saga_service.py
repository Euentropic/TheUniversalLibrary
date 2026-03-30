import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Ajustar PYTHONPATH para poder importar desde src si se ejecuta como script
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from google import genai
from google.genai import types

from src.db.database_manager import get_connection, DB_PATH

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cargar variables de entorno (incluye GEMINI_API_KEY)
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)

def get_saga_metadata(book_title: str, author: str) -> dict:
    """
    Analiza si un libro pertenece a una saga o universo utilizando la API de Gemini.
    Devuelve un diccionario estructurado en JSON.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("No se encontró la variable de entorno GEMINI_API_KEY.")
        return {}

    # Instanciar el cliente usando el SDK oficial de Google GenAI
    client = genai.Client(api_key=api_key)

    prompt = f"""
Actúa como un experto literario exhaustivo e infalible. 
Por favor, analiza si el siguiente libro pertenece a una serie, saga o universo literario.

Título del libro: "{book_title}"
Autor: "{author}"

Devuelve la información estrictamente respetando el siguiente formato y estructura JSON, no incluyas markdown, asume el esquema directamente:
{{
  "is_part_of_saga": true o false,
  "universe": "Nombre del Universo (o null si no aplica)",
  "universe_description": "Breve descripción general del universo o null",
  "saga_name": "Nombre de la Saga (o null si es autoconclusivo y no hay saga)",
  "total_books_in_saga": número total de libros publicados en la saga (o null),
  "catalog": [
     {{
       "title": "Título del libro 1 en la saga",
       "author": "Nombre del Autor",
       "reading_order": número u orden recomendado de lectura (1, 2, 3...),
       "chronological_order": número en el orden cronológico interno del universo,
       "spanish_published": true o false (si ha sido publicado formalmente en español)
     }}
  ]
}}

Si el libro NO es parte de ninguna saga o universo, "is_part_of_saga" debe ser false, y todas las listas o campos relacionados deben retornar null o estar vacíos.
"""

    try:
        # Usamos el modelo más reciente (gemini-3.0-flash como solicitado, 
        # o puedes ajustar a gemini-2.5-flash si 3.0 no está disponible aún)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2 # Temperatura baja para un output determinístico y preciso
            )
        )
        
        # Como hemos configurado response_mime_type="application/json", 
        # la respuesta (response.text) será una cadena JSON válida.
        result_data = json.loads(response.text)
        return result_data

    except Exception as e:
        logger.error(f"Error al analizar datos con Gemini API: {e}")
        return {}

if __name__ == '__main__':
    conn = get_connection(DB_PATH)
    if conn:
        cursor = conn.cursor()
        
        # Extraer exactamente un libro al azar de la base de datos junto con su autor.
        # En caso de tener varios autores guardados como cadenas con comas los cogemos enteros.
        query = '''
            SELECT b.title, COALESCE(GROUP_CONCAT(DISTINCT a.name), 'Desconocido') AS author_name
            FROM Books b 
            LEFT JOIN Book_Authors ba ON b.id = ba.book_id 
            LEFT JOIN Authors a ON ba.author_id = a.id 
            GROUP BY b.id
            ORDER BY RANDOM() 
            LIMIT 1
        '''
        cursor.execute(query)
        row = cursor.fetchone()
        
        if row:
            title_random, author_random = row
            logger.info(f"==> Analizando libro extraído al azar: '{title_random}' de '{author_random}'")
            
            saga_data = get_saga_metadata(title_random, author_random)
            
            print("\nResultado JSON estructurado:")
            print(json.dumps(saga_data, indent=4, ensure_ascii=False))
        else:
            logger.warning("No se encontraron libros en la base de datos para analizar.")
            
        conn.close()
    else:
        logger.error("Fallo de conexión a la base de datos local SQLite.")
