from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QPushButton, 
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSettings

# Importar la lógica y constantes del proyecto
from src.core.search_engine import execute_semantic_search
from src.db.database_manager import DB_PATH

class SearchWorker(QThread):
    """
    Worker para procesar la búsqueda semántica en segundo plano sin congelar la UI.
    """
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, user_query: str, groq_api_key: str, db_path: str):
        super().__init__()
        self.user_query = user_query
        self.groq_api_key = groq_api_key
        self.db_path = db_path

    def run(self):
        try:
            results = execute_semantic_search(self.user_query, self.groq_api_key, self.db_path)
            # Emitiremos la lista (esté llena o vacía)
            self.results_ready.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))


class SemanticSearchDialog(QDialog):
    """
    Diálogo para buscar libros usando el motor semántico (Groq + SQLite FTS5).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buscador Semántico Asistido por IA")
        self.resize(600, 400)
        
        # Guardaremos referencia al worker para que no sea destruido por el GC
        self.worker = None
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Campo de entrada
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Ej: Novelas de detectives en el espacio con toques de humor...")
        
        # Al presionar Enter estando en el input, también se dispara la búsqueda
        self.search_input.returnPressed.connect(self.perform_search)
        layout.addWidget(self.search_input)
        
        # Botón de búsqueda
        self.search_btn = QPushButton("Buscar")
        self.search_btn.clicked.connect(self.perform_search)
        layout.addWidget(self.search_btn)
        
        # Tabla de resultados
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Título", "Autor", "Resumen"])
        
        # El resumen suele ser largo, por lo que estiramos la última columna
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.results_table)

    def on_item_double_clicked(self, item):
        row = item.row()
        title_item = self.results_table.item(row, 0)
        self.selected_book_id = title_item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def perform_search(self):
        query_text = self.search_input.text().strip()
        if not query_text:
            return
            
        # UI: deshabilitar controles temporalmente
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Analizando...")
        self.results_table.setRowCount(0)
        
        # Recuperar API key
        groq_api_key = QSettings("UniversalLibrary", "Config").value("groq_api_key", "")
        if not groq_api_key:
            QMessageBox.warning(self, "API Key no encontrada", "No se ha configurado la API Key de Groq en los Ajustes.")
            self._reset_button()
            return
            
        db_path_str = str(DB_PATH)
        
        # Instanciar y conectar el Worker
        self.worker = SearchWorker(query_text, groq_api_key, db_path_str)
        self.worker.results_ready.connect(self.on_results_ready)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()

    def on_results_ready(self, results):
        self._reset_button()
        
        if not results:
            QMessageBox.information(self, "Sin Resultados", "No se encontraron libros que coincidan con la búsqueda.")
            return
            
        # Llenar la tabla con los resultados (diccionarios devueltos por el motor)
        for row, result_data in enumerate(results):
            self.results_table.insertRow(row)
            
            title_item = QTableWidgetItem(str(result_data.get('title', '')))
            title_item.setData(Qt.ItemDataRole.UserRole, result_data.get('book_id'))
            author_item = QTableWidgetItem(str(result_data.get('author', '')))
            
            # El texto del resumen del snippet FTS puede ser extenso
            summary_item = QTableWidgetItem(str(result_data.get('summary', '')))
            
            # Formato simple para mejor presentación (tooltip para el resumen completo si es necesario)
            summary_item.setToolTip(str(result_data.get('summary', '')))
            
            self.results_table.setItem(row, 0, title_item)
            self.results_table.setItem(row, 1, author_item)
            self.results_table.setItem(row, 2, summary_item)
            
        # Opcional: auto-ajustar las primeras dos columnas
        self.results_table.resizeColumnToContents(0)
        self.results_table.resizeColumnToContents(1)

    def on_error(self, error_message):
        self._reset_button()
        QMessageBox.critical(self, "Error de Búsqueda", f"No se pudo completar la búsqueda:\n{error_message}")

    def _reset_button(self):
        """Devuelve el botón a su estado normal."""
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Buscar")
