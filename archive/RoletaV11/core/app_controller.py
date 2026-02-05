# RoletaV11/core/app_controller.py

import threading
import time
from typing import Optional

from core.game_state import GameStateManager
from core.simulation import SimulationManager
from core import config

class AppController:
    """
    Controlador principal da aplicação.
    Coordena a interação entre UI, GameState e Simulação.
    """
    def __init__(self):
        self.ui = None # Será injetado depois (referência circular resolvida via injeção)
        
        # Inicializar Core Logic
        self.game_state = GameStateManager(app_controller=self)
        self.simulation = SimulationManager(game_state_manager=self.game_state)
        
        # Estado atual
        self.running = True
        print("AppController inicializado.")

    def register_ui(self, main_window):
        """Registra a referência da UI."""
        self.ui = main_window

    def start_simulation(self):
        """Dispara simulação via SimulationManager."""
        self.simulation.start_simulation(ui_ref=self.ui)
        if self.ui:
            self.ui.update_status("Simulação INICIADA")

    def stop_simulation(self):
        """Para simulação."""
        self.simulation.stop_simulation()
        if self.ui:
            self.ui.update_status("Simulação PARADA")

    def atualizar_ui(self, ultimo_numero: dict, resultado_analise: dict):
        """
        Callback chamado pelo GameStateManager quando há novos dados.
        Deve garantir que a atualização da UI ocorra na thread correta.
        """
        if not self.ui:
            return

        # Como Tkinter não é thread-safe, e isso pode vir de uma thread de simulação,
        # usamos root.after ou similar se disponível, ou confiamos que a UI handle isso.
        
        # Se a UI tiver um método thread-safe 'processar_update', chamamos ele
        if hasattr(self.ui, 'processar_update_async'):
             self.ui.processar_update_async(ultimo_numero, resultado_analise)
        else:
            # Tentar agendar no main loop se tiver acesso ao root
            if hasattr(self.ui, 'root'):
                self.ui.root.after(0, lambda: self.ui.atualizar_tela(ultimo_numero, resultado_analise))
    
    def on_app_close(self):
        """Limpeza ao fechar o app."""
        print("Finalizando aplicação...")
        self.stop_simulation()
        # Salvar estado final
        self.game_state.persistence.save_data({
            'historico': self.game_state.historico_jogadas,
            'banca': self.game_state.banca_atual
        })
