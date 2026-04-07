from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QMessageBox
from PyQt6.QtCore import QSettings, Qt
from src.db.database_manager import reindex_fts, generate_missing_embeddings

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de la Aplicación")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "<p><b>Nivel 1 (Modo Básico):</b> Sin claves. Lectura rápida y conversión a Kobo.</p>"
            "<p><b>Nivel 2 (Modo Inteligente):</b> API Key de Groq (Gratis). Activa la generación automática de resúmenes.</p>"
            "<p><b>Nivel 3 (Modo Pro):</b> Groq + Gemini. Desbloquea la agrupación automática por Sagas y Universos, y el Asistente IA para consultar dudas sobre un libro concreto.</p>"
        )
        info_label.setTextFormat(Qt.TextFormat.RichText)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # --- Gemini ---
        layout.addWidget(QLabel("API Key de Google Gemini (Taxónomo/Sagas):"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Clave de la API de Gemini...")
        layout.addWidget(self.api_key_input)
        
        # --- Groq ---
        layout.addWidget(QLabel("API Key de Groq (Buscador/Resúmenes):"))
        groq_layout = QHBoxLayout()
        self.groq_api_key_input = QLineEdit()
        self.groq_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.groq_api_key_input.setPlaceholderText("Clave de la API de Groq...")
        
        groq_help_btn = QPushButton("❓ Cómo obtenerla gratis")
        groq_help_btn.clicked.connect(self.show_groq_help)
        
        groq_layout.addWidget(self.groq_api_key_input)
        groq_layout.addWidget(groq_help_btn)
        layout.addLayout(groq_layout)
        
        # --- Cargar Ajustes ---
        settings = QSettings("UniversalLibrary", "Config")
        
        current_api_key = settings.value("gemini_api_key", "")
        if current_api_key:
             self.api_key_input.setText(current_api_key)
             
        current_groq_key = settings.value("groq_api_key", "")
        if current_groq_key:
             self.groq_api_key_input.setText(current_groq_key)
             
        # --- Botones inferiores ---
        # self.btn_reindex = QPushButton("🔄 Reindexar Motor de Búsqueda")
        # self.btn_reindex.clicked.connect(self.run_reindex)
        # layout.addWidget(self.btn_reindex)
        
        button_layout = QHBoxLayout()
        save_button = QPushButton("Guardar")
        save_button.clicked.connect(self.save_settings)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.apply_dark_theme()
        
    def run_reindex(self):
        reindex_fts()
        generate_missing_embeddings()
        QMessageBox.information(self, "Reindexación Completada", "El índice FTS5 y los vectores semánticos han sido actualizados correctamente con los libros de tu biblioteca.")
        
    def show_groq_help(self):
        msg = (
            "La clave de Groq es totalmente gratuita y te permite usar el buscador inteligente.\n\n"
            "1. Entra en https://console.groq.com\n"
            "2. Inicia sesión con tu cuenta.\n"
            "3. Ve a la sección 'API Keys' y pulsa 'Create API Key'.\n"
            "4. Cópiala y pégala aquí."
        )
        QMessageBox.information(self, "Obtener API Key de Groq", msg)
        
    def save_settings(self):
        settings = QSettings("UniversalLibrary", "Config")
        settings.setValue("gemini_api_key", self.api_key_input.text().strip())
        settings.setValue("groq_api_key", self.groq_api_key_input.text().strip())
        self.accept()
        
    def apply_dark_theme(self):
        dark_qss = """
        QDialog {
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        QLabel {
            color: #cccccc;
            font-size: 11pt;
            margin-top: 5px;
        }
        QLineEdit {
            background-color: #2d2d2d;
            border: 1px solid #3e3e42;
            border-radius: 4px;
            padding: 8px;
            color: #d4d4d4;
            font-size: 11pt;
        }
        QPushButton {
            background-color: #0e639c;
            color: #ffffff;
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 10pt;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #1177bb;
        }
        """
        self.setStyleSheet(dark_qss)
