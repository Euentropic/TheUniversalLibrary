from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
from PyQt6.QtCore import QSettings

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de la Aplicación")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "Introduce tu API Key de Google Gemini para habilitar el Taxónomo IA y los resúmenes automáticos. "
            "Si lo dejas en blanco, la aplicación funcionará en Modo Básico."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Clave de la API de Gemini...")
        layout.addWidget(self.api_key_input)
        
        settings = QSettings("UniversalLibrary", "Config")
        current_api_key = settings.value("gemini_api_key", "")
        if current_api_key:
             self.api_key_input.setText(current_api_key)
             
        button_layout = QHBoxLayout()
        save_button = QPushButton("Guardar")
        save_button.clicked.connect(self.save_settings)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.apply_dark_theme()
        
    def save_settings(self):
        settings = QSettings("UniversalLibrary", "Config")
        settings.setValue("gemini_api_key", self.api_key_input.text().strip())
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
            padding: 8px;
            font-size: 11pt;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #1177bb;
        }
        """
        self.setStyleSheet(dark_qss)
