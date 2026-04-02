import sys
from pathlib import Path

# Añadimos la raíz del proyecto al sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

import shutil
import unicodedata

def remove_accents(input_str):
    if not input_str: return ""
    return unicodedata.normalize('NFKD', str(input_str)).encode('ASCII', 'ignore').decode('utf-8').lower()

# PyQt6 Core y Widgets
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QLabel, QTextEdit, QListWidgetItem, QSplitter,
    QLineEdit, QPushButton, QSizePolicy, QMessageBox, QComboBox
)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Importamos las dependencias locales de la base de datos y backend
from src.db.database_manager import get_connection, DB_PATH, get_all_books_details, delete_book, get_all_categories
from src.core.ingestion_engine import process_directory
from src.core.ai_service import run_summary_pipeline
from src.core.saga_orchestrator import run_saga_analysis_pipeline
from src.ui.chat_window import GeminiChatWindow
from src.ui.edit_metadata_dialog import EditMetadataDialog
from PyQt6.QtWidgets import QDialog

class IngestionWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, target_dir):
        super().__init__()
        self.target_dir = target_dir
        
    def run(self):
        self.progress.emit("Ingestando archivos locales...")
        book_ids = process_directory(str(self.target_dir))
        
        self.progress.emit("Generando resúmenes con IA...")
        run_summary_pipeline(book_ids)
        
        self.progress.emit("Analizando sagas y universos...")
        run_saga_analysis_pipeline(book_ids)
        
        self.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Configuración inicial de la ventana
        self.setWindowTitle("The Universal Library - Dashboard")
        self.resize(1000, 600)
        self.setAcceptDrops(True)
        
        # Aplicamos el tema oscuro global
        self.apply_dark_theme()
        
        # Inicializar UI y cargar datos
        self.init_ui()
        self.load_data()

    def apply_dark_theme(self):
        """Aplica un QSS (Qt Style Sheet) de estilo oscuro moderno premium."""
        dark_qss = """
        QMainWindow {
            background-color: #1e1e1e;
        }
        QWidget {
            background-color: #1e1e1e;
            color: #e0e0e0;
            font-family: "Segoe UI", "Helvetica Neue", sans-serif;
        }
        QListWidget {
            background-color: #252526;
            border: none;
            border-right: 1px solid #333333;
            outline: none;
            padding: 5px;
        }
        QListWidget::item {
            padding: 8px;
            border-radius: 4px;
        }
        QListWidget::item:hover {
            background-color: #2a2d2e;
        }
        QListWidget::item:selected {
            background-color: #37373d;
            color: #ffffff;
        }
        QSplitter::handle {
            background-color: #333333;
        }
        QSplitter::handle:horizontal {
            width: 2px;
        }
        QSplitter::handle:pressed {
            background-color: #007acc; /* Azul acento estilo VS Code */
        }
        QLabel {
            color: #cccccc;
        }
        QTextEdit {
            background-color: #2d2d2d;
            border: 1px solid #3e3e42;
            border-radius: 5px;
            color: #d4d4d4;
            selection-background-color: #264f78;
        }
        """
        self.setStyleSheet(dark_qss)
        
    def init_ui(self):
        # 1. Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Tarea 1: QSplitter Ajustable (reemplazando QHBoxLayout en el centro)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0) # Extender visualmente toda la ventana
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)
        
        # 2. Panel Izquierdo: Buscador y Lista
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        search_layout = QHBoxLayout()
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Buscar libro, autor o saga...")
        self.search_bar.textChanged.connect(self.filter_books)
        self.search_bar.setStyleSheet("""
            QLineEdit {
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 6px;
                background-color: #252526;
                color: #d4d4d4;
                font-size: 11pt;
            }
        """)
        search_layout.addWidget(self.search_bar)
        
        self.category_filter = QComboBox()
        self.category_filter.setStyleSheet("""
            QComboBox {
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 6px;
                background-color: #252526;
                color: #d4d4d4;
                font-size: 11pt;
            }
        """)
        self.category_filter.currentTextChanged.connect(self.filter_books)
        search_layout.addWidget(self.category_filter)
        
        left_layout.addLayout(search_layout)
        
        self.books_list = QListWidget()
        self.books_list.setStyleSheet("font-size: 11pt;")
        
        # Tarea 2: Mejora de la lista (elipse de textos largos)
        self.books_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.books_list.setWordWrap(False)
        left_layout.addWidget(self.books_list)
        
        self.splitter.addWidget(left_panel)
        
        # Conectar evento de cambio de selección
        self.books_list.itemSelectionChanged.connect(self.on_book_selected)
        
        # 3. Panel Derecho: Detalles del libro
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20) # Padding interno para respirar
        self.splitter.addWidget(right_panel)
        
        # Tarea 1: Proporción del Splitter 30/70
        self.splitter.setSizes([300, 700])
        
        # --- Componentes del Panel Derecho ---
        
        # A) Portada (QLabel) - Tarea 4 (Limpieza / centrado)
        self.cover_label = QLabel("Seleccione un libro para ver los detalles")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setMaximumHeight(350)
        right_layout.addWidget(self.cover_label)
        
        # B) Título (QLabel) - Grande y Negrita
        self.title_label = QLabel("")
        font_title = QFont()
        font_title.setPointSize(16)
        font_title.setBold(True)
        self.title_label.setFont(font_title)
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumHeight(35)
        self.title_label.setStyleSheet("color: #ffffff;") # Blanco para destacar
        right_layout.addWidget(self.title_label)
        
        # C) Autor y Editorial (QLabel)
        self.meta_label = QLabel("")
        font_meta = QFont()
        font_meta.setPointSize(12)
        self.meta_label.setFont(font_meta)
        self.meta_label.setStyleSheet("color: #9cdcfe;") # Acento azul claro para meta (legible y armónico)
        self.meta_label.setMinimumHeight(25)
        right_layout.addWidget(self.meta_label)
        
        # Información de Universo y Saga
        self.saga_label = QLabel("")
        font_saga = QFont()
        font_saga.setPointSize(11)
        font_saga.setItalic(True)
        self.saga_label.setFont(font_saga)
        self.saga_label.setStyleSheet("color: #c586c0;") # Color distintivo (estilo VS Code)
        self.saga_label.setMinimumHeight(25)
        self.saga_label.hide() # Oculto por defecto
        right_layout.addWidget(self.saga_label)
        
        # Información de Categorías
        self.categories_label = QLabel("")
        font_cat = QFont()
        font_cat.setPointSize(10)
        font_cat.setItalic(True)
        self.categories_label.setFont(font_cat)
        self.categories_label.setStyleSheet("color: #8a8a8a;")
        self.categories_label.hide()
        right_layout.addWidget(self.categories_label)
        
        # D) Resumen Inteligente (QTextEdit) - Solo lectura
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.summary_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.summary_text.setMinimumHeight(150)
        # Padding interno asignado en duro si la QSS base requiere ayuda
        self.summary_text.setStyleSheet("padding: 12px; font-size: 11pt; line-height: 1.5;")
        right_layout.addWidget(self.summary_text)

        # Botón del Bibliotecario (Esqueleto Chat)
        self.chat_button = QPushButton("✨ Preguntar a Gemini sobre este libro")
        self.chat_button.setStyleSheet("""
            QPushButton {
                background-color: #5c2d91;
                color: #ffffff;
                border-radius: 6px;
                padding: 10px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6d3aab;
            }
            QPushButton:disabled {
                background-color: #3b205e;
                color: #888888;
            }
        """)
        self.chat_button.setEnabled(False)
        self.chat_button.clicked.connect(self.open_ai_chat)
        right_layout.addWidget(self.chat_button)

        # Botón de Edición
        self.edit_button = QPushButton("✏️ Editar Metadatos")
        self.edit_button.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border-radius: 6px;
                padding: 10px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:disabled {
                background-color: #2d2d30;
                color: #888888;
            }
        """)
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(self.open_edit_metadata)
        right_layout.addWidget(self.edit_button)

        # Botón de Borrado
        self.delete_button = QPushButton("🗑️ Borrar Libro de la Biblioteca")
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: #a51d2d;
                color: #ffffff;
                border-radius: 6px;
                padding: 10px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c1272d;
            }
            QPushButton:disabled {
                background-color: #5c1b22;
                color: #888888;
            }
        """)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_selected_book)
        right_layout.addWidget(self.delete_button)

    def load_data(self):
        """Lee los libros de la base de datos y poblamos la lista del panel izquierdo."""
        conn = get_connection(DB_PATH)
        if not conn:
            self.title_label.setText("Error fatal: No se pudo conectar a SQLite.")
            return
            
        books = get_all_books_details(conn)
        categories = get_all_categories(conn)
        conn.close()
        
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("Todas las categorías")
        self.category_filter.addItems(categories)
        self.category_filter.blockSignals(False)
        
        self.books_list.clear() # Limpiar lista
        
        for book in books:
            list_title = book.get('title', 'Libro Desconocido')
            item = QListWidgetItem(list_title)
            
            # Tarea 2: Tooltip mostrando el nombre completo al hacer hover
            item.setToolTip(list_title)
            
            # Guardamos el diccionario completo del libro
            item.setData(Qt.ItemDataRole.UserRole, book)
            self.books_list.addItem(item)
            
    def on_book_selected(self):
        """Se activa cada vez que el usuario hace click en un libro de la lista izquierda."""
        selected_items = self.books_list.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        # Recuperamos la data inyectada previamente
        book = item.data(Qt.ItemDataRole.UserRole)
        
        # Habilitar el botón de chat y borrar
        self.chat_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.edit_button.setEnabled(True)
        
        # 1. Actualizar Textos
        self.title_label.setText(book.get('title', 'Sin título disponible'))
        
        author = book.get('author_name', 'Desconocido')
        publisher = book.get('publisher_name', 'Desconocido')
        self.meta_label.setText(f"Autor: {author}  |  Editorial: {publisher}")
        
        saga_name = book.get('saga_name')
        if saga_name:
            universe_name = book.get('universe_name', 'Desconocido')
            reading_order = book.get('reading_order', '?')
            total_books = book.get('total_books', '?')
            self.saga_label.setText(f"🌌 Universo: {universe_name} | 📚 Saga: {saga_name} (Libro {reading_order} de {total_books})")
            self.saga_label.show()
        else:
            self.saga_label.hide()
            
        categories = book.get('categories')
        if categories:
            self.categories_label.setText(f"🏷️ Categorías: {categories}")
            self.categories_label.show()
        else:
            self.categories_label.hide()
        
        # 2. Actualizar Resumen
        summary = book.get('summary')
        if summary:
            self.summary_text.setPlainText(summary)
        else:
            self.summary_text.setPlainText("Este libro aún no ha sido resumido por Groq/Llama.")
            
        # 3. Actualizar Portada
        # Tarea 4: Las imágenes mantienen ratio y están centradas (setAlignment en init y scaledToHeight)
        cover_path = book.get('cover_path')
        if cover_path and Path(cover_path).is_file():
            pixmap = QPixmap(cover_path)
            scaled_pixmap = pixmap.scaledToHeight(350, Qt.TransformationMode.SmoothTransformation)
            
            self.cover_label.setPixmap(scaled_pixmap)
            # Removemos cualquier estilo de error
            self.cover_label.setStyleSheet("border: none; background-color: transparent;")
        else:
            self.cover_label.clear()
            self.cover_label.setText("Sin Portada")
            # Estilo fallback
            self.cover_label.setStyleSheet("color: #888; font-size: 14pt; border: 1px dashed #555;")

    def filter_books(self, text=None):
        query = remove_accents(self.search_bar.text()).strip()
        selected_category = self.category_filter.currentText()
        
        for i in range(self.books_list.count()):
            item = self.books_list.item(i)
            file_data = item.data(Qt.ItemDataRole.UserRole)
            if file_data:
                title = remove_accents(file_data.get('title', ''))
                author = remove_accents(file_data.get('author_name', ''))
                saga = remove_accents(file_data.get('saga_name', ''))
                universe = remove_accents(file_data.get('universe_name', ''))
                
                text_match = not query or (query in title or query in author or query in saga or query in universe)
                
                cat_match = True
                if selected_category != "Todas las categorías":
                    book_cats = file_data.get('categories')
                    if not book_cats:
                        cat_match = False
                    else:
                        cat_match = selected_category in book_cats
                        
                if text_match and cat_match:
                    item.setHidden(False)
                else:
                    item.setHidden(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        
        target_dir = PROJECT_ROOT / "data" / "ebooks_test"
        target_dir.mkdir(parents=True, exist_ok=True)
        
        for url in urls:
            path = Path(url.toLocalFile())
            if path.is_file():
                try:
                    shutil.copy(path, target_dir)
                except Exception as e:
                    print(f"Error copiando archivo {path}: {e}")
                    
        self.setWindowTitle("Procesando libros, por favor espera...")
        
        # Iniciar worker en segundo plano
        self.worker = IngestionWorker(target_dir)
        self.worker.progress.connect(lambda msg: self.setWindowTitle(f"Procesando: {msg}"))
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_finished(self):
        self.setWindowTitle("The Universal Library - Dashboard")
        self.load_data()

    def open_ai_chat(self):
        selected_items = self.books_list.selectedItems()
        if not selected_items:
            return
            
        book = selected_items[0].data(Qt.ItemDataRole.UserRole)
        title = book.get('title', 'Desconocido')
        author = book.get('author_name', 'Desconocido')
        summary = book.get('summary', '')
        
        # Instanciar la ventana de chat de forma no modal y asegurar la referencia
        self.chat_win = GeminiChatWindow(title, author, summary, self)
        self.chat_win.show()

    def open_edit_metadata(self):
        selected_items = self.books_list.selectedItems()
        if not selected_items:
            return
            
        book = selected_items[0].data(Qt.ItemDataRole.UserRole)
        book_id = book.get('id')
        
        dialog = EditMetadataDialog(book, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_data()
            
            # Re-seleccionar el libro editado para actualizar el panel derecho
            for i in range(self.books_list.count()):
                item = self.books_list.item(i)
                item_data = item.data(Qt.ItemDataRole.UserRole)
                if item_data and item_data.get('id') == book_id:
                    self.books_list.setCurrentItem(item)
                    break

    def delete_selected_book(self):
        selected_items = self.books_list.selectedItems()
        if not selected_items:
            return
            
        book = selected_items[0].data(Qt.ItemDataRole.UserRole)
        book_id = book.get('id')
        title = book.get('title', 'Desconocido')
        
        reply = QMessageBox.question(
            self, 'Confirmar borrado', 
            f"¿Estás seguro de que deseas eliminar '{title}'?\\nDeberás volver a arrastrarlo para procesarlo.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            conn = get_connection(DB_PATH)
            if conn:
                delete_book(conn, book_id)
                conn.close()
                
                # Mensaje temporal en el título
                self.setWindowTitle(f"Libro eliminado: {title}")
                
                # Limpiar panel derecho
                self.title_label.setText("")
                self.meta_label.setText("")
                self.saga_label.setText("")
                self.categories_label.setText("")
                self.summary_text.setPlainText("")
                self.cover_label.clear()
                self.chat_button.setEnabled(False)
                self.delete_button.setEnabled(False)
                self.edit_button.setEnabled(False)
                
                self.load_data()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
