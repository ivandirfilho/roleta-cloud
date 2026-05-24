#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Roleta Cloud - Entry Point

Backend para processamento de roleta em tempo real.
Recebe spins via WebSocket e retorna sugestões.

Uso:
    python main.py                    # Sem SSL
    SSL_ENABLED=true python main.py   # Com SSL

Variáveis de ambiente:
    WS_HOST      - Host do servidor (default: 0.0.0.0)
    WS_PORT      - Porta do servidor (default: 8765)
    SSL_ENABLED  - Habilitar SSL (default: false)
    SSL_CERT     - Caminho do certificado
    SSL_KEY      - Caminho da chave privada
    AUTH_ENABLED - Habilitar autenticação (default: false)
"""

import asyncio
import signal
import sys
from pathlib import Path

from core.logging_config import setup_logging
from server.websocket import start_server, game_state
from server.health_server import start_health_server

logger = setup_logging()

# VF-3: subir logger 'database' para INFO em produção (ver hook fires)
import logging as _logging
_logging.getLogger("database").setLevel(_logging.INFO)

# BUG-MAIN-002 fix: Flag para prevenir double shutdown
_shutdown_called = False


def handle_shutdown(signum, frame):
    """Handler para shutdown graceful."""
    global _shutdown_called
    if _shutdown_called:
        return
    _shutdown_called = True
    
    logger.info("shutdown_requested", signal=signum)
    
    # BUG-MAIN-004 fix: try/except no save()
    try:
        game_state.save()
    except Exception as e:
        logger.error(f"Erro ao salvar estado: {e}")
    
    # Finalizar sessão ativa no DB
    try:
        from database.service import db_service
        from server.websocket import message_handler
        if hasattr(message_handler, 'current_session_id') and message_handler.current_session_id:
            db_service.end_session(message_handler.current_session_id)
    except Exception as e:
        logger.warning(f"Erro ao finalizar sessão no shutdown: {e}")
    
    logger.info("state_saved")
    sys.exit(0)


def main():
    """Ponto de entrada principal."""
    # Registrar handler de shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    try:
        signal.signal(signal.SIGTERM, handle_shutdown)
    except (OSError, AttributeError):
        pass  # BUG-MAIN-001: SIGTERM não existe no Windows
    
    # Ler versão do arquivo VERSION (path relativo ao script)
    version = "unknown"
    try:
        version_file = Path(__file__).parent / "VERSION"
        with open(version_file, "r") as f:
            version = f.read().strip()
    except FileNotFoundError:
        pass
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║              🎰 ROLETA CLOUD v{version:<24s}  ║
    ║                                                           ║
    ║  Backend para processamento de roleta em tempo real       ║
    ║  Estratégia: M15-ADA (17 números, offset adaptativo)     ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    try:
        # VF-3/VF-4: iniciar health server (/health + /metrics) ANTES do WS loop
        start_health_server()
        asyncio.run(start_server())
    except KeyboardInterrupt:
        handle_shutdown(None, None)


if __name__ == "__main__":
    main()
