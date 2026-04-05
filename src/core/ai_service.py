"""
AI Service para The Universal Library.

Genera resúmenes atractivos usando Groq (Llama) analizando
muestras de texto limpio de los archivos EPUB.
"""

import os
import sys
import time
import random
import logging
import json
from pathlib import Path
from PyQt6.QtCore import QSettings

# Añadimos la raíz del proyecto al sys.path para poder importar src desde cualquier parte
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Importamos dependencias externas
from dotenv import load_dotenv
from groq import Groq
from google import genai

# Importaciones del proyecto
from src.db.database_manager import (
    get_connection, 
    DB_PATH, 
    get_books_without_summary, 
    update_book_summary,
    save_book_categories
)
from src.core.text_extractor import extract_sample_text

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cargar variables de entorno (incluye GROQ_API_KEY)
# Verifica la ruta .env que debe encontrarse en PROJECT_ROOT
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)
    logger.info("Variables de entorno cargadas.")
else:
    logger.warning("No se encontró el archivo .env, usando variables del sistema directamente.")

# Instanciar el cliente
try:
    client = Groq() # Automáticamente usa os.environ.get("GROQ_API_KEY")
except Exception as e:
    logger.error("No se pudo inicializar el cliente de Groq. ¿Está configurado GROQ_API_KEY?")
    client = None

# Instanciar cliente de Gemini estrictamente bajo estrategia BYOK
api_key = QSettings("UniversalLibrary", "Config").value("gemini_api_key", "")
if api_key:
    try:
        gemini_client = genai.Client(api_key=api_key)
    except Exception as e:
        logger.error(f"No se pudo inicializar Gemini: {e}")
        gemini_client = None
else:
    gemini_client = None

def generate_comic_metadata_with_gemini(title: str) -> str:
    """Llama a Gemini para obtener metadata de un cómic solo con el título."""
    api_key = QSettings("UniversalLibrary", "Config").value("gemini_api_key", "")
    if not api_key:
        return json.dumps({"summary": "Modo Básico: API Key necesaria para cómics (Estrategia BYOK no configurada).", "categories": ["Sin clasificar"]})
    
    gemini_client_local = genai.Client(api_key=api_key)
    prompt = f"Eres un experto en cómics. Identifica este cómic por su título: '{title}'. Devuelve ÚNICAMENTE un JSON con 'summary' (resumen de 4 líneas) y 'categories' (lista de 2 a 4 géneros). No incluyas nada fuera del JSON."
    try:
        response = gemini_client_local.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error generando en Gemini: {e}")
        return ""

def generate_summary(book_title: str, sample_text: str) -> str:
    """
    Llama a la API de Groq para generar un resumen corto utilizando Llama 3.
    """
    if not client:
        return ""
        
    prompt = f"Título del libro: {book_title}\n\nFragmento del libro:\n{sample_text}"
    
    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": "Eres un bibliotecario experto. Analiza el fragmento y devuelve ÚNICAMENTE un objeto JSON válido con dos claves: 'summary' (un resumen detallado y con punto final) y 'categories' (una lista de 2 a 4 géneros literarios o temáticas, ej: ['Ciencia Ficción', 'Aventura']). No incluyas texto fuera del JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7,
        max_tokens=1024,
        response_format={"type": "json_object"},
    )
    return completion.choices[0].message.content.strip()

def run_summary_pipeline(book_ids=None):
    logger.info("Iniciando Pipeline de Generación de Resúmenes mediante IA de Groq...")
    
    conn = get_connection(DB_PATH)
    if conn:
        if book_ids is not None:
            if not book_ids:
                logger.info("La lista de libros está vacía. No hay nada que procesar.")
                return
            placeholders = ','.join('?' for _ in book_ids)
            cursor = conn.cursor()
            cursor.execute(f"SELECT id, title, file_path FROM Books WHERE id IN ({placeholders}) AND (summary IS NULL OR summary = '')", book_ids)
            books = cursor.fetchall()
        else:
            books = get_books_without_summary(conn)
            
        logger.info(f"Se detectaron {len(books)} libros pendientes de recibir un resumen.")
        
        for book_id, title, file_path in books:
            logger.info(f"==> Iniciando proceso para el libro: '{title}'")
            
            # 1. Extraer Muestra Plana
            sample_text = extract_sample_text(file_path, max_chars=4000)
            
            if file_path.endswith(('.cbz', '.cbr')) or not sample_text:
                logger.info(f"El archivo es un cómic o no tiene texto. Usando Gemini para '{title}'...")
                
                summary = ""
                categories = []
                retries = 0
                max_retries = 3
                
                while retries < max_retries:
                    try:
                        raw_json = generate_comic_metadata_with_gemini(title)
                        
                        # Limpiar bloques markdown si Gemini los ha incluido
                        if raw_json.startswith('```'):
                            raw_json = raw_json.split('```')[1]
                            if raw_json.startswith('json'):
                                raw_json = raw_json[4:]
                            raw_json = raw_json.strip()
                            
                        parsed = json.loads(raw_json)
                        summary = parsed.get("summary", "")
                        categories = parsed.get("categories", [])
                        break
                    except Exception as e:
                        retries += 1
                        logger.warning(f"Error parseando JSON de Gemini, reintento {retries}/{max_retries}: {e}")
                        time.sleep(2)
                        
                if summary:
                    update_book_summary(conn, book_id, summary)
                    if categories:
                        save_book_categories(conn, book_id, categories)
                    logger.info("✅ Resumen de cómic y categorías generadas exitosamente mediante Gemini.")
                else:
                    logger.warning(f"❌ Falló la generación por Gemini para '{title}'.")
                    
            elif sample_text:
                # 2. Generar mediante la red con manejo avanzado de Rate Limits (Exponential Backoff)
                logger.info(f"Fragmento extraído de {len(sample_text)} caracteres. Llamando a Groq...")
                
                summary = ""
                categories = []
                retries = 0
                max_retries = 5  # Aumentamos ligeramente los intentos
                base_delay = 5   # Tiempo base de espera en segundos
                
                while retries < max_retries:
                    try:
                        raw_json = generate_summary(title, sample_text)
                        parsed = json.loads(raw_json)
                        summary = parsed.get("summary", "")
                        categories = parsed.get("categories", [])
                        break  # Si tiene éxito, salimos del bucle
                    except Exception as e:
                        error_str = str(e).lower()
                        if "429" in error_str or "too many requests" in error_str:
                            retries += 1
                            # Fórmula de retroceso exponencial con Jitter
                            delay = (base_delay * (2 ** (retries - 1))) + random.uniform(0, 1)
                            logger.warning(f"⚠️ Rate Limit de Groq (429). Esperando {delay:.2f}s antes del intento {retries}/{max_retries}...")
                            time.sleep(delay)
                        else:
                            logger.error(f"❌ Error desconocido en API al generar JSON: {e}")
                            break # Si es otro error, no reintentamos
                            
                if summary:
                    api_key = QSettings("UniversalLibrary", "Config").value("api_key", "")
                    if not api_key:
                        categories = ["Sin clasificar"]
                        logger.info("Modo Básico: API Key no configurada. Categorías omitidas.")
                        
                    # 3. Guardar Base de Datos
                    update_book_summary(conn, book_id, summary)
                    if categories:
                        save_book_categories(conn, book_id, categories)
                    logger.info("✅ Resumen y categorías generadas exitosamente mediante Groq.")
                else:
                    logger.warning(f"❌ Falló la generación del resumen final para '{title}' tras agotar reintentos.")
                
            # 4. Controlar limites de velocidad estándar entre libros
            logger.info("Esperando 5 segundos por cortesía antes del siguiente libro...")
            time.sleep(5)
            
        conn.close()
        logger.info("Pipeline de Resúmenes finalizado.")
    else:
        logger.error("No se pudo conectar a SQLite. Abortando proceso.")

if __name__ == '__main__':
    run_summary_pipeline()
