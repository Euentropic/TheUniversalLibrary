import fitz
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QScrollArea, QLabel, QPushButton
)
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt

class ReaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Visor Interno")
        self.setMinimumSize(800, 900)
        
        self.doc = None
        self.current_page = 0
        
        # Widget Central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Scroll Area para el renderizado
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.page_label = QLabel("Cargando documento...")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.page_label)
        
        main_layout.addWidget(self.scroll_area)
        
        # Barra de Navegación Inferior
        nav_layout = QHBoxLayout()
        
        self.btn_prev = QPushButton("⬅️ Anterior")
        self.btn_prev.clicked.connect(self.prev_page)
        nav_layout.addWidget(self.btn_prev)
        
        self.page_counter = QLabel("Página 0 de 0")
        self.page_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.page_counter)
        
        self.btn_next = QPushButton("Siguiente ➡️")
        self.btn_next.clicked.connect(self.next_page)
        nav_layout.addWidget(self.btn_next)
        
        main_layout.addLayout(nav_layout)
        
        self.apply_dark_theme()
        
    def apply_dark_theme(self):
        dark_qss = """
        QMainWindow { background-color: #1e1e1e; }
        QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: "Segoe UI"; }
        QScrollArea { border: none; background-color: #1e1e1e; }
        QLabel { color: #cccccc; font-size: 11pt; }
        QPushButton {
            background-color: #0e639c;
            color: #ffffff;
            border-radius: 4px;
            padding: 8px 15px;
            font-size: 11pt;
            font-weight: bold;
        }
        QPushButton:hover { background-color: #1177bb; }
        QPushButton:disabled { background-color: #2d2d30; color: #666666; }
        """
        self.setStyleSheet(dark_qss)

    def load_document(self, file_path):
        try:
            self.doc = fitz.open(file_path)
            self.current_page = 0
            self.setWindowTitle(f"Visor: {self.doc.name}")
            self.show_page()
        except Exception as e:
            self.page_label.setText(f"Error cargando el archivo: {e}")

    def show_page(self):
        if not self.doc:
            return
            
        try:
            page = self.doc[self.current_page]
            # Factor de escala superior para mayor nitidez (x2.0)
            zoom_matrix = fitz.Matrix(2.0, 2.0) 
            pix = page.get_pixmap(matrix=zoom_matrix)
            
            # Formato de imagen dependiendo de si tiene Alpha (transparencia) o no
            fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            
            pixmap = QPixmap.fromImage(qimg)
            self.page_label.setPixmap(pixmap)
            
            total_pages = len(self.doc)
            self.page_counter.setText(f"Página {self.current_page + 1} de {total_pages}")
            
            self.btn_prev.setEnabled(self.current_page > 0)
            self.btn_next.setEnabled(self.current_page < total_pages - 1)
        except Exception as e:
             self.page_label.setText(f"Error renderizando la página: {e}")

    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.show_page()
            
    def next_page(self):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.show_page()
