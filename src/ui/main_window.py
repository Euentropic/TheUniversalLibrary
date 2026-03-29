import sys
from pathlib import Path

# Añadimos la raíz del proyecto al sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# PyQt6 Core y Widgets
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QLabel, QTextEdit, QListWidgetItem, QSplitter
)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt

# Importamos las dependencias locales de la base de datos
from src.db.database_manager import get_connection, DB_PATH, get_all_books_details

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Configuración inicial de la ventana
        self.setWindowTitle("The Universal Library - Dashboard")
        self.resize(1000, 600)
        
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
        
        # 2. Panel Izquierdo: Lista de libros
        self.books_list = QListWidget()
        self.books_list.setStyleSheet("font-size: 11pt;")
        
        # Tarea 2: Mejora de la lista (elipse de textos largos)
        self.books_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.books_list.setWordWrap(False)
        self.splitter.addWidget(self.books_list)
        
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
        
        # D) Resumen Inteligente (QTextEdit) - Solo lectura
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        # Padding interno asignado en duro si la QSS base requiere ayuda
        self.summary_text.setStyleSheet("padding: 12px; font-size: 11pt; line-height: 1.5;")
        right_layout.addWidget(self.summary_text)

    def load_data(self):
        """Lee los libros de la base de datos y poblamos la lista del panel izquierdo."""
        conn = get_connection(DB_PATH)
        if not conn:
            self.title_label.setText("Error fatal: No se pudo conectar a SQLite.")
            return
            
        books = get_all_books_details(conn)
        conn.close()
        
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
        
        # 1. Actualizar Textos
        self.title_label.setText(book.get('title', 'Sin título disponible'))
        
        author = book.get('author_name', 'Desconocido')
        publisher = book.get('publisher_name', 'Desconocido')
        self.meta_label.setText(f"Autor: {author}  |  Editorial: {publisher}")
        
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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
