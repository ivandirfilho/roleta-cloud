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

from server.websocket import start_server, game_state


def handle_shutdown(signum, frame):
    """Handler para shutdown graceful."""
    print("\n🛑 Encerrando servidor...")
    game_state.save()
    print("💾 Estado salvo.")
    sys.exit(0)


def main():
    """Ponto de entrada principal."""
    # Registrar handler de shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║              🎰 ROLETA CLOUD v1.0.0                       ║
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
