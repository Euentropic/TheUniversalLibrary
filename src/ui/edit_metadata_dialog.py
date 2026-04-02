import sqlite3
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QComboBox, QSpinBox, QPushButton, QMessageBox, QFormLayout
)
from PyQt6.QtCore import Qt
from src.db.database_manager import DB_PATH, get_connection

class EditMetadataDialog(QDialog):
    def __init__(self, book_data, parent=None):
        super().__init__(parent)
        self.book_data = book_data
        self.book_id = book_data.get('id')
        
        # Guardaremos el catalog_entry_id para el UPDATE final
        self.catalog_entry_id = None
        
        self.setWindowTitle(f"Editar Metadatos: {book_data.get('title', '')}")
        self.resize(450, 300)
        
        # Datos para los combos: lista de dicts o tuplas
        self.sagas_data = []      # [(id, name, universe_id), ...]
        self.universes_data = []  # [(id, name), ...]
        
        self.init_ui()
        self.load_initial_db_data()
        self.populate_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        # Título
        self.title_input = QLineEdit()
        form_layout.addRow("Título:", self.title_input)
        
        # Autor
        self.author_input = QLineEdit()
        form_layout.addRow("Autor:", self.author_input)
        
        # Universo
        self.universe_combo = QComboBox()
        form_layout.addRow("Universo:", self.universe_combo)
        
        # Saga
        self.saga_combo = QComboBox()
        form_layout.addRow("Saga:", self.saga_combo)
        
        # Orden de lectura
        self.reading_order_spin = QSpinBox()
        self.reading_order_spin.setRange(0, 1000)
        self.reading_order_spin.setSpecialValueText("(Ninguno)")
        form_layout.addRow("Orden de Lectura:", self.reading_order_spin)
        
        layout.addLayout(form_layout)
        
        # Botones
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Guardar")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)
        self.cancel_btn = QPushButton("❌ Cancelar")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #4e4e52; }
        """)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)
        
        # Conexiones
        self.save_btn.clicked.connect(self.save_data)
        self.cancel_btn.clicked.connect(self.reject)

    def load_initial_db_data(self):
        conn = get_connection(DB_PATH)
        if not conn:
            return
            
        cursor = conn.cursor()
        
        # Obtener catalog_entry_id
        cursor.execute("SELECT catalog_entry_id FROM Books WHERE id = ?", (self.book_id,))
        row = cursor.fetchone()
        if row:
            self.catalog_entry_id = row[0]
            
        # Cargar Universos
        cursor.execute("SELECT id, name FROM universes ORDER BY name")
        self.universes_data = cursor.fetchall()
        self.universe_combo.addItem("(Ninguna)", None)
        for u_id, u_name in self.universes_data:
            self.universe_combo.addItem(u_name, u_id)
            
        # Cargar Sagas
        cursor.execute("SELECT id, name, universe_id FROM sagas ORDER BY name")
        self.sagas_data = cursor.fetchall()
        self.saga_combo.addItem("(Ninguna)", None)
        for s_id, s_name, _ in self.sagas_data:
            self.saga_combo.addItem(s_name, s_id)
            
        conn.close()

    def populate_data(self):
        title = self.book_data.get('title', '')
        author = self.book_data.get('author_name', '')
        self.title_input.setText(title)
        
        # El autor viene como 'Desconocido' si no hay. Evitamos mostrarlo
        if author == 'Desconocido':
            self.author_input.setText("")
        else:
            self.author_input.setText(author)
            
        # Setear universo localizando el item en el combo referenciado por texto
        universe_name = self.book_data.get('universe_name')
        if universe_name:
            idx = self.universe_combo.findText(universe_name)
            if idx >= 0:
                self.universe_combo.setCurrentIndex(idx)
                
        # Setear saga localizando el item
        saga_name = self.book_data.get('saga_name')
        if saga_name:
            idx = self.saga_combo.findText(saga_name)
            if idx >= 0:
                self.saga_combo.setCurrentIndex(idx)
                
        # Setear orden
        reading_o = self.book_data.get('reading_order')
        if reading_o not in (None, "?", ""):
            try:
                self.reading_order_spin.setValue(int(reading_o))
            except ValueError:
                self.reading_order_spin.setValue(0)
        else:
            self.reading_order_spin.setValue(0)

    def save_data(self):
        new_title = self.title_input.text().strip()
        new_author = self.author_input.text().strip()
        saga_id = self.saga_combo.currentData()
        universe_id = self.universe_combo.currentData()
        reading_order = self.reading_order_spin.value()
        
        if not new_title:
            QMessageBox.warning(self, "Error", "El título no puede estar vacío.")
            return
            
        conn = get_connection(DB_PATH)
        if not conn:
            QMessageBox.critical(self, "Error", "No se pudo conectar a la base de datos.")
            return
            
        try:
            cursor = conn.cursor()
            
            # 1. Update Books table
            cursor.execute("UPDATE Books SET title = ? WHERE id = ?", (new_title, self.book_id))
            
            # 2. Update Authors table and relations
            if new_author:
                cursor.execute("SELECT id FROM Authors WHERE name = ?", (new_author,))
                row = cursor.fetchone()
                if row:
                    auth_id = row[0]
                else:
                    cursor.execute("INSERT INTO Authors (name) VALUES (?)", (new_author,))
                    auth_id = cursor.lastrowid
                    
                # Update link
                cursor.execute("DELETE FROM Book_Authors WHERE book_id = ?", (self.book_id,))
                cursor.execute("INSERT INTO Book_Authors (book_id, author_id) VALUES (?, ?)", (self.book_id, auth_id))
            else:
                # Si lo dejó en blanco, borramos relaciones de autor
                cursor.execute("DELETE FROM Book_Authors WHERE book_id = ?", (self.book_id,))
            
            # 3. Update saga's universe si están ambos
            if saga_id and universe_id:
                cursor.execute("UPDATE sagas SET universe_id = ? WHERE id = ?", (universe_id, saga_id))
                
            # 4. Update catalog_entries
            final_reading_order = reading_order if reading_order > 0 else None
            
            if self.catalog_entry_id:
                # Update existing
                cursor.execute("""
                    UPDATE catalog_entries 
                    SET title = ?, author = ?, saga_id = ?, reading_order = ?
                    WHERE id = ?
                """, (new_title, new_author, saga_id, final_reading_order, self.catalog_entry_id))
            else:
                # Si hay saga u orden, creamos entrada
                if saga_id or final_reading_order is not None:
                    cursor.execute("""
                        INSERT INTO catalog_entries (saga_id, title, author, reading_order)
                        VALUES (?, ?, ?, ?)
                    """, (saga_id, new_title, new_author, final_reading_order))
                    new_catalog_id = cursor.lastrowid
                    cursor.execute("UPDATE Books SET catalog_entry_id = ? WHERE id = ?", (new_catalog_id, self.book_id))
                    
            conn.commit()
            self.accept()
            
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "Error", f"Fallo al guardar: {e}")
        finally:
            conn.close()
