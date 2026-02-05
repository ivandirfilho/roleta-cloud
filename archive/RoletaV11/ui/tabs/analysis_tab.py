# RoletaV11/ui/tabs/analysis_tab.py

import tkinter as tk
from tkinter import ttk
from ui.styles import Theme

class AnalysisTab:
    """
    Aba de Análises e Logs:
    - Exibe logs textuais do sistema.
    - Exibe tabelas de dados brutos (se necessário).
    """
    def __init__(self, parent, controller, theme):
        self.parent = parent
        self.controller = controller
        self.theme = theme
        self.frame = tk.Frame(self.parent, bg="white")
        self.frame.pack(fill="both", expand=True)
        
        self.build()

    def build(self):
        """Constrói a área de logs."""
        
        lbl_titulo = tk.Label(self.frame, text="Log de Eventos do Sistema", font=("Arial", 12, "bold"), bg="white")
        lbl_titulo.pack(anchor="w", padx=10, pady=(10, 5))
        
        # Área de Texto com Scroll
        txt_frame = tk.Frame(self.frame)
        txt_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        scrollbar = tk.Scrollbar(txt_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.log_text = tk.Text(txt_frame, height=20, font=("Courier New", 9),
                                yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        
        scrollbar.config(command=self.log_text.yview)
        
        # Botões de controle do log
        btn_frame = tk.Frame(self.frame, bg="white")
        btn_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Button(btn_frame, text="Limpar Log", command=self._clear_log).pack(side="left")

    def _clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def log_message(self, message):
        """Adiciona mensagem ao log."""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
