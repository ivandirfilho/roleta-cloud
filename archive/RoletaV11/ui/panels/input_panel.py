# RoletaV11/ui/panels/input_panel.py

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json
from core import config

class InputPanel:
    """
    Painel de Entrada de Dados e Controles Principais.
    Contém:
    - Botões Manuais (0-36)
    - Botão Desfazer
    - 🆕 Botão Escuta Beat (WebSocket listener)
    """
    def __init__(self, parent, controller, theme):
        self.parent = parent
        self.controller = controller
        self.theme = theme
        self.frame = None
        self.btn_map = {}
        
        # 🆕 Estado do Escuta Beat
        self.escuta_beat_ativo = False
        self.ws_thread = None
        self.ws_running = False
        
        self.build()

    def build(self):
        """Constrói o layout do painel."""
        self.frame = tk.Frame(self.parent, bg="#f0f0f0", bd=2, relief="groove")
        self.frame.pack(fill="x", padx=5, pady=5)
        
        # 🆕 Frame superior com botão Escuta Beat
        control_frame = tk.Frame(self.frame, bg="#f0f0f0")
        control_frame.pack(side="top", fill="x", pady=5)
        
        self.btn_escuta_beat = tk.Button(
            control_frame, 
            text="🔌 ESCUTA BEAT: DESLIGADO",
            bg="#444444", fg="white",
            font=("Arial", 10, "bold"),
            width=30,
            command=self._toggle_escuta_beat
        )
        self.btn_escuta_beat.pack(side="left", padx=10)
        
        self.lbl_escuta_status = tk.Label(
            control_frame,
            text="Clique para ativar recepção automática",
            bg="#f0f0f0", fg="#666666",
            font=("Arial", 9)
        )
        self.lbl_escuta_status.pack(side="left", padx=10)
        
        # Sub-frame para botões numéricos
        self.num_frame = tk.Frame(self.frame, bg="#f0f0f0")
        self.num_frame.pack(side="top", pady=5)
        
        # O 0
        btn_zero = self._create_number_button(self.num_frame, 0, "green")
        btn_zero.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=2, pady=2)
        
        # 1-36
        for n in range(1, 37):
            color_name = config.ROULETTE_NUMBER_DEFINITIONS.get(n, "black")
            bg_color = config.TKINTER_COLORS.get(color_name, "black")
            c = (n - 1) // 3 + 1
            r = 2 - ((n - 1) % 3)
            btn = self._create_number_button(self.num_frame, n, bg_color)
            btn.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)

        # Botão Desfazer
        undo_frame = tk.Frame(self.frame, bg="#f0f0f0")
        undo_frame.pack(side="top", fill="x", pady=5)
        
        btn_undo = tk.Button(undo_frame, text="DESFAZER ÚLTIMO", 
                             bg=config.TKINTER_COLORS['button_danger'],
                             command=self._on_undo_click)
        btn_undo.pack(side="right", padx=10)

    def _create_number_button(self, parent, number, bg_color):
        fg_color = "white"
        btn = tk.Button(parent, text=str(number), 
                        bg=bg_color, fg=fg_color,
                        font=self.theme.FONT_INPUT_BTN,
                        width=4, height=2,
                        command=lambda n=number: self._on_number_click(n))
        self.btn_map[number] = btn
        return btn

    def _on_number_click(self, number):
        """Callback ao clicar num número."""
        if self.escuta_beat_ativo:
            return
            
        from core.simulation import NovaJogadaInfo
        
        info = NovaJogadaInfo(
            numero=number,
            fonte="manual",
            direcao="indefinida",
            dealer="Manual",
            modelo="Manual",
            provedor="Manual"
        )
        
        last_dir = "horario"
        if self.controller.game_state.historico_jogadas:
            last_dir = self.controller.game_state.historico_jogadas[-1]['direcao']
        
        info.direcao = "anti-horario" if last_dir == "horario" else "horario"
        self.controller.game_state.processar_novo_numero(info)

    def _on_undo_click(self):
        messagebox.showinfo("Indisponível", "Função Desfazer ainda não migrada.")

    # ===== 🆕 ESCUTA BEAT =====
    def _toggle_escuta_beat(self):
        if not self.escuta_beat_ativo:
            self._start_escuta_beat()
        else:
            self._stop_escuta_beat()
    
    def _start_escuta_beat(self):
        self.escuta_beat_ativo = True
        self.ws_running = True
        
        self.btn_escuta_beat.config(text="🔌 ESCUTA BEAT: LIGADO", bg="#00aa44")
        self.lbl_escuta_status.config(text="Aguardando dados...", fg="#00aa44")
        
        for btn in self.btn_map.values():
            btn.config(state="disabled")
        
        self.ws_thread = threading.Thread(target=self._ws_listener, daemon=True)
        self.ws_thread.start()
    
    def _stop_escuta_beat(self):
        self.escuta_beat_ativo = False
        self.ws_running = False
        
        self.btn_escuta_beat.config(text="🔌 ESCUTA BEAT: DESLIGADO", bg="#444444")
        self.lbl_escuta_status.config(text="Clique para ativar", fg="#666666")
        
        for btn in self.btn_map.values():
            btn.config(state="normal")
    
    def _ws_listener(self):
        """Thread que escuta o arquivo live_results.json"""
        import time
        from pathlib import Path
        
        # 🔧 Corrigido: "Extrator Beat" com maiúsculas
        results_file = Path(__file__).parent.parent.parent / "Extrator Beat" / "Integracao Escuta x Roleta" / "logs" / "live_results.json"
        print(f"📂 Monitorando: {results_file}")
        print(f"   Existe: {results_file.exists()}")
        
        last_count = 0
        
        while self.ws_running:
            try:
                if results_file.exists():
                    with open(results_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    current_count = data.get("total_results", 0)
                    
                    if current_count > last_count:
                        history = data.get("history", [])
                        
                        if last_count == 0:
                            # Batch inicial
                            self.parent.after(0, lambda h=history: self._process_batch(h))
                        else:
                            # Novo resultado
                            if history:
                                self.parent.after(0, lambda h=history[0]: self._process_single(h))
                        
                        last_count = current_count
                
                time.sleep(1)
                
            except Exception as e:
                print(f"Erro leitura: {e}")
                time.sleep(2)
    
    def _process_single(self, result):
        """Processa um resultado"""
        from core.simulation import NovaJogadaInfo
        
        numero = result.get("numero")
        direcao = result.get("direcao", "horario")
        
        info = NovaJogadaInfo(
            numero=numero, fonte="escuta_beat", direcao=direcao,
            dealer="", modelo="", provedor=""
        )
        
        self.controller.game_state.processar_novo_numero(info)
        
        dir_emoji = "⬅️" if direcao == "horario" else "➡️"
        self.lbl_escuta_status.config(text=f"Último: {numero} {dir_emoji}", fg="#00aa44")
    
    def _process_batch(self, history):
        """Processa batch inicial"""
        for r in reversed(history):
            self._process_single(r)
        
        self.lbl_escuta_status.config(text=f"✅ {len(history)} números carregados", fg="#00aa44")
