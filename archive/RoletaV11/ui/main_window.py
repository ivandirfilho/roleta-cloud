# RoletaV11/ui/main_window.py

import tkinter as tk
from tkinter import ttk, messagebox
import threading

from ui.styles import Theme
from core import config

class MainWindow:
    """
    Janela Principal do RoletaV11 Clean.
    Gerencia o layout principal e a orquestração dos painéis.
    """
    def __init__(self, root, app_controller):
        self.root = root
        self.controller = app_controller
        self.theme = Theme()
        
        # Variáveis de UI vinculadas (Tkinter Vars)
        self.setup_variables()
        
        # Configurar Janela
        self.setup_window()
        
        # Construir Layout
        self.build_layout()
        
        # Registrar-se no controller
        if self.controller:
            self.controller.register_ui(self)

    def setup_variables(self):
        """Inicializa variáveis reativas do Tkinter."""
        self.acao_var = tk.StringVar(value="Aguardando dados...")
        self.status_var = tk.StringVar(value="Sistema Iniciado")
        self.banca_var = tk.StringVar(value=f"R$ {config.BANCA_INICIAL:.2f}")
        self.proxima_jogada_var = tk.StringVar(value="--")
        
        # Variáveis para simulação e controles
        self.simulacao_ativa_var = tk.BooleanVar(value=False)

    def setup_window(self):
        """Configurações da janela principal."""
        self.root.title("RoletaV11 Clean - Sistema de Análise")
        self.root.geometry("1400x950")
        self.root.configure(bg="#f0f0f0")
        
        # Configurar grid principal (1 coluna agora, conforme simplificação anterior)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

    def build_layout(self):
        """
        Constrói a estrutura mestre da UI.
        Baseado no layout simplificado (Coluna Única / Esquerda Expandida).
        """
        # Container Principal
        self.main_container = tk.Frame(self.root, bg="#f0f0f0")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(2, weight=1) # Notebook area expands
        
        # 1. Header (Banca, Status)
        self._build_header(self.main_container)
        
        # 2. Painel de Resultados Recentes
        self._build_recent_results_panel(self.main_container)
        
        # 3. Recomendação Principal (Big Text)
        self._build_recommendation_panel(self.main_container)
        
        # 4. Painel de Controle e Entrada (Input + Botões)
        self._build_input_control_panel(self.main_container)
        
        # 5. Notebook Principal (Abas)
        self._build_notebook(self.main_container)
        
    def _build_header(self, parent):
        """Constrói o cabeçalho."""
        header_frame = tk.Frame(parent, bg="#e0e0e0", height=40)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        lbl_banca = tk.Label(header_frame, textvariable=self.banca_var, 
                             font=self.theme.FONT_BANCA, bg="#e0e0e0", fg="blue")
        lbl_banca.pack(side="left", padx=20)
        
        lbl_status = tk.Label(header_frame, textvariable=self.status_var,
                              font=("Arial", 10), bg="#e0e0e0")
        lbl_status.pack(side="right", padx=20)

    def _build_recent_results_panel(self, parent):
        """Fita de Resultados Recentes."""
        from ui.panels.results_panel import ResultsPanel
        # Wrapper frame managed by grid
        container = tk.Frame(parent, bg="#f0f0f0")
        container.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.results_panel = ResultsPanel(container, self.controller, self.theme)

    def _build_recommendation_panel(self, parent):
        """Label gigante com a sugestão de ação."""
        lbl_acao = tk.Label(parent, textvariable=self.acao_var, 
                            font=self.theme.FONT_RECOMENDACAO, 
                            bg="#f0f0f0", fg="black", wraplength=1000)
        lbl_acao.grid(row=2, column=0, sticky="ew", pady=5)

    def _build_input_control_panel(self, parent):
        """Painel de Entrada e Controles."""
        from ui.panels.input_panel import InputPanel
        # Wrapper frame managed by grid
        container = tk.Frame(parent, bg="#f0f0f0")
        container.grid(row=3, column=0, sticky="ew", pady=10)
        self.input_panel = InputPanel(container, self.controller, self.theme)

    def _build_notebook(self, parent):
        """Notebook com as abas principais."""
        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)
        
        # Importar Abas
        from ui.tabs.microservice_tab import MicroserviceTab
        from ui.tabs.strategies_tab import StrategiesTab
        from ui.tabs.analysis_tab import AnalysisTab
        
        # Aba Microserviço
        self.tab_microservico = MicroserviceTab(self.notebook, self.controller, self.theme)
        self.notebook.add(self.tab_microservico.frame, text="Microserviço")
        
        # Aba Estratégias
        self.tab_estrategias = StrategiesTab(self.notebook, self.controller, self.theme)
        self.notebook.add(self.tab_estrategias.frame, text="Estratégias")
        
        # Aba Análises
        self.tab_analises = AnalysisTab(self.notebook, self.controller, self.theme)
        self.notebook.add(self.tab_analises.frame, text="Análises & Logs")

    def update_status(self, message):
        """Atualiza a barra de status (Thread-safe via after se necessário)."""
        self.status_var.set(message)

    def atualizar_tela(self, ultimo_numero, resultado_analise):
        """Recebe update do controller e distribui para os sub-componentes."""
        # Atualizar Fita de Resultados
        # Atualizar Banca
        # Atualizar Abas Ativas
        pass
    
    def processar_update_async(self, ultimo_numero, resultado_analise):
        """Wrapper thread-safe para atualizar_tela."""
        self.root.after(0, lambda: self.atualizar_tela(ultimo_numero, resultado_analise))
