#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Roleta Cloud - Dashboard de Monitoramento

Exibe logs em tempo real e status do servidor.
Uso: python dashboard.py
"""

import subprocess
import sys
import time
from datetime import datetime

SERVER_IP = "187.45.181.75"
SSH_CMD = f"ssh root@{SERVER_IP}"

def clear_screen():
    """Limpa a tela do terminal."""
    print("\033[2J\033[H", end="")

def run_ssh(cmd: str) -> str:
    """Executa comando via SSH e retorna output."""
    try:
        result = subprocess.run(
            f'{SSH_CMD} "{cmd}"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Erro: {e}"

def get_status():
    """Obtém status do serviço."""
    return run_ssh("systemctl is-active roleta-cloud")

def get_last_logs(lines: int = 20):
    """Obtém últimas linhas de log."""
    return run_ssh(f"tail -n {lines} /root/roleta-cloud/server.log")

def get_connections():
    """Conta conexões ativas na porta 8765."""
    output = run_ssh("ss -tn | grep :8765 | wc -l")
    try:
        return int(output)
    except:
        return 0

def display_dashboard():
    """Exibe o dashboard."""
    clear_screen()
    
    status = get_status()
    connections = get_connections()
    logs = get_last_logs(15)
    
    status_emoji = "🟢" if status == "active" else "🔴"
    
    print("=" * 60)
    print("       🎰 ROLETA CLOUD - DASHBOARD DE MONITORAMENTO")
    print("=" * 60)
    print()
    print(f"  ⏰ Última atualização: {datetime.now().strftime('%H:%M:%S')}")
    print(f"  {status_emoji} Status: {status.upper()}")
    print(f"  🔌 Conexões ativas: {connections}")
    print(f"  🌐 URL: wss://roleta.xma-ia.com:8765")
    print()
    print("-" * 60)
    print("  📋 ÚLTIMOS LOGS:")
    print("-" * 60)
    
    for line in logs.split("\n")[-15:]:
        # Colorir logs
        if "[ERROR]" in line or "❌" in line:
            print(f"  \033[91m{line}\033[0m")  # Vermelho
        elif "[INFO]" in line and ("APOSTAR" in line or "✅" in line):
            print(f"  \033[92m{line}\033[0m")  # Verde
        elif "[WARNING]" in line or "⚠️" in line:
            print(f"  \033[93m{line}\033[0m")  # Amarelo
        else:
            print(f"  {line}")
    
    print()
    print("-" * 60)
    print("  [R] Reiniciar servidor | [Q] Sair | [Enter] Atualizar")
    print("-" * 60)

def restart_server():
    """Reinicia o servidor."""
    print("\n  ⏳ Reiniciando servidor...")
    run_ssh("systemctl restart roleta-cloud")
    time.sleep(2)
    print("  ✅ Servidor reiniciado!")
    time.sleep(1)

def main():
    """Loop principal do dashboard."""
    print("🎰 Iniciando Dashboard...")
    
    while True:
        try:
            display_dashboard()
            
            # Esperar input do usuário com timeout
            import select
            import sys
            
            # Windows não suporta select em stdin, usar input simples
            if sys.platform == "win32":
                try:
                    import msvcrt
                    if msvcrt.kbhit():
                        key = msvcrt.getch().decode().lower()
                        if key == 'q':
                            print("\n  👋 Tchau!")
                            break
                        elif key == 'r':
                            restart_server()
                    else:
                        time.sleep(5)
                except:
                    time.sleep(5)
            else:
                # Linux/Mac
                i, _, _ = select.select([sys.stdin], [], [], 5)
                if i:
                    key = sys.stdin.read(1).lower()
                    if key == 'q':
                        print("\n  👋 Tchau!")
                        break
                    elif key == 'r':
                        restart_server()
                        
        except KeyboardInterrupt:
            print("\n  👋 Tchau!")
            break

if __name__ == "__main__":
    main()
