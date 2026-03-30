import sqlite3
import sys
from pathlib import Path

# Ajustar PYTHONPATH para poder importar desde src si se ejecuta como script
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.db.database_manager import DB_PATH

def initialize_saga_tables():
    """
    Se conecta a la base de datos y prepara las tablas para el sistema
    de Universos, Sagas y Entradas de Catálogo.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Habilitar claves foráneas
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Crear tabla universes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS universes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        )
    """)

    # 2. Crear tabla sagas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sagas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            universe_id INTEGER,
            name TEXT NOT NULL,
            total_books INTEGER,
            FOREIGN KEY(universe_id) REFERENCES universes(id)
        )
    """)

    # 3. Crear tabla catalog_entries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS catalog_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saga_id INTEGER,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            reading_order INTEGER,
            chronological_order INTEGER,
            spanish_published BOOLEAN DEFAULT 0,
            FOREIGN KEY(saga_id) REFERENCES sagas(id)
        )
    """)

    # 4. Modificar tabla Books para vincularla al catálogo
    try:
        cursor.execute("""
            ALTER TABLE Books 
            ADD COLUMN catalog_entry_id INTEGER NULL REFERENCES catalog_entries(id);
        """)
    except sqlite3.OperationalError as e:
        # Si la columna ya existe (por ejemplo, 'duplicate column name: catalog_entry_id')
        # silenciamos el error y continuamos.
        pass

    conn.commit()
    conn.close()

if __name__ == '__main__':
    initialize_saga_tables()
    print("✅ Tablas de Sagas y Universos inicializadas correctamente.")
