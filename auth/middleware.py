# Roleta Cloud - Auth Middleware

from app_config.settings import settings


async def verify_auth(token: str | None) -> bool:
    """
    Verifica autenticação.
    
    Se AUTH_ENABLED=False (padrão), sempre retorna True (bypass).
    Se AUTH_ENABLED=True, valida o token JWT com Keycloak.
    
    Args:
        token: Token JWT ou None
        
    Returns:
        True se autorizado, False caso contrário
    """
    # Bypass mode - sempre autorizado
    if not settings.auth.enabled:
        return True
    
    # Token obrigatório quando auth está ativo
    if not token:
        return False
    
    # TODO: Implementar validação JWT com Keycloak
    # Por enquanto, aceita qualquer token não vazio
    return len(token) > 0


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
    
    # TODO: Decodificar JWT e extrair claims
    return {
        "user_id": "unknown",
        "username": "unknown",
        "roles": []
    }
