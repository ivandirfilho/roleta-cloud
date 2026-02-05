# RoletaV11/ui/panels/results_panel.py

import tkinter as tk
from ui.styles import Theme
from core import config

class ResultsPanel:
    """
    Fita de Resultados Recentes.
    Mostra os últimos N números sorteados com indicadores de direção e status (vitória/derrota).
    """
    def __init__(self, parent, controller, theme):
        self.parent = parent
        self.controller = controller
        self.theme = theme
        self.frame = None
        
        self.result_display_units = [] # Lista de dicts {'btn': Widget, 'arrow': Widget}
        
        self.build()

    def build(self):
        """Constrói a fita de resultados."""
        self.frame = tk.Frame(self.parent, bg="#f0f0f0")
        self.frame.pack(fill="x", padx=10, pady=5)
        
        # Scrollable container? Não, o original era fixo (12 itens).
        # Vamos manter fixo para simplicidade e paridade.
        
        # Criar 12 slots para histórico recente
        for i in range(config.MAX_HISTORY_DISPLAY_TOP):
            frame_unit = tk.Frame(self.frame, bg="#e0e0e0", bd=1, relief="ridge")
            frame_unit.pack(side="left", padx=2, fill="y")
            
            # Label de Direção (Seta)
            arrow_label = tk.Label(frame_unit, text="", font=("Arial", 10, "bold"), bg="#e0e0e0", fg="blue")
            arrow_label.pack(side="top", pady=(2,0))
            
            # Botão do Número
            btn = tk.Button(frame_unit, text="", font=self.theme.FONT_BUTTONS_TOP_NUM,
                           width=3, height=1, state=tk.DISABLED,
                           disabledforeground="black")
            btn.pack(side="bottom", padx=2, pady=2)
            
            self.result_display_units.append({'btn': btn, 'arrow': arrow_label})
            
    def update_display(self, historico_recente):
        """
        Atualiza a fita com os dados do histórico.
        historico_recente: Lista de dicts de jogadas (mais recente primeiro? ou ordem cronológica?)
        No original: self.controller.game_state_manager.historico_resultados_top (indice 0 = mais recente)
        """
        for i, unit in enumerate(self.result_display_units):
            btn = unit['btn']
            arrow = unit['arrow']
            
            if i < len(historico_recente):
                jogada = historico_recente[i]
                
                # Extrair dados com segurança
                num = jogada.get('numero', '--')
                direcao = jogada.get('direcao', '')
                
                # Cor do número
                cor_nome = config.ROULETTE_NUMBER_DEFINITIONS.get(num, "black") if isinstance(num, int) else "black"
                bg_color = Theme.get_color(cor_nome)
                fg_color = "white" if cor_nome != "green" else "black" # Verde no preto buga? Green no original é texto preto?
                if cor_nome == "green": fg_color = "black"
                
                # Texto
                btn.config(text=str(num), bg=bg_color, fg=fg_color, state=tk.NORMAL)
                
                # Seta
                arrow_text = ""
                if direcao == "horario": arrow_text = "→"
                elif direcao == "anti-horario" or direcao == "antihorario": arrow_text = "←"
                arrow.config(text=arrow_text)
                
                # Borda de Vitória/Derrota (se houver essa info no histórico)
                # O GameState pode enriquecer o histórico com 'win'/'loss'
                # Por hora, resetamos
                btn.config(relief="raised", bd=2)
                
            else:
                # Slot vazio
                btn.config(text="", bg="#cccccc", state=tk.DISABLED)
                arrow.config(text="")
