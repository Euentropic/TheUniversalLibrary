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
    QLineEdit, QPushButton, QSizePolicy, QMessageBox, QComboBox, QAbstractItemView, QFileDialog, QProgressDialog
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
from src.ui.settings_dialog import SettingsDialog
from src.ui.reader_window import ReaderWindow
from PyQt6.QtWidgets import QDialog

from src.core.converter_engine import ConverterEngine

class ConversionWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool)
    
    def __init__(self, books_info):
        super().__init__()
        self.books_info = books_info
        
    def run(self):
        converter = ConverterEngine()
        total = len(self.books_info)
        for i, b in enumerate(self.books_info):
            self.progress.emit(f"Convirtiendo a KEPUB ({i+1}/{total}): {b['title']}")
            try:
                converter.convert_to_kepub(b['path'])
            except Exception as e:
                self.progress.emit(f"Error en {b['title']}: {str(e)[:40]}...")
                import logging
                logging.getLogger(__name__).error(f"Error conversion KEPUB {b['path']}: {e}")
        self.finished.emit(True)

class IngestionWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(int, int)
    
    def __init__(self, files_list):
        super().__init__()
        self.files_list = files_list
        
    def run(self):
        self.progress.emit("Ingestando archivos locales...")
        book_ids, warnings = process_directory(self.files_list)
        
        self.progress.emit("Generando resúmenes con IA...")
        run_summary_pipeline(book_ids)
        
        self.progress.emit("Analizando sagas y universos...")
        run_saga_analysis_pipeline(book_ids)
        
        self.finished.emit(len(book_ids), len(warnings))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Configuración inicial de la ventana
        self.setWindowTitle("The Universal Library - Dashboard")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)
        self.setAcceptDrops(True)
        
        # Aplicamos el tema oscuro global
        self.apply_dark_theme()
        
        # Inicializar UI y cargar datos
        self.init_ui()
        self.load_data()
        
        # Activar barra de estado nativa
        self.statusBar().showMessage("Listo.", 5000)

    def show_toast(self, message: str):
        """Muestra un aviso rápido en la barra de estado."""
        self.statusBar().showMessage(message, 5000)

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
        left_panel.setMinimumWidth(260)
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
        
        self.format_filter = QComboBox()
        self.format_filter.setStyleSheet("""
            QComboBox {
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 6px;
                background-color: #252526;
                color: #d4d4d4;
                font-size: 11pt;
            }
        """)
        self.format_filter.addItems(['Todos los formatos', 'Solo EPUBs', 'Solo PDFs', 'Solo Cómics (CBZ/CBR)'])
        self.format_filter.currentTextChanged.connect(self.filter_books)
        search_layout.addWidget(self.format_filter)

        left_layout.addLayout(search_layout)
        
        self.books_list = QListWidget()
        self.books_list.setStyleSheet("font-size: 11pt;")
        self.books_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        
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
        self.splitter.setSizes([330, 770])
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 7)
        
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
        self.summary_text.setMinimumHeight(250)
        # Padding interno asignado en duro si la QSS base requiere ayuda
        self.summary_text.setStyleSheet("padding: 12px; font-size: 11pt; line-height: 1.5;")
        right_layout.addWidget(self.summary_text)

        # Botonera en layout horizontal
        buttons_layout = QHBoxLayout()
        right_layout.addLayout(buttons_layout)

        # Botón de Ajustes
        self.settings_button = QPushButton("⚙️ Ajustes")
        self.settings_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border-radius: 6px;
                padding: 10px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)
        self.settings_button.clicked.connect(self.open_settings)
        buttons_layout.addWidget(self.settings_button)

        # Botones Principales (IA, Lectura, Edición)
        self.read_button = QPushButton("📖 Leer")
        self.read_button.setStyleSheet("""
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
        self.read_button.setEnabled(False)
        self.read_button.clicked.connect(self.open_reader)
        buttons_layout.addWidget(self.read_button)

        # Botón del Bibliotecario (Esqueleto Chat)
        self.chat_button = QPushButton("✨ Consultar IA")
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
        buttons_layout.addWidget(self.chat_button)

        # Botones Especiales Epub / Export
        export_layout = QVBoxLayout()
        buttons_layout.addLayout(export_layout)

        # Botón de Conversión
        self.convert_button = QPushButton("🔄 Convertir a KEPUB")
        self.convert_button.setStyleSheet("""
            QPushButton {
                background-color: #217346;
                color: #ffffff;
                border-radius: 6px;
                padding: 10px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #278853;
            }
            QPushButton:disabled {
                background-color: #17422a;
                color: #888888;
            }
        """)
        self.convert_button.setEnabled(False)
        self.convert_button.hide()
        self.convert_button.clicked.connect(self.handle_conversion)
        export_layout.addWidget(self.convert_button)

        # Botón de Exportar
        self.export_zip_button = QPushButton("📦 Exportar para KOBO")
        self.export_zip_button.setStyleSheet("""
            QPushButton {
                background-color: #b0620c;
                color: #ffffff;
                border-radius: 6px;
                padding: 10px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d17b1f;
            }
            QPushButton:disabled {
                background-color: #5c3407;
                color: #888888;
            }
        """)
        self.export_zip_button.setEnabled(False)
        self.export_zip_button.hide()
        self.export_zip_button.clicked.connect(self.handle_export_to_zip)
        export_layout.addWidget(self.export_zip_button)

        # Botón de Edición
        self.edit_button = QPushButton("✏️ Editar")
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
        buttons_layout.addWidget(self.edit_button)
        
        # Espaciador para separar Borrar
        buttons_layout.addStretch()

        # Botón de Borrado
        self.delete_button = QPushButton("🗑️")
        self.delete_button.setFixedWidth(40)
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
        buttons_layout.addWidget(self.delete_button)

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
            
        item = selected_items[-1] # Mostrar info del último cliqueado en multiselección
        # Recuperamos la data inyectada previamente
        book = item.data(Qt.ItemDataRole.UserRole)
        
        # Habilitar los botones base
        self.read_button.setEnabled(len(selected_items) == 1)
        self.chat_button.setEnabled(len(selected_items) == 1)
        self.delete_button.setEnabled(True)
        self.edit_button.setEnabled(len(selected_items) == 1)
        
        all_epubs = all(i.data(Qt.ItemDataRole.UserRole).get('file_path', '').lower().endswith('.epub') for i in selected_items)
        if all_epubs and len(selected_items) > 0:
            self.convert_button.show()
            self.convert_button.setEnabled(True)
            self.export_zip_button.show()
            
            # Verificar si hay kepubs disponibles para habilitar la exportación
            all_paths = [i.data(Qt.ItemDataRole.UserRole).get('file_path', '') for i in selected_items]
            has_kepubs = any(Path(p).with_suffix('.kepub.epub').exists() for p in all_paths if p)
            self.export_zip_button.setEnabled(has_kepubs)
        else:
            self.convert_button.hide()
            self.convert_button.setEnabled(False)
            self.export_zip_button.hide()
            self.export_zip_button.setEnabled(False)
        
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
        selected_format = self.format_filter.currentText()
        
        for i in range(self.books_list.count()):
            item = self.books_list.item(i)
            file_data = item.data(Qt.ItemDataRole.UserRole)
            if file_data:
                title = remove_accents(file_data.get('title', ''))
                author = remove_accents(file_data.get('author_name', ''))
                saga = remove_accents(file_data.get('saga_name', ''))
                universe = remove_accents(file_data.get('universe_name', ''))
                file_path = file_data.get('file_path', '').lower()
                
                text_match = not query or (query in title or query in author or query in saga or query in universe)
                
                cat_match = True
                if selected_category != "Todas las categorías":
                    book_cats = file_data.get('categories')
                    if not book_cats:
                        cat_match = False
                    else:
                        cat_match = selected_category in book_cats
                        
                format_match = True
                if selected_format == 'Solo EPUBs':
                    format_match = file_path.endswith('.epub')
                elif selected_format == 'Solo PDFs':
                    format_match = file_path.endswith('.pdf')
                elif selected_format == 'Solo Cómics (CBZ/CBR)':
                    format_match = file_path.endswith('.cbz') or file_path.endswith('.cbr')

                if text_match and cat_match and format_match:
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
        
        # 1. Elimina uso de ebooks_test, se envía directamente al trabajador como archivos externos
        new_files = []
        
        for url in urls:
            path = Path(url.toLocalFile())
            if path.is_file():
                ext = path.suffix.lower()
                final_name = path.name

                if ext == '.zip':
                    reply = QMessageBox.question(
                        self, "Control de Aduanas (ZIP)",
                        f"""Hemos detectado el archivo ZIP '{path.name}'.
¿Deseas procesarlo como un cómic (CBZ)?""",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        final_name = path.with_suffix('.cbz').name
                    else:
                        continue  # Ignorar
                
                elif ext == '.pdf':
                    msg_box = QMessageBox(self)
                    msg_box.setWindowTitle("Control de Aduanas (PDF)")
                    msg_box.setText(f"""El archivo '{path.name}' es un PDF.

¿Deseas procesarlo como un Libro (extraer texto) o como un Cómic (solo título)?""")
                    btn_libro = msg_box.addButton("📖 Como Libro", QMessageBox.ButtonRole.ActionRole)
                    btn_comic = msg_box.addButton("🦸‍♂️ Como Cómic", QMessageBox.ButtonRole.ActionRole)
                    btn_cancel = msg_box.addButton("❌ Cancelar", QMessageBox.ButtonRole.RejectRole)
                    msg_box.exec()
                    
                    clicked_button = msg_box.clickedButton()
                    if clicked_button == btn_cancel:
                        continue
                    elif clicked_button == btn_comic:
                        final_name = path.with_suffix('.pdf_comic').name

                # Pasar tupla con path real y final_name propuesto al worker
                new_files.append((path, final_name))
                    
        if new_files:
            self.setWindowTitle("Procesando libros, por favor espera...")
            
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            
            self.progress_dialog = QProgressDialog("Iniciando ingestión...", None, 0, 0, self)
            self.progress_dialog.setWindowTitle("Sistema Ocupado")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.show()
            
            # Iniciar worker en segundo plano pasándole la lista de archivos
            self.worker = IngestionWorker(new_files)
            self.worker.progress.connect(self.progress_dialog.setLabelText)
            self.worker.finished.connect(self.on_worker_finished)
            self.worker.start()

    def on_worker_finished(self, success_count, warnings_count):
        QApplication.restoreOverrideCursor()
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
            
        self.setWindowTitle("The Universal Library - Dashboard")
        self.load_data()
        
        self.show_toast(f"✅ Ingesta de {success_count} libros completada con éxito.")
        
        if warnings_count > 0:
            QMessageBox.warning(
                self,
                "Libro Duplicado",
                "Este libro está duplicado. Si quiere procesarlo de nuevo, bórrelo y arrástrelo otra vez a la aplicación.",
                QMessageBox.StandardButton.Ok
            )

    def open_settings(self):
        SettingsDialog(self).exec()

    def open_reader(self):
        selected_items = self.books_list.selectedItems()
        if not selected_items:
            return
            
        book = selected_items[0].data(Qt.ItemDataRole.UserRole)
        file_path = book.get('file_path')
        
        if file_path and file_path.lower().endswith(('.pdf', '.cbz', '.cbr', '.epub')):
            self.reader = ReaderWindow()
            if self.reader.load_document(file_path):
                self.reader.show()
        else:
            self.show_toast("Formato aún no soportado en el visor interno (se requiere .pdf, .cbz, .cbr o .epub)")

    def open_ai_chat(self):
        from PyQt6.QtCore import QSettings
        
        api_key = QSettings("UniversalLibrary", "Config").value("gemini_api_key")
        if not api_key:
            QMessageBox.warning(
                self, 
                "Modo Vanilla Activo", 
                "Para consultar a la IA directamente, necesitas configurar tu propia API Key de Google Gemini en la ventana de Ajustes (Estrategia BYOK)."
            )
            return

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

    def handle_conversion(self):
        selected_items = self.books_list.selectedItems()
        if not selected_items:
            return
            
        books_info = []
        for item in selected_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            path = data.get('file_path')
            title = data.get('title', Path(path).name if path else '')
            if path and path.lower().endswith('.epub'):
                books_info.append({'path': path, 'title': title})
                
        if not books_info:
            return
            
        self.convert_button.setEnabled(False)
        self.export_zip_button.setEnabled(False)
        
        self.conv_worker = ConversionWorker(books_info)
        self.conv_worker.progress.connect(self.show_toast)
        self.conv_worker.finished.connect(lambda: self.on_conversion_finished(len(books_info)))
        self.conv_worker.start()

    def on_conversion_finished(self, size):
        self.show_toast(f"✅ Se convirtieron {size} libros a formato KEPUB con éxito.")
        self.on_book_selected() # Refresh button states

    def handle_export_to_zip(self):
        selected_items = self.books_list.selectedItems()
        if not selected_items:
            return
            
        kepub_info = []
        for item in selected_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            path = data.get('file_path')
            title = data.get('title', 'Libro')
            if path and path.lower().endswith('.epub'):
                kepub_cand = Path(path).with_suffix('.kepub.epub')
                if kepub_cand.exists():
                    clean_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
                    kepub_info.append((kepub_cand, f"{clean_title}.kepub.epub"))
                    
        if not kepub_info:
            self.show_toast("Ninguno de los libros seleccionados ha sido convertido a KEPUB todavía.")
            return
            
        suggested_name = "Exportacion_Kobo.zip"
        if len(kepub_info) == 1:
            suggested_name = kepub_info[0][1].replace('.kepub.epub', '_Kobo.zip')
            
        save_path, _ = QFileDialog.getSaveFileName(self, "Exportar KEPUBs", suggested_name, "ZIP Files (*.zip)")
        if save_path:
            import zipfile
            try:
                with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for kp_path, kp_name in kepub_info:
                        zipf.write(kp_path, kp_name)
                self.show_toast(f"✅ {len(kepub_info)} libros exportados a {Path(save_path).name}.")
            except Exception as e:
                self.show_toast(f"❌ Error al exportar: {e}")

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
            
        if len(selected_items) == 1:
            title = selected_items[0].data(Qt.ItemDataRole.UserRole).get('title', 'Desconocido')
            msg = f"¿Estás seguro de que deseas eliminar '{title}'?"
        else:
            msg = f"¿Estás seguro de que deseas eliminar {len(selected_items)} libros seleccionados?"
            
        reply = QMessageBox.question(
            self, 'Confirmar borrado', 
            f"{msg}\\nDeberás volver a arrastrarlos para procesarlos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            conn = get_connection(DB_PATH)
            if conn:
                for item in selected_items:
                    book_id = item.data(Qt.ItemDataRole.UserRole).get('id')
                    delete_book(conn, book_id)
                conn.close()
                
                # Mensaje temporal en el título
                self.setWindowTitle(f"Eliminados {len(selected_items)} libros.")
                
                # Limpiar panel derecho
                self.title_label.setText("")
                self.meta_label.setText("")
                self.saga_label.setText("")
                self.categories_label.setText("")
                self.summary_text.setPlainText("")
                self.cover_label.clear()
                self.read_button.setEnabled(False)
                self.chat_button.setEnabled(False)
                self.convert_button.setEnabled(False)
                self.convert_button.hide()
                self.export_zip_button.setEnabled(False)
                self.export_zip_button.hide()
                self.delete_button.setEnabled(False)
                self.edit_button.setEnabled(False)
                
                self.load_data()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
