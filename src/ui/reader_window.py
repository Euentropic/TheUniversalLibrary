import os
import fitz
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, 
    QScrollArea, QLabel, QPushButton, QToolBar, QMessageBox, QStackedWidget
)
from PyQt6.QtGui import QImage, QPixmap, QTransform
from PyQt6.QtCore import Qt
from PyQt6.QtWebEngineWidgets import QWebEngineView

from src.core.comic_engine import ComicEngine, DependencyError
from src.core.epub_engine import EpubEngine, EpubError

class ReaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Visor Interno")
        self.setMinimumSize(800, 900)
        
        self.doc = None
        self.comic = None
        self.epub = None
        self.current_page = 0
        self.current_scale = 1.0  # Lógica de Zoom Dinámico
        self.current_rotation = 0 # Lógica de Rotación
        
        # Widget Central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # TAREA 1: Barra de Navegación Superior
        self.navigation_toolbar = self.addToolBar("Navegación")
        self.navigation_toolbar.setMovable(False)
        
        # Controles de Paginación
        self.btn_prev = QPushButton("⬅️ Anterior")
        self.btn_prev.clicked.connect(self.prev_page)
        self.navigation_toolbar.addWidget(self.btn_prev)
        
        self.page_counter = QLabel("Página 0 de 0")
        self.page_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_counter.setMinimumWidth(100)
        self.navigation_toolbar.addWidget(self.page_counter)
        
        self.btn_next = QPushButton("Siguiente ➡️")
        self.btn_next.clicked.connect(self.next_page)
        self.navigation_toolbar.addWidget(self.btn_next)
        
        self.navigation_toolbar.addSeparator()
        
        # TAREA 2: Controles de Zoom y Ajuste
        self.btn_zoom_out = QPushButton("➖ Alejar")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        self.navigation_toolbar.addWidget(self.btn_zoom_out)
        
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(60)
        self.navigation_toolbar.addWidget(self.zoom_label)
        
        self.btn_zoom_in = QPushButton("➕ Acercar")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.navigation_toolbar.addWidget(self.btn_zoom_in)
        
        self.navigation_toolbar.addSeparator()
        
        self.btn_fit_width = QPushButton("🔄 Ajustar a Ancho")
        self.btn_fit_width.clicked.connect(self.fit_to_width)
        self.navigation_toolbar.addWidget(self.btn_fit_width)
        
        self.btn_fit_page = QPushButton("🔍 Ajustar a Página")
        self.btn_fit_page.clicked.connect(self.fit_to_page)
        self.navigation_toolbar.addWidget(self.btn_fit_page)
        
        self.btn_rotate = QPushButton("🔄 Girar")
        self.btn_rotate.clicked.connect(self.rotate_page)
        self.navigation_toolbar.addWidget(self.btn_rotate)
        
        # Stacked Widget para soportar múltiples motores de renderizado
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)
        
        # Índice 0: Scroll Area para el renderizado de PDFs y Cómics
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.page_label = QLabel("Cargando documento...")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.page_label)
        
        self.stacked_widget.addWidget(self.scroll_area)
        
        # Índice 1: Web Engine View para la carga de HTML/EPUB
        self.web_view = QWebEngineView()
        self.stacked_widget.addWidget(self.web_view)
        
        self.apply_dark_theme()
        
    def apply_dark_theme(self):
        dark_qss = """
        QMainWindow { background-color: #1e1e1e; }
        QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: "Segoe UI"; }
        QScrollArea { border: none; background-color: #1e1e1e; }
        QLabel { color: #cccccc; font-size: 11pt; padding: 0 5px; }
        QToolBar { 
            border: none; 
            border-bottom: 1px solid #333333; 
            background-color: #252526; 
            padding: 5px; 
            spacing: 8px;
        }
        QPushButton {
            background-color: #2d2d30;
            color: #ffffff;
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 10pt;
        }
        QPushButton:hover { background-color: #3e3e42; }
        QPushButton:disabled { color: #666666; background-color: #252526; }
        """
        self.setStyleSheet(dark_qss)

    def load_document(self, file_path):
        try:
            if self.comic:
                self.comic.close()
                
            self.current_page = 0
            self.current_rotation = 0
            self.doc = None
            self.comic = None
            self.epub = None
            
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.epub':
                self.epub = EpubEngine(file_path)
                self.setWindowTitle(f"Visor: {os.path.basename(file_path)}")
                self.stacked_widget.setCurrentIndex(1)
                self.btn_fit_width.setVisible(True)
                self.btn_fit_page.setVisible(True)
            elif ext in ['.cbz', '.cbr']:
                self.comic = ComicEngine(file_path)
                self.setWindowTitle(f"Visor: {os.path.basename(file_path)}")
                self.stacked_widget.setCurrentIndex(0)
                self.btn_fit_width.setVisible(True)
                self.btn_fit_page.setVisible(True)
            else: # PDF format (fitz)
                self.doc = fitz.open(file_path)
                self.setWindowTitle(f"Visor: {self.doc.name}")
                self.stacked_widget.setCurrentIndex(0)
                self.btn_fit_width.setVisible(True)
                self.btn_fit_page.setVisible(True)
                
            self.show_page()
            return True
            
        except EpubError as ee:
            self.close()
            QMessageBox.critical(None, "Error abriendo EPUB", str(ee))
            return False
        except DependencyError as de:
            self.close()
            
            msg = QMessageBox(None)
            msg.setWindowTitle("Dependencia requerida para CBR")
            msg.setText("Para leer archivos .cbr, tu sistema necesita tener WinRAR instalado y configurado. ¿Deseas ver las instrucciones para solucionarlo?")
            msg.setIcon(QMessageBox.Icon.Warning)
            
            btn_instrucciones = msg.addButton("Ver Instrucciones", QMessageBox.ButtonRole.ActionRole)
            btn_cancelar = msg.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            
            msg.exec()
            
            if msg.clickedButton() == btn_instrucciones:
                self._show_cbr_instructions()
                
            return False
        except Exception as e:
            self.page_label.setText(f"Error cargando el archivo: {e}")
            return True

    def show_page(self):
        if not self.doc and not self.comic and not self.epub:
            return
            
        try:
            total_pages = 0
            pixmap = None
            
            if self.epub:
                total_pages = len(self.epub)
                html_content = self.epub.get_chapter_html(self.current_page)
                self.web_view.setHtml(html_content)
                self.page_counter.setText(f"Sección {self.current_page + 1} de {total_pages}")
                self.zoom_label.setText(f"{int(self.current_scale * 100)}%")
                self.btn_prev.setEnabled(self.current_page > 0)
                self.btn_next.setEnabled(self.current_page < total_pages - 1)
                return

            if self.doc:
                # Flujo PDF
                page = self.doc[self.current_page]
                zoom_matrix = fitz.Matrix(self.current_scale, self.current_scale) 
                pix = page.get_pixmap(matrix=zoom_matrix)
                
                fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                pixmap = QPixmap.fromImage(qimg)
                total_pages = len(self.doc)
                
            elif self.comic:
                # Flujo Cómics .cbz / .cbr
                page_bytes = self.comic.get_page_bytes(self.current_page)
                pixmap = QPixmap()
                pixmap.loadFromData(page_bytes)
                
                # Para cómics, la escala se aplica al Pixmap crudo
                if self.current_scale != 1.0:
                    new_width = int(pixmap.width() * self.current_scale)
                    new_height = int(pixmap.height() * self.current_scale)
                    pixmap = pixmap.scaled(
                        new_width, 
                        new_height, 
                        Qt.AspectRatioMode.KeepAspectRatio, 
                        Qt.TransformationMode.SmoothTransformation
                    )
                total_pages = len(self.comic)
            
            if pixmap:
                if self.current_rotation != 0:
                    transform = QTransform().rotate(self.current_rotation)
                    pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
                self.page_label.setPixmap(pixmap)
            
            self.page_counter.setText(f"Página {self.current_page + 1} de {total_pages}")
            self.zoom_label.setText(f"{int(self.current_scale * 100)}%")
            
            self.btn_prev.setEnabled(self.current_page > 0)
            self.btn_next.setEnabled(self.current_page < total_pages - 1)
        except Exception as e:
             self.page_label.setText(f"Error renderizando la página: {e}")

    def prev_page(self):
        if (self.doc or self.comic or self.epub) and self.current_page > 0:
            self.current_page -= 1
            self.show_page()
            
    def next_page(self):
        if self.epub:
            total = len(self.epub)
        else:
            total = len(self.doc) if self.doc else len(self.comic)
        
        if (self.doc or self.comic or self.epub) and self.current_page < total - 1:
            self.current_page += 1
            self.show_page()

    def zoom_in(self):
        self.current_scale += 0.2
        if self.epub:
            self.web_view.setZoomFactor(self.current_scale)
            self.zoom_label.setText(f"{int(self.current_scale * 100)}%")
        else:
            self.show_page()

    def zoom_out(self):
        if self.current_scale > 0.3:
            self.current_scale -= 0.2
            if self.epub:
                self.web_view.setZoomFactor(self.current_scale)
                self.zoom_label.setText(f"{int(self.current_scale * 100)}%")
            else:
                self.show_page()

    def fit_to_width(self):
        if self.epub:
            self.current_scale = 1.0
            self.web_view.setZoomFactor(self.current_scale)
            self.zoom_label.setText("100%")
            return
            
        if not self.doc and not self.comic:
            return
        
        target_width = self.scroll_area.viewport().width() - 20
        rect_width = 1
        
        if self.doc:
            page = self.doc[self.current_page]
            rect_width = page.rect.width
        elif self.comic:
            pixmap = QPixmap()
            pixmap.loadFromData(self.comic.get_page_bytes(self.current_page))
            rect_width = pixmap.width()
            
        new_scale = target_width / max(1, rect_width)
        
        if new_scale > 0:
            self.current_scale = new_scale
            self.show_page()

    def rotate_page(self):
        self.current_rotation = (self.current_rotation + 90) % 360
        self.show_page()

    def fit_to_page(self):
        if self.epub:
            self.current_scale = 1.0
            self.web_view.setZoomFactor(self.current_scale)
            self.zoom_label.setText("100%")
            return
            
        if not self.doc and not self.comic:
            return
            
        target_width = self.scroll_area.viewport().width() - 20
        target_height = self.scroll_area.viewport().height() - 20
        
        rect_width = 1
        rect_height = 1
        
        if self.doc:
            page = self.doc[self.current_page]
            rect_width = page.rect.width
            rect_height = page.rect.height
        elif self.comic:
            pixmap = QPixmap()
            pixmap.loadFromData(self.comic.get_page_bytes(self.current_page))
            rect_width = pixmap.width()
            rect_height = pixmap.height()
            
        scale_w = target_width / max(1, rect_width)
        scale_h = target_height / max(1, rect_height)
        
        # Tomar la escala mínima para asegurar que quepa por completo
        new_scale = min(scale_w, scale_h)
        
        if new_scale > 0:
            self.current_scale = new_scale
            self.show_page()

    def _show_cbr_instructions(self):
        import tempfile
        import sys
        
        instructions = (
            "Paso 1: Descargar e instalar WinRAR (gratuito) desde rarlab.com.\n\n"
            "Paso 2: Buscar 'Variables de entorno' en el menú inicio de Windows.\n\n"
            "Paso 3: En 'Variables del sistema', editar 'Path' y añadir una nueva línea con: C:\\Program Files\\WinRAR\n\n"
            "Paso 4: Reiniciar esta aplicación."
        )
        
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, "Instrucciones_CBR.txt")
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(instructions)
            
        try:
            if os.name == 'nt':
                os.startfile(file_path)
            else:
                import subprocess
                if sys.platform == 'darwin':
                    subprocess.call(('open', file_path))
                else:
                    subprocess.call(('xdg-open', file_path))
        except Exception as e:
            QMessageBox.critical(None, "Error", f"No se pudo abrir el archivo de instrucciones: {e}")

    def closeEvent(self, event):
        """Limpiar recursos al cerrar la ventana"""
        if self.comic:
            self.comic.close()
        super().closeEvent(event)
