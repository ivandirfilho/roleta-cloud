# RoletaV11/core/config.py

"""
Arquivo de Configuração Central para o Roleta V11 (Clean).
"""

# --- 1. ARQUIVOS E PERSISTÊNCIA ---
NOME_ARQUIVO_DADOS_JSON = "roleta_dados_salvos.json"
NOME_ARQUIVO_LOG_TXT = "log_de_apostas_completo.txt"
CAMINHO_CREDENCIAL = "firebase-credentials.json"
NOME_ARQUIVO_SDA_DATALAKE_DB = "sda_datalake.db"

# --- 1.1. PERFORMANCE SETTINGS ---
UI_UPDATE_THROTTLE_MS = 100    # Mínimo tempo entre updates da UI (ms)
ENABLE_DEBUG_PRINTS = False    # Desabilitar prints de debug para produção


# --- 2. LÓGICA DA ROLETA (Constantes Físicas) ---
ROULETTE_WHEEL_ORDER = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26
]

ROULETTE_NUMBER_DEFINITIONS = {
    0: "green", 1: "red", 2: "black", 3: "red", 4: "black", 5: "red",
    6: "black", 7: "red", 8: "black", 9: "red", 10: "black", 11: "black",
    12: "red", 13: "black", 14: "red", 15: "black", 16: "red", 17: "black",
    18: "red", 19: "red", 20: "black", 21: "red", 22: "black", 23: "red",
    24: "black", 25: "red", 26: "black", 27: "red", 28: "black", 29: "black",
    30: "red", 31: "black", 32: "red", 33: "black", 34: "red", 35: "black",
    36: "red"
}

NUMEROS_CHAVE_MICRO_REGIOES = [15, 21, 17, 27, 11, 23, 24, 1, 31, 18, 28, 3]

# --- 3. PARÂMETROS DE APOSTA E FINANCEIROS ---
BANCA_INICIAL = 2000.0
CUSTO_POR_NUMERO_BASE = 0.50
PAYOUT_FACTOR = 36
WHEEL_SIZE = len(ROULETTE_WHEEL_ORDER)

# --- 4. PARÂMETROS DAS ESTRATÉGIA (Tuning) ---
FORCA_HISTORICO_FORCAS_ANALISADAS = 6
FORCA_FATOR_AJUSTE_DINAMICO = 3.0
FORCA_VIZINHOS_APOSTA = 4
INERCIA_TAMANHO_CESTA_CLUSTER = 11
INERCIA_MIN_FORCAS_NO_CLUSTER = 3
INERCIA_VIZINHOS_APOSTA = 5
MRA_FATOR_CONFIANCA_VITORIA = 0.15
MRA_FATOR_CONFIANCA_DERROTA = -0.25
MRA_VIZINHOS_APOSTA = 9
HIBRIDA_LIMITE_CAOS_CONVERGENCE = 4
HIBRIDA_VIZINHOS_APOSTA = 2
HIBRIDA_AMPLA_VIZINHOS_APOSTA = 3
ESP_JANELA_CLUSTER = 7
ESP_MIN_FORCAS_CLUSTER = 2
ESP_VIZINHOS_APOSTA = 2

# --- 10. PARÂMETROS ESTRATÉGIA SINERGIA DIRECIONAL AVANÇADA (SDA) ---
SDA_FORCAS_ANALISADAS = 4
SDA_VIZINHOS_APOSTA = 5 
SDA_CENTROS_ELEITOS = 1 
SDA_MIN_CLUSTER_SCORE_PARA_APOSTAR = 3
SDA_MEMORY_WEIGHTS = [0.40, 0.25, 0.15, 0.10, 0.05, 0.05]
SDA_VECTOR_CACHE_SIZE = 256
SDA_FORCA_MIN = 1
SDA_FORCA_MAX = 37
SDA_FORCA_DEFAULT = 18

# --- 10.1. PARÂMETROS SDA MULTI-VARIÁVEL ---
SDA_VARIACOES_CONFIG = {
    "SDA-7": {
        "raio_gravidade": 7,
        "num_vizinhos": 3,
        "forca_gravitacional_media": 7,
        "total_numeros": 7
    },
    "SDA-9": {
        "raio_gravidade": 9,
        "num_vizinhos": 4,
        "forca_gravitacional_media": 9,
        "total_numeros": 9
    },
    "SDA-11": {
        "raio_gravidade": 11,
        "num_vizinhos": 5,
        "forca_gravitacional_media": 11,
        "total_numeros": 11
    },
    "SDA-17": {
        "raio_gravidade": 17,
        "num_vizinhos": 8,
        "forca_gravitacional_media": 17,
        "total_numeros": 17
    }
}

SDA_SELECAO_ROI_JANELA = 12
SDA_SELECAO_MODELO = "ROI_MEDIO"

# --- 10.2. PARÂMETROS SDA ESPELHO ---
SDA_ESPELHO_VIZINHOS_APOSTA = 1
SDA_ESPELHO_TOTAL_FORCAS = 4
SDA_ESPELHO_TOTAL_NUMEROS_ESPERADO = 12

# --- 11. PARÂMETROS DO ORÁCULO QUÂNTICO (SACA/SPDE) ---
SACA_MODO_OPERACAO = 'ATIVO'
SACA_BOOTSTRAP_RODADAS_MINIMAS = 6
SACA_DATA_LAKE_VIZINHOS = 50
SACA_MOMENTUM_JANELA = 40
SACA_PROBABILIDADE_EXPLORACAO = 0.05
SACA_ANN_TREES = 10
SACA_FALLBACK_VETOR = 'V_REVERSION'
SACA_W_CONTEXTO = 0.7
SACA_W_MOMENTUM = 0.3

SPDE_ENTROPY_THRESHOLD = 2.4
SPDE_W_CONTEXTO_ORDEM = 0.7
SPDE_W_MOMENTUM_ORDEM = 0.3
SPDE_W_CONTEXTO_CAOS = 0.3
SPDE_W_MOMENTUM_CAOS = 0.7
SPDE_GRADIENT_ERROR_SCALE = 10.0

# --- 5. PARÂMETROS DE UI E SIMULAÇÃO ---
MAX_HISTORICO_JOGADAS = 45
MAX_HISTORY_DISPLAY_TOP = 12
MAX_HISTORY_DISPLAY_BOTTOM = 50
MAX_PREDICTION_HISTORY = 12
SIMULACAO_INTERVALO_MS = 500

TKINTER_COLORS = {
    "red": "#FF4136", "black": "#333333", "green": "#2ECC40",
    "disabled": "#D3D3D3", "win_border": "darkgreen", "loss_border": "darkred",
    "hit_color": "#4CAF50", "miss_color": "#F44336", "neutral_color": "#BDBDBD",
    "active_strategy_bg": "#E8F5E9", "button_primary": "#B0E0E6",
    "button_secondary": "#DDEEFF", "button_success": "#90EE90", "button_danger": "#FFA07A",
    "protagonist_bg": "#FFF9C4", "protagonist_border": "#FBC02D"
}

# Fontes Atualizadas
FONT_BUTTONS_TOP_NUM = ("Arial", 18, "bold")
FONT_SUGESTAO_PRINCIPAL_TEXT = ("Arial", 20, "italic")
FONT_ANALISE_text = ("Arial", 9)
FONT_HISTORICO_50_TITULO = ("Arial", 12, "underline")
FONT_BANCA = ("Arial", 14, "bold")
FONT_LOG_APOSTAS = ("Courier New", 9)
FONT_MANUAL_ENTRY_LABEL = ("Arial", 10)
FONT_MANUAL_ENTRY_BUTTON = ("Arial", 10, "bold")
FONT_RECOMENDACAO_LABEL = ("Arial", 16, "bold")
FONT_SIMULACAO_BUTTON = ("Arial", 10, "bold")
FONT_MARTINGALE_LABEL = ("Arial", 10, "bold")
FONT_WEBSCRAP_LABEL = ("Arial", 10)
FONT_WEBSCRAP_DISPLAY = ("Arial", 14, "bold")
FONT_ESTRATEGIA_LABEL = ("Arial", 10, "bold")
FONT_PERFORMANCE_LABEL = ("Arial", 9, "italic")
