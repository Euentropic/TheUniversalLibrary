import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QLineEdit, QPushButton
)
from PyQt6.QtCore import Qt

class GeminiChatWindow(QDialog):
    def __init__(self, book_title: str, book_author: str, book_summary: str, parent=None):
        super().__init__(parent)
        self.book_title = book_title
        self.book_author = book_author
        self.book_summary = book_summary
        
        self.setWindowTitle("Bibliotecario IA - Gemini")
        self.resize(500, 600)
        self.is_expanded = False
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header Label
        self.header_label = QLabel(f"Consultando sobre: <b>{self.book_title}</b>")
        self.header_label.setStyleSheet("font-size: 14pt; color: #c586c0;")
        layout.addWidget(self.header_label)
        
        # History
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("background-color: #2d2d2d; color: #d4d4d4; font-size: 11pt; padding: 10px; border-radius: 5px; border: 1px solid #3e3e42;")
        
        # Contexto Inicial
        self.chat_history.append(f"<i>Hola, soy tu bibliotecario virtual. Pregúntame lo que quieras sobre el libro '{self.book_title}' de {self.book_author}.</i>\\n")
        layout.addWidget(self.chat_history)
        
        # Input Layout
        input_layout = QHBoxLayout()
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Escribe tu pregunta aquí...")
        self.input_field.setStyleSheet("padding: 8px; font-size: 11pt; background-color: #252526; color: white; border: 1px solid #3e3e42; border-radius: 4px;")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field)
        
        self.send_btn = QPushButton("Enviar")
        self.send_btn.setStyleSheet("background-color: #007acc; color: white; border-radius: 4px; padding: 8px; font-weight: bold;")
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)
        
        layout.addLayout(input_layout)
        
        # Botón Expandir
        expand_layout = QHBoxLayout()
        expand_layout.addStretch()
        self.expand_btn = QPushButton("⛶ Expandir")
        self.expand_btn.setStyleSheet("background-color: transparent; color: #888888; text-decoration: underline;")
        self.expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_btn.clicked.connect(self.toggle_expand)
        expand_layout.addWidget(self.expand_btn)
        
        layout.addLayout(expand_layout)
        
    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
            
        self.chat_history.append(f"<b style='color: #9cdcfe;'>Tú:</b> {text}")
        self.input_field.clear()
        
        # Dummy message hasta que integremos la API de Gemini
        self.chat_history.append("<b style='color: #c586c0;'>Gemini:</b> <i>Enviando consulta a Gemini...</i>\\n")
        
    def toggle_expand(self):
        if not self.is_expanded:
            self.resize(800, 800)
            self.expand_btn.setText("🗕 Contraer")
        else:
            self.resize(500, 600)
            self.expand_btn.setText("⛶ Expandir")
        self.is_expanded = not self.is_expanded
