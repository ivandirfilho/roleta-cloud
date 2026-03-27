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

from core.logging_config import setup_logging
from server.websocket import start_server, game_state

logger = setup_logging()


def handle_shutdown(signum, frame):
    """Handler para shutdown graceful."""
    logger.info("shutdown_requested", signal=signum)
    game_state.save()
    # Finalizar sessão ativa no DB (atualiza stats + end_time)
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
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Ler versão do arquivo VERSION
    version = "unknown"
    try:
        with open("VERSION", "r") as f:
            version = f.read().strip()
    except FileNotFoundError:
        pass
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║              🎰 ROLETA CLOUD v{version:<24s}  ║
    ║                                                           ║
    ║  Backend para processamento de roleta em tempo real       ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        handle_shutdown(None, None)


if __name__ == "__main__":
    main()
