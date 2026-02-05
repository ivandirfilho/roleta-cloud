# RoletaV11/ui/tabs/strategies_tab.py

import tkinter as tk
from tkinter import ttk
from ui.styles import Theme

class StrategiesTab:
    """
    Aba de Estratégias:
    - Exibe o status e performance de cada estratégia individualmente.
    - Permite ativar/desativar estratégias (se implementado).
    """
    def __init__(self, parent, controller, theme):
        self.parent = parent
        self.controller = controller
        self.theme = theme
        self.frame = tk.Frame(self.parent, bg="white")
        self.frame.pack(fill="both", expand=True)
        
        self.widgets_estrategias = {}
        
        self.build()

    def build(self):
        """Constrói as sub-abas para cada estratégia."""
        # Notebook interno para as estratégias (como no original)
        inner_notebook = ttk.Notebook(self.frame)
        inner_notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Lista de estratégias para criar abas
        nome_estrategias = [
            "Pela Força", 
            "Inércia Preditiva", 
            "Ressonância Polinomial",
            "Híbrida Adaptativa",
            "Sinergia Preditiva",
            "Sinergia Direcional Avançada"
        ]
        
        for nome in nome_estrategias:
            page = tk.Frame(inner_notebook, bg="white")
            inner_notebook.add(page, text=nome)
            
            # Conteúdo da página da estratégia
            self._build_strategy_page(page, nome)

    def _build_strategy_page(self, parent, nome):
        """Constrói o layout padrão de uma estratégia."""
        # Seção Superior: Status e Controles
        top_frame = tk.Frame(parent, bg="white")
        top_frame.pack(fill="x", padx=10, pady=10)
        
        lbl_titulo = tk.Label(top_frame, text=f"Estratégia: {nome}", font=("Arial", 14, "bold"), bg="white")
        lbl_titulo.pack(anchor="w")
        
        # Seção Gráfico de Performance (Ultimos 12 gatilhos)
        perf_frame = tk.LabelFrame(parent, text="Performance Recente", bg="white")
        perf_frame.pack(fill="x", padx=10, pady=5)
        
        indicators_frame = tk.Frame(perf_frame, bg="white")
        indicators_frame.pack(fill="x", pady=5)
        
        indicators = []
        for i in range(12):
            lbl = tk.Label(indicators_frame, width=2, height=1, bg="#e0e0e0", relief="groove")
            lbl.pack(side="left", padx=2)
            indicators.append(lbl)
            
        self.widgets_estrategias[nome] = {
            "grafico": indicators
        }
