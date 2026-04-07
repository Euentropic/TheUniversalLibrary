"""
Database Manager for The Universal Library.

Este módulo maneja la inicialización y las operaciones básicas de la base de datos
SQLite utilizada para almacenar los metadatos de los ebooks, autores, categorías, etc.
"""


import sqlite3
import logging
import json
from google import genai
from google.genai import types
from PyQt6.QtCore import QSettings
import sys
import os
from pathlib import Path
from typing import Optional

# Configuración básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_project_root() -> Path:
    """Devuelve la ruta raíz del proyecto, sea como script o empaquetado en .exe"""
    if getattr(sys, 'frozen', False):
        # Si es un ejecutable creado por PyInstaller
        return Path(sys.executable).parent
    else:
        # Si se ejecuta como script (src/db/database_manager.py)
        # Subimos 3 niveles: db -> src -> BOOK_MASTER
        return Path(__file__).resolve().parent.parent.parent

# --- RUTAS MAESTRAS DEL SISTEMA ---
PROJECT_ROOT = get_project_root()
DB_PATH = PROJECT_ROOT / "library.db"
DATA_DIR = PROJECT_ROOT / "data"
COVERS_DIR = DATA_DIR / "covers"
BOOKS_DIR = DATA_DIR / "books"

# Crear carpetas si no existen (previene crashes al arrancar de cero)
COVERS_DIR.mkdir(parents=True, exist_ok=True)
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

def get_connection(db_path: Path = DB_PATH) -> Optional[sqlite3.Connection]:
    """
    Crea y retorna una conexión a la base de datos SQLite.
    Habilita el soporte para llaves foráneas. Reconstrulle si no hay datos.
    """
    try:
        is_new = not db_path.exists() or db_path.stat().st_size == 0
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA encoding = 'UTF-8';")
        
        if is_new:
            # Reconstrulle tablas principales instantáneamente si la bdd fue borrada
            _rebuild_core_schema(conn)
            
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error al conectar con la base de datos: {e}")
        return None

def _rebuild_core_schema(conn: sqlite3.Connection):
    """Auto-reconstruye las tablas base para evitar fallos si el archivo DB es borrado manualmente."""
    try:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS Books (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, file_path TEXT UNIQUE NOT NULL, format TEXT NOT NULL, added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, summary TEXT, cover_path TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Authors (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE COLLATE NOCASE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Publishers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Collections (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Book_Authors (book_id INTEGER, author_id INTEGER, PRIMARY KEY (book_id, author_id), FOREIGN KEY (book_id) REFERENCES Books (id) ON DELETE CASCADE, FOREIGN KEY (author_id) REFERENCES Authors (id) ON DELETE CASCADE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Book_Categories (book_id INTEGER, category_id INTEGER, PRIMARY KEY (book_id, category_id), FOREIGN KEY (book_id) REFERENCES Books (id) ON DELETE CASCADE, FOREIGN KEY (category_id) REFERENCES Categories (id) ON DELETE CASCADE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Book_Publishers (book_id INTEGER, publisher_id INTEGER, PRIMARY KEY (book_id, publisher_id), FOREIGN KEY (book_id) REFERENCES Books (id) ON DELETE CASCADE, FOREIGN KEY (publisher_id) REFERENCES Publishers (id) ON DELETE CASCADE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Book_Collections (book_id INTEGER, collection_id INTEGER, PRIMARY KEY (book_id, collection_id), FOREIGN KEY (book_id) REFERENCES Books (id) ON DELETE CASCADE, FOREIGN KEY (collection_id) REFERENCES Collections (id) ON DELETE CASCADE)''')
        
        # Ecosistema de Sagas
        cursor.execute('''CREATE TABLE IF NOT EXISTS universes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, description TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS sagas (id INTEGER PRIMARY KEY AUTOINCREMENT, universe_id INTEGER, name TEXT NOT NULL, total_books INTEGER, FOREIGN KEY(universe_id) REFERENCES universes(id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS catalog_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, saga_id INTEGER, title TEXT NOT NULL, author TEXT NOT NULL, reading_order INTEGER, chronological_order INTEGER, spanish_published BOOLEAN DEFAULT 0, FOREIGN KEY(saga_id) REFERENCES sagas(id))''')
        
        # Migración adicional del catalog_entry_id generada por sagas (la ignorará si falla)
        try:
            cursor.execute("ALTER TABLE Books ADD COLUMN catalog_entry_id INTEGER NULL REFERENCES catalog_entries(id)")
        except:
            pass
            
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error auto-reconstruyendo el esquema: {e}")

def initialize_db(db_path: Path = DB_PATH) -> None:
    """
    Inicializa la base de datos creando todas las tablas necesarias si no existen.
    
    Tablas creadas:
    - Books, Authors, Categories, Publishers, Collections
    - Tablas intermedias: Book_Authors, Book_Categories, Book_Publishers, Book_Collections
    """
    logger.info(f"Inicializando base de datos en: {db_path}")
    conn = get_connection(db_path)
    
    if not conn:
        logger.error("Fallo al inicializar: No se pudo establecer la conexión.")
        return

    try:
        cursor = conn.cursor()

        # ---------------------------------------------------------------------
        # Creación de Tablas Principales
        # ---------------------------------------------------------------------

        # Tabla: Books
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                file_path TEXT UNIQUE NOT NULL,
                format TEXT NOT NULL,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                summary TEXT
            )
        ''')

        # Tabla: Authors
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Authors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')

        # Tabla: Categories
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE COLLATE NOCASE
            )
        ''')

        # Tabla: Publishers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Publishers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')

        # Tabla: Collections
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')

        # ---------------------------------------------------------------------
        # Creación de Tablas Intermedias (Relaciones Muchos a Muchos)
        # ---------------------------------------------------------------------

        # Tabla: Book_Authors
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Book_Authors (
                book_id INTEGER,
                author_id INTEGER,
                PRIMARY KEY (book_id, author_id),
                FOREIGN KEY (book_id) REFERENCES Books (id) ON DELETE CASCADE,
                FOREIGN KEY (author_id) REFERENCES Authors (id) ON DELETE CASCADE
            )
        ''')

        # Tabla: Book_Categories
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Book_Categories (
                book_id INTEGER,
                category_id INTEGER,
                PRIMARY KEY (book_id, category_id),
                FOREIGN KEY (book_id) REFERENCES Books (id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES Categories (id) ON DELETE CASCADE
            )
        ''')

        # Tabla: Book_Publishers
        # Asumiendo que un libro puede tener varias editoriales y viceversa
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Book_Publishers (
                book_id INTEGER,
                publisher_id INTEGER,
                PRIMARY KEY (book_id, publisher_id),
                FOREIGN KEY (book_id) REFERENCES Books (id) ON DELETE CASCADE,
                FOREIGN KEY (publisher_id) REFERENCES Publishers (id) ON DELETE CASCADE
            )
        ''')

        # Tabla: Book_Collections
        # Asumiendo que un libro puede pertenecer a varias colecciones personalizadas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Book_Collections (
                book_id INTEGER,
                collection_id INTEGER,
                PRIMARY KEY (book_id, collection_id),
                FOREIGN KEY (book_id) REFERENCES Books (id) ON DELETE CASCADE,
                FOREIGN KEY (collection_id) REFERENCES Collections (id) ON DELETE CASCADE
            )
        ''')

        # Migración: Añadir columna cover_path a la tabla Books
        try:
            cursor.execute("ALTER TABLE Books ADD COLUMN cover_path TEXT")
            logger.info("Migración: Columna 'cover_path' añadida a la tabla Books.")
        except sqlite3.OperationalError:
            # La columna probablemente ya existe
            pass

        # Migración: Añadir columna embedding a la tabla Books
        try:
            cursor.execute("ALTER TABLE Books ADD COLUMN embedding TEXT;")
            logger.info("Migración: Columna 'embedding' añadida a la tabla Books.")
        except sqlite3.OperationalError:
            # La columna probablemente ya existe
            pass

        # Guardar cambios
        conn.commit()
        logger.info("Todas las tablas fueron creadas o verificadas exitosamente.")

    except sqlite3.Error as e:
        logger.error(f"Error al inicializar las tablas de la base de datos: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_or_create_author(conn: sqlite3.Connection, name: str) -> Optional[int]:
    """Obtiene el ID del autor o lo crea si no existe."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Authors WHERE name = ?", (name,))
        result = cursor.fetchone()
        if result:
            return result[0]
        cursor.execute("INSERT INTO Authors (name) VALUES (?)", (name,))
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error en get_or_create_author: {e}")
        return None

def get_or_create_publisher(conn: sqlite3.Connection, name: str) -> Optional[int]:
    """Obtiene el ID de la editorial o lo crea si no existe."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Publishers WHERE name = ?", (name,))
        result = cursor.fetchone()
        if result:
            return result[0]
        cursor.execute("INSERT INTO Publishers (name) VALUES (?)", (name,))
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error en get_or_create_publisher: {e}")
        return None

def insert_book(conn: sqlite3.Connection, title: str, file_path: str, format_str: str, cover_path: Optional[str] = None) -> Optional[int]:
    """
    Inserta un nuevo libro en la base de datos y devuelve su ID.
    Si el file_path ya existe, devuelve el ID del libro existente.
    """
    try:
        if file_path:
            file_path = str(BOOKS_DIR / os.path.basename(file_path))
        if cover_path:
            cover_path = str(COVERS_DIR / os.path.basename(cover_path))
            
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Books WHERE file_path = ?", (file_path,))
        result = cursor.fetchone()
        if result:
            logger.info(f"El libro con ruta {file_path} ya existe.")
            return result[0]

        cursor.execute('''
            INSERT INTO Books (title, file_path, format, cover_path) 
            VALUES (?, ?, ?, ?)
        ''', (title, file_path, format_str, cover_path))
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error al insertar el libro: {e}")
        return None

def link_book_author(conn: sqlite3.Connection, book_id: int, author_id: int):
    """Vincula un libro con un autor en la tabla intermedia."""
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO Book_Authors (book_id, author_id) VALUES (?, ?)", (book_id, author_id))
    except sqlite3.Error as e:
        logger.error(f"Error al vincular libro y autor: {e}")

def link_book_publisher(conn: sqlite3.Connection, book_id: int, publisher_id: int):
    """Vincula un libro con una editorial en la tabla intermedia."""
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO Book_Publishers (book_id, publisher_id) VALUES (?, ?)", (book_id, publisher_id))
    except sqlite3.Error as e:
        logger.error(f"Error al vincular libro y editorial: {e}")

def delete_book(conn: sqlite3.Connection, book_id: int):
    """Elimina un libro de la base de datos por su ID."""
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Books WHERE id = ?", (book_id,))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error al eliminar el libro {book_id}: {e}")
        conn.rollback()

def get_books_without_summary(conn: sqlite3.Connection):
    """Devuelve una lista de tuplas (id, title, file_path) de libros sin resumen."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, file_path FROM Books WHERE summary IS NULL OR summary = ''")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error al obtener libros sin resumen: {e}")
        return []

def update_book_summary(conn: sqlite3.Connection, book_id: int, summary_text: str):
    """Actualiza la columna summary de un libro específico."""
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Books SET summary = ? WHERE id = ?", (summary_text, book_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error al actualizar el resumen del libro {book_id}: {e}")
        conn.rollback()

def save_book_categories(conn: sqlite3.Connection, book_id: int, category_list: list):
    """Guarda una lista de categorías para un libro."""
    if not category_list:
        return
    try:
        cursor = conn.cursor()
        for cat in category_list:
            cat_name = str(cat).strip()
            if not cat_name:
                continue
            cursor.execute("INSERT OR IGNORE INTO Categories (name) VALUES (?)", (cat_name,))
            cursor.execute("SELECT id FROM Categories WHERE name = ?", (cat_name,))
            row = cursor.fetchone()
            if row:
                cat_id = row[0]
                cursor.execute("INSERT OR IGNORE INTO Book_Categories (book_id, category_id) VALUES (?, ?)", (book_id, cat_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error al guardar categorías para el libro {book_id}: {e}")
        conn.rollback()

def get_all_categories(conn: sqlite3.Connection):
    """Devuelve una lista de nombres de categoría ordenados."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM Categories ORDER BY name ASC")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Error al obtener categorías: {e}")
        return []

def get_all_books_details(conn: sqlite3.Connection):
    """
    Devuelve todos los detalles de los libros haciendo JOIN
    con Authors y Publishers. Retorna una lista de diccionarios.
    """
    try:
        cursor = conn.cursor()
        query = '''
            SELECT 
                b.id, 
                b.title, 
                b.file_path,
                COALESCE(GROUP_CONCAT(DISTINCT a.name), 'Desconocido') AS author_name,
                COALESCE(GROUP_CONCAT(DISTINCT p.name), 'Desconocido') AS publisher_name,
                b.cover_path, 
                b.summary,
                ce.reading_order,
                s.name AS saga_name,
                s.total_books,
                u.name AS universe_name,
                GROUP_CONCAT(DISTINCT c.name) AS categories
            FROM Books b
            LEFT JOIN Book_Authors ba ON b.id = ba.book_id
            LEFT JOIN Authors a ON ba.author_id = a.id
            LEFT JOIN Book_Publishers bp ON b.id = bp.book_id
            LEFT JOIN Publishers p ON bp.publisher_id = p.id
            LEFT JOIN catalog_entries ce ON b.catalog_entry_id = ce.id
            LEFT JOIN sagas s ON ce.saga_id = s.id
            LEFT JOIN universes u ON s.universe_id = u.id
            LEFT JOIN Book_Categories bc ON b.id = bc.book_id
            LEFT JOIN Categories c ON bc.category_id = c.id
            GROUP BY b.id
        '''
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        
        results = []
        for row in cursor.fetchall():
            book_dict = dict(zip(columns, row))
            
            if book_dict.get('file_path'):
                nombre_archivo = os.path.basename(book_dict['file_path'])
                book_dict['file_path'] = str(BOOKS_DIR / nombre_archivo)
                
            if book_dict.get('cover_path'):
                nombre_portada = os.path.basename(book_dict['cover_path'])
                book_dict['cover_path'] = str(COVERS_DIR / nombre_portada)
                
            results.append(book_dict)
            
        return results
    except sqlite3.Error as e:
        logger.error(f"Error al obtener detalles de libros: {e}")
        return []

if __name__ == "__main__":
    # Si se ejecuta este script directamente, inicializa la base de datos
    initialize_db()

def reindex_fts(db_path: Path = DB_PATH) -> None:
    """
    Crea, limpia y reindexa la tabla virtual FTS5 para búsquedas semánticas.
    """
    logger.info("Iniciando reindexación de FTS5...")
    conn = get_connection(db_path)
    if not conn:
        logger.error("No se pudo conectar a la base de datos para reindexar.")
        return
        
    try:
        cursor = conn.cursor()
        
        # 1. Crear la tabla virtual FTS5
        cursor.execute("DROP TABLE IF EXISTS books_fts;")
        cursor.execute("CREATE VIRTUAL TABLE books_fts USING fts5(book_id UNINDEXED, title, author, categories, summary, tokenize='unicode61');")
        
        # 2. Borrar contenido actual
        cursor.execute("DELETE FROM books_fts;")
        
        # 3. Repoblar la tabla insertando los datos de la tabla principal
        try:
            cursor.execute("INSERT INTO books_fts (book_id, title, author, categories, summary) SELECT id, title, author, categories, summary FROM books WHERE summary IS NOT NULL;")
        except sqlite3.OperationalError as op_err:
            if "no such column" in str(op_err):
                # Si la tabla Books no tiene la columna autor o categorias, usar JOIN con las tablas vinculadas
                cursor.execute('''
                    INSERT INTO books_fts (book_id, title, author, categories, summary)
                    SELECT 
                        b.id, 
                        b.title, 
                        COALESCE((SELECT GROUP_CONCAT(a.name, ', ') FROM Authors a JOIN Book_Authors ba ON a.id = ba.author_id WHERE ba.book_id = b.id), 'Desconocido') AS author,
                        (SELECT GROUP_CONCAT(c.name, ', ') FROM Categories c JOIN Book_Categories bc ON c.id = bc.category_id WHERE bc.book_id = b.id) AS categories,
                        b.summary 
                    FROM Books b 
                    WHERE b.summary IS NOT NULL;
                ''')
            else:
                raise op_err
                
        conn.commit()
        logger.info("Tabla books_fts reindexada con éxito.")
        
    except sqlite3.Error as e:
        logger.error(f"Error al reindexar books_fts: {e}")
        conn.rollback()
    finally:
        conn.close()

def generate_missing_embeddings(db_path: Path = DB_PATH) -> None:
    """Genera y almacena embeddings para los libros que aún no lo tienen."""
    logger.info("Iniciando generación de embeddings faltantes...")
    gemini_api_key = QSettings("UniversalLibrary", "Config").value("gemini_api_key", "")
    
    if not gemini_api_key:
        logger.info("No hay API key de Gemini. Se omite la generación de embeddings.")
        return

    client = genai.Client(api_key=gemini_api_key)
    conn = get_connection(db_path)
    if not conn:
        logger.error("Error: no se pudo conectar a SQLite para generar embeddings.")
        return

    try:
        cursor = conn.cursor()
        
        # Garantizar que la columna embedding existe antes de operar
        try:
            cursor.execute("ALTER TABLE Books ADD COLUMN embedding TEXT;")
            conn.commit()
            logger.info("Migración Forzada: Columna 'embedding' añadida a la tabla Books.")
        except sqlite3.OperationalError:
            pass # La columna ya existe
        
        # Buscamos los libros elegibles que no tengan embedding,
        # obteniendo autor y categorias de las tablas vinculadas si es necesario
        query = '''
            SELECT 
                b.id, 
                b.title, 
                COALESCE((SELECT GROUP_CONCAT(a.name, ', ') FROM Authors a JOIN Book_Authors ba ON a.id = ba.author_id WHERE ba.book_id = b.id), 'Desconocido') AS author,
                COALESCE((SELECT GROUP_CONCAT(c.name, ', ') FROM Categories c JOIN Book_Categories bc ON c.id = bc.category_id WHERE bc.book_id = b.id), '') AS categories,
                b.summary 
            FROM Books b 
            WHERE b.summary IS NOT NULL AND b.embedding IS NULL;
        '''
        
        try:
            cursor.execute(query)
            books_to_process = cursor.fetchall()
        except sqlite3.OperationalError as op_err:
            if "no such column: b.embedding" in str(op_err):
                logger.warning("La columna embedding no existe todavía. Abortando generación.")
                return
            else:
                raise op_err

        if not books_to_process:
            logger.info("No hay libros pendientes de generar embeddings.")
            return

        for row in books_to_process:
            book_id = row[0]
            title = row[1]
            author = row[2]
            categories = row[3]
            summary = row[4]

            texto_completo = f"{title} {author} {categories} {summary}"

            try:
                result = client.models.embed_content(
                    model="gemini-embedding-001", 
                    contents=texto_completo, 
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
                )
                vector_json = json.dumps(result.embeddings[0].values)
                
                cursor.execute("UPDATE Books SET embedding = ? WHERE id = ?", (vector_json, book_id))
            except Exception as e:
                logger.error(f"Error al generar embedding para el libro ID {book_id}: {e}")

        conn.commit()
        logger.info(f"Se completó la generación de embeddings para {len(books_to_process)} libros.")

    except sqlite3.Error as e:
        logger.error(f"Error de base de datos en generate_missing_embeddings: {e}")
        conn.rollback()
    finally:
        conn.close()
