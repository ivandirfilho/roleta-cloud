# RoletaV11/ui/styles.py
import tkinter as tk
from core import config

class Theme:
    """
    Centraliza os estilos e cores da interface.
    Utiliza as configurações definidas em core.config.
    """
    
    COLORS = config.TKINTER_COLORS
    
    # Fontes
    FONT_BUTTONS_TOP_NUM = config.FONT_BUTTONS_TOP_NUM
    FONT_SUGESTAO_PRINCIPAL_TEXT = config.FONT_SUGESTAO_PRINCIPAL_TEXT
    FONT_ANALISE = config.FONT_ANALISE_text
    FONT_HISTORICO_TITULO = config.FONT_HISTORICO_50_TITULO
    FONT_BANCA = config.FONT_BANCA
    FONT_LOG = config.FONT_LOG_APOSTAS
    FONT_INPUT_LABEL = config.FONT_MANUAL_ENTRY_LABEL
    FONT_INPUT_BTN = config.FONT_MANUAL_ENTRY_BUTTON
    FONT_RECOMENDACAO = config.FONT_RECOMENDACAO_LABEL
    FONT_SIMULACAO_BTN = config.FONT_SIMULACAO_BUTTON
    FONT_MARTINGALE = config.FONT_MARTINGALE_LABEL
    FONT_WEBSCRAP = config.FONT_WEBSCRAP_LABEL
    FONT_WEBSCRAP_DISPLAY = config.FONT_WEBSCRAP_DISPLAY
    FONT_ESTRATEGIA = config.FONT_ESTRATEGIA_LABEL
    FONT_PERFORMANCE = config.FONT_PERFORMANCE_LABEL
    
    @staticmethod
    def apply_global_styles(root):
        """Aplica configurações globais ao root."""
        # Se houver configurações globais de estilo (ttk.Style), aplicar aqui
        pass

    @staticmethod
    def get_color(name: str):
        return Theme.COLORS.get(name, "#000000")
