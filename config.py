# Roleta Cloud - Configurações

import os
from pathlib import Path

# ============================================================================
# PATHS
# ============================================================================
BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
LOG_FILE = BASE_DIR / "roleta.log"

# ============================================================================
# SERVER
# ============================================================================
WS_HOST = os.getenv("WS_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("WS_PORT", "8765"))

# SSL - Caminhos dos certificados (Let's Encrypt)
SSL_ENABLED = os.getenv("SSL_ENABLED", "false").lower() == "true"
SSL_CERT = os.getenv("SSL_CERT", "/etc/letsencrypt/live/roleta.seudominio.com/fullchain.pem")
SSL_KEY = os.getenv("SSL_KEY", "/etc/letsencrypt/live/roleta.seudominio.com/privkey.pem")

# ============================================================================
# AUTH (Keycloak - Bypass mode por padrão)
# ============================================================================
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "roleta")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "roleta-cloud")

# ============================================================================
# GAME
# ============================================================================
MAX_TIMELINE_SIZE = 45  # Máximo de forças por direção
SDA_FORCES_ANALYZED = 4  # Forças usadas pela SDA

# ============================================================================
# ROULETTE WHEEL (Sequência física europeia)
# ============================================================================
WHEEL_SEQUENCE = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26
]

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}
