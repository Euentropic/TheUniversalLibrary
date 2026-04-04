"""
Database Manager for The Universal Library.

Este módulo maneja la inicialización y las operaciones básicas de la base de datos
SQLite utilizada para almacenar los metadatos de los ebooks, autores, categorías, etc.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

# Configuración básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Rutas del proyecto
# __file__ es .../src/db/database_manager.py
# parent 1: src/db
# parent 2: src
# parent 3: raíz del proyecto (donde estará library.db)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_NAME = "library.db"
DB_PATH = PROJECT_ROOT / DB_NAME

def get_connection(db_path: Path = DB_PATH) -> Optional[sqlite3.Connection]:
    """
    Crea y retorna una conexión a la base de datos SQLite.
    Habilita el soporte para llaves foráneas.
    """
    try:
        # connect() acepta tanto strings como objetos Path en Python modernos
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error al conectar con la base de datos: {e}")
        return None

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
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Error al obtener detalles de libros: {e}")
        return []

if __name__ == "__main__":
    # Si se ejecuta este script directamente, inicializa la base de datos
    initialize_db()
