# Roleta Cloud - Auth Middleware

import hmac
import logging
import os

from app_config.settings import settings

logger = logging.getLogger(__name__)

# API key carregada de variável de ambiente (nunca hardcoded)
_API_KEY = os.environ.get("ROLETA_API_KEY", "")


async def verify_auth(token: str | None) -> bool:
    """
    Verifica autenticação.
    
    Se AUTH_ENABLED=False (padrão), sempre retorna True (bypass).
    Se AUTH_ENABLED=True, valida o token via API key (HMAC-safe).
    
    Args:
        token: API key ou None
        
    Returns:
        True se autorizado, False caso contrário
    """
    if not settings.auth.enabled:
        return True
    
    if not token:
        logger.warning("🔒 Conexão rejeitada: token ausente")
        return False
    
    if not _API_KEY:
        logger.error("🔒 ROLETA_API_KEY não configurada! Defina a variável de ambiente.")
        return False
    
    # Comparação segura contra timing attacks
    is_valid = hmac.compare_digest(token, _API_KEY)
    if not is_valid:
        logger.warning("🔒 Conexão rejeitada: token inválido")
    return is_valid


def get_user_from_token(token: str) -> dict:
    """
    Extrai informações do usuário do token.
    
    Returns:
        Dict com user_id, username, roles, etc.
    """
    if not settings.auth.enabled:
        return {
            "user_id": "anonymous",
            "username": "anonymous",
            "roles": ["user"]
        }
    
    # Com API key, todos os dispositivos autenticados são "operator"
    return {
        "user_id": "operator",
        "username": "operator",
        "roles": ["user", "operator"]
    }
