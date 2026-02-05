# RoletaV11/ui/tabs/microservice_tab.py

import tkinter as tk
from tkinter import ttk
from ui.styles import Theme
from core import config

class MicroserviceTab:
    """
    Aba do Microserviço:
    - Exibe histórico de força visual.
    - Exibe variações de força.
    - Exibe debug e status do microserviço.
    """
    def __init__(self, parent, controller, theme):
        self.parent = parent
        self.controller = controller
        self.theme = theme
        self.frame = tk.Frame(self.parent, bg="white")
        self.frame.pack(fill="both", expand=True)
        
        # Variáveis de UI vinculadas (seriam passadas pelo MainWindow ou Controller)
        # Por simplicidade, vamos criar locais ou vincular se existirem no controller
        self.setup_variables()
        self.build()

    def setup_variables(self):
        # Placeholders para variáveis de display de força
        # Idealmente, o controller exporia isso
        self.forcas_horario_vars = [tk.StringVar(value="-") for _ in range(config.FORCA_HISTORICO_FORCAS_ANALISADAS)]
        self.forcas_anti_horario_vars = [tk.StringVar(value="-") for _ in range(config.FORCA_HISTORICO_FORCAS_ANALISADAS)]
        
        # Variáveis de variação (11 quadrados)
        self.variacao_horario_vars = [tk.StringVar(value="") for _ in range(11)]
        self.variacao_anti_horario_vars = [tk.StringVar(value="") for _ in range(11)]

    def build(self):
        """Constrói o conteúdo da aba."""
        
        # 1. Painel Histórico de Força
        self._build_force_history_panel()
        
        # 2. Painel Variação de Força
        self._build_force_variation_panel()
        
        # 3. Informações de Debug do Microserviço
        self._build_debug_info_panel()

    def _build_force_history_panel(self):
        """Constrói a visualização das forças recentes."""
        frame = tk.LabelFrame(self.frame, text="Histórico de Força (em casas)", 
                              font=self.theme.FONT_ESTRATEGIA, bg="white", padx=5, pady=5)
        frame.pack(fill="x", padx=10, pady=5)
        
        # Horário
        row_h = tk.Frame(frame, bg="white"); row_h.pack(fill="x", pady=2)
        tk.Label(row_h, text="Horário (→):", width=12, anchor="w", bg="white").pack(side="left")
        for v in self.forcas_horario_vars:
            tk.Label(row_h, textvariable=v, font=("Arial", 12, "bold"), fg="darkorange", 
                     width=4, relief="groove", bg="#fff").pack(side="left", padx=2)

        # Anti-Horário
        row_ah = tk.Frame(frame, bg="white"); row_ah.pack(fill="x", pady=2)
        tk.Label(row_ah, text="Anti-Horário (←):", width=12, anchor="w", bg="white").pack(side="left")
        for v in self.forcas_anti_horario_vars:
            tk.Label(row_ah, textvariable=v, font=("Arial", 12, "bold"), fg="indigo", 
                     width=4, relief="groove", bg="#fff").pack(side="left", padx=2)

    def _build_force_variation_panel(self):
        """Constrói o gráfico de variação."""
        frame = tk.LabelFrame(self.frame, text="Variação de Força", 
                              font=self.theme.FONT_ESTRATEGIA, bg="white", padx=5, pady=5)
        frame.pack(fill="x", padx=10, pady=5)
        
         # Horário
        row_h = tk.Frame(frame, bg="white"); row_h.pack(fill="x", pady=2)
        tk.Label(row_h, text="H (→):", width=8, anchor="w", bg="white").pack(side="left")
        for v in self.variacao_horario_vars:
            tk.Label(row_h, textvariable=v, font=("Arial", 10, "bold"), fg="darkorange", 
                     width=3, relief="groove", bg="#f9f9f9").pack(side="left", padx=1)

        # Anti-Horário
        row_ah = tk.Frame(frame, bg="white"); row_ah.pack(fill="x", pady=2)
        tk.Label(row_ah, text="AH (←):", width=8, anchor="w", bg="white").pack(side="left")
        for v in self.variacao_anti_horario_vars:
            tk.Label(row_ah, textvariable=v, font=("Arial", 10, "bold"), fg="indigo", 
                     width=3, relief="groove", bg="#f9f9f9").pack(side="left", padx=1)

    def _build_debug_info_panel(self):
        """Info textual do microserviço."""
        frame = tk.LabelFrame(self.frame, text="Debug Microserviço", bg="white")
        frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.txt_debug = tk.Text(frame, height=10, font=("Courier New", 9))
        self.txt_debug.pack(fill="both", expand=True, padx=5, pady=5)
        self.txt_debug.insert("1.0", "Aguardando dados do pipeline...\n")

    def update(self, dados):
        """Atualiza visualizações."""
        # TODO: Implementar lógica de preenchimento das vars baseado no dados['stats']
        pass
