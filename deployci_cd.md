# 🚀 Deploy CI/CD — Roleta Cloud v3.5.0

> **Objetivo:** Guia completo e executável para o agente realizar deploy após alterações no código.  
> **Fluxo:** Local → GitHub (push) → Servidor Debian (Docker)  
> **Repositório:** `https://github.com/ivandirfilho/roleta-cloud.git`  
> **Branch de produção:** `main`  
> **Servidor:** `root@187.45.181.75` (Debian)  
> **Domínio:** `roleta.xma-ia.com`  
> **Porta WebSocket:** `8765`

---

## ÍNDICE

1. [Pré-requisitos](#1-pré-requisitos)
2. [Fase 1 — Validação Local](#2-fase-1--validação-local)
3. [Fase 2 — Commit e Push para GitHub](#3-fase-2--commit-e-push-para-github)
4. [Fase 3 — Deploy no Servidor Debian (Docker)](#4-fase-3--deploy-no-servidor-debian-docker)
5. [Fase 4 — Verificação Pós-Deploy](#5-fase-4--verificação-pós-deploy)
6. [Rollback de Emergência](#6-rollback-de-emergência)
7. [Deploy Completo (Script Unificado)](#7-deploy-completo-script-unificado)
8. [Referência de Variáveis de Ambiente](#8-referência-de-variáveis-de-ambiente)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. PRÉ-REQUISITOS

### No ambiente local (Windows)

```powershell
# Verificar que Git está configurado
git --version
git config user.name
git config user.email

# Verificar que Python 3.12+ está disponível (para rodar testes locais)
python --version

# Verificar acesso SSH ao servidor
ssh -o ConnectTimeout=5 root@187.45.181.75 "echo 'SSH OK'"
```

### No servidor Debian (primeira vez apenas)

```bash
# Instalar Docker e Docker Compose (se ainda não instalados)
apt-get update && apt-get install -y docker.io docker-compose-plugin
systemctl enable docker && systemctl start docker

# Clonar repositório (primeira vez)
cd /root
git clone https://github.com/ivandirfilho/roleta-cloud.git
cd roleta-cloud

# Criar arquivo .env de produção
cat > .env << 'EOF'
WS_HOST=0.0.0.0
WS_PORT=8765
SSL_ENABLED=false
AUTH_ENABLED=false
ROLETA_API_KEY=
EOF

# Criar state.json inicial (se não existe)
[ ! -f state.json ] && echo '{}' > state.json

# Porta 8765 está restrita a 127.0.0.1 (localhost) via docker-compose.yml
# O acesso externo é feito via nginx reverse proxy (porta 443 com SSL)
# NÃO abrir porta 8765 no firewall — ela deve permanecer inacessível externamente
# ufw allow 443/tcp  ← já configurado para nginx (HTTPS + WSS)
```

---

## 2. FASE 1 — VALIDAÇÃO LOCAL

> **Regra:** Nunca fazer push sem validar. Todos os comandos abaixo devem passar antes de prosseguir.

### 2.1 Verificar estado do repositório

```powershell
cd "C:\Users\Windows\Desktop\Roleta Cloud"

# Status do Git — ver arquivos modificados
git --no-pager status

# Diff das mudanças (resumo)
git --no-pager diff --stat

# Diff completo (se necessário)
git --no-pager diff
```

### 2.2 Rodar testes

```powershell
# Instalar dependências de teste (se necessário)
pip install pytest pytest-asyncio

# Executar todos os testes
python -m pytest tests/ -v --tb=short

# Testes devem passar:
#   tests/test_core.py         — RouletteCore (cálculos circulares)
#   tests/test_sda17.py        — SDA-19 strategy (IQR, median, drift)
#   tests/test_bet_advisor.py  — Kill Switch Advisor (veto/aprovação)
#   tests/test_game_state.py   — GameState (process_spin, martingale)
#   tests/test_db_query.py     — Queries SQLite
```

### 2.3 Verificar imports e sintaxe

```powershell
# Verifica se o entry point importa corretamente
python -c "from server.websocket import start_server; print('Imports OK')"

# Verificar se a versão está coerente
$version = Get-Content VERSION
Write-Host "VERSION file: $version"
```

### 2.4 Verificar que secrets não estão no código

```powershell
# Buscar possíveis secrets hardcoded
git --no-pager diff --cached | Select-String -Pattern "sk-|password|secret|api_key|token" -CaseSensitive:$false
```

> ⚠️ **Se qualquer teste falhar, NÃO prossiga para a Fase 2. Corrija primeiro.**

---

## 3. FASE 2 — COMMIT E PUSH PARA GITHUB

### 3.1 Adicionar arquivos ao staging

```powershell
# Adicionar todos os arquivos modificados
git add -A

# OU adicionar seletivamente
git add core/ server/ state/ strategies/ database/ models/ auth/ app_config/ tests/
git add main.py requirements.txt VERSION Dockerfile docker-compose.yml

# Verificar o que será commitado
git --no-pager status
git --no-pager diff --cached --stat
```

### 3.2 Criar commit com mensagem descritiva

```powershell
# Formato: tipo(escopo): descrição curta
# Tipos: feat, fix, refactor, docs, test, chore, perf, security

# Exemplos:
git commit -m "fix(sda17): corrigir drift formula multiplicação 0.25→0.5

- Drift detection agora aplica int(sum(diffs) * 0.5) corretamente
- Predições mais responsivas a tendências de força
- Backtest validou melhoria na taxa de acerto

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"

# Ou para múltiplas mudanças:
git commit -m "feat(v3.5.1): correções pós-auditoria março/2026

- fix: drift SDA-19 (BUG-POST-001)
- fix: sanitizar ErrorOutput (BUG-POST-004)
- fix: banner versão hardcoded (BUG-POST-001)
- refactor: remover colunas mortas calibration
- docs: Manutenabilidade ISO 25010

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### 3.3 Push para GitHub

```powershell
# Push para branch main
git push origin main

# Se houver conflito (rejeição):
git pull --rebase origin main
# Resolver conflitos se necessário, depois:
git push origin main
```

### 3.4 Verificar que o push chegou

```powershell
# Confirmar que o commit está no remote
git --no-pager log --oneline -3 origin/main
```

### 3.5 (Opcional) Criar tag de versão

```powershell
# Ler versão do arquivo VERSION
$version = (Get-Content VERSION).Trim()

# Criar tag
git tag -a "v$version" -m "Release v$version"
git push origin "v$version"
```

---

## 4. FASE 3 — DEPLOY NO SERVIDOR DEBIAN (DOCKER)

### 4.1 Conectar no servidor e atualizar código

```powershell
# Comando único: pull + rebuild + restart
ssh root@187.45.181.75 "cd /root/roleta-cloud && git pull origin main"
```

### 4.2 Rebuild da imagem Docker

```powershell
# Rebuild com cache (mais rápido — só reconstrói layers alterados)
ssh root@187.45.181.75 "cd /root/roleta-cloud && docker compose build"

# OU rebuild sem cache (para mudanças em requirements.txt ou Dockerfile)
ssh root@187.45.181.75 "cd /root/roleta-cloud && docker compose build --no-cache"
```

### 4.3 Restart do container

```powershell
# Parar container antigo e iniciar com nova imagem
ssh root@187.45.181.75 "cd /root/roleta-cloud && docker compose down && docker compose up -d"

# Aguardar healthcheck (30s start_period + 30s interval)
Start-Sleep -Seconds 10
```

### 4.4 Verificar que o container subiu

```powershell
# Status do container
ssh root@187.45.181.75 "docker ps --filter name=roleta-cloud --format 'table {{.Status}}\t{{.Ports}}'"

# Deve mostrar algo como:
# Up X seconds (healthy)    127.0.0.1:8765->8765/tcp
```

### 4.5 Verificar logs do container

```powershell
# Últimas 30 linhas de log
ssh root@187.45.181.75 "docker logs roleta-cloud --tail 30"

# Logs em tempo real (Ctrl+C para sair)
ssh root@187.45.181.75 "docker logs roleta-cloud -f --tail 10"
```

### 4.6 Limpar imagens antigas (manutenção)

```powershell
# Remover imagens Docker não utilizadas (libera espaço)
ssh root@187.45.181.75 "docker image prune -f"
```

---

## 5. FASE 4 — VERIFICAÇÃO PÓS-DEPLOY

### 5.1 Healthcheck — Conexão WebSocket

```powershell
# Verificar que a porta está respondendo
ssh root@187.45.181.75 "python3 -c \"import socket; s=socket.socket(); s.settimeout(3); s.connect(('localhost', 8765)); s.close(); print('WebSocket OK')\""
```

### 5.2 Healthcheck — Docker nativo

```powershell
# Verificar healthcheck do Docker
ssh root@187.45.181.75 "docker inspect roleta-cloud --format='{{.State.Health.Status}}'"

# Deve retornar: healthy
```

### 5.3 Verificar versão em produção

```powershell
# Verificar que o commit correto está em produção
ssh root@187.45.181.75 "cd /root/roleta-cloud && git --no-pager log --oneline -1"

# Verificar arquivo VERSION
ssh root@187.45.181.75 "cat /root/roleta-cloud/VERSION"
```

### 5.4 Verificar banco de dados

```powershell
# Verificar que o SQLite está acessível e tem dados
ssh root@187.45.181.75 "docker exec roleta-cloud python -c \"
import sqlite3
conn = sqlite3.connect('/app/data/decisions.db')
tables = conn.execute(\\\"SELECT name FROM sqlite_master WHERE type='table'\\\").fetchall()
for t in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM {t[0]}').fetchone()[0]
    print(f'{t[0]}: {count} registros')
conn.close()
\""
```

### 5.5 Teste funcional (enviar spin de teste via WebSocket)

```powershell
# Testar conexão WebSocket com mensagem de teste
ssh root@187.45.181.75 "python3 -c \"
import asyncio, websockets, json

async def test():
    async with websockets.connect('ws://localhost:8765') as ws:
        msg = await ws.recv()
        data = json.loads(msg)
        print(f'Resposta: type={data.get(\\\"type\\\")}, role={data.get(\\\"role\\\", \\\"N/A\\\")}')
        print('WebSocket FUNCIONAL ✅')

asyncio.run(test())
\""
```

---

## 6. ROLLBACK DE EMERGÊNCIA

### 6.1 Rollback rápido (volta ao commit anterior)

```powershell
# Identificar commit anterior
ssh root@187.45.181.75 "cd /root/roleta-cloud && git --no-pager log --oneline -5"

# Reverter para commit específico
ssh root@187.45.181.75 "cd /root/roleta-cloud && git checkout <COMMIT_HASH> -- . && docker compose down && docker compose build && docker compose up -d"
```

### 6.2 Rollback para tag específica

```powershell
# Listar tags disponíveis
ssh root@187.45.181.75 "cd /root/roleta-cloud && git --no-pager tag -l --sort=-version:refname | head -5"

# Voltar para tag
ssh root@187.45.181.75 "cd /root/roleta-cloud && git checkout v3.5.0 -- . && docker compose down && docker compose build && docker compose up -d"
```

### 6.3 Rollback forçado (reset hard)

```powershell
# CUIDADO: descarta todas as mudanças locais no servidor
ssh root@187.45.181.75 "cd /root/roleta-cloud && git reset --hard origin/main~1 && docker compose down && docker compose build && docker compose up -d"
```

### 6.4 Backup do banco antes de deploy

```powershell
# ⚠️ O banco de produção está no Docker Named Volume (NÃO no host path)
# Backup via Docker exec (método correto):
ssh root@187.45.181.75 "docker exec roleta-cloud cp /app/data/decisions.db /app/data/decisions_backup_$(date +%Y%m%d_%H%M%S).db"

# Copiar backup para o host (opcional):
ssh root@187.45.181.75 "docker cp roleta-cloud:/app/data/decisions_backup_*.db /root/backups/ 2>/dev/null"
```

---

## 7. DEPLOY COMPLETO (SCRIPT UNIFICADO)

### 7.1 Deploy rápido (one-liner do Windows)

```powershell
# DEPLOY COMPLETO: test → commit → push → server pull → rebuild → restart → verify
# Substitua a mensagem de commit conforme necessário

python -m pytest tests/ -v --tb=short; if ($LASTEXITCODE -eq 0) { git add -A; git commit -m "deploy: atualização de produção`n`nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"; git push origin main; ssh root@187.45.181.75 "cd /root/roleta-cloud && git pull origin main && docker compose down && docker compose build && docker compose up -d && sleep 15 && docker ps --filter name=roleta-cloud && docker logs roleta-cloud --tail 5" } else { Write-Host "TESTES FALHARAM - Deploy cancelado" -ForegroundColor Red }
```

### 7.2 Deploy passo a passo (recomendado para mudanças grandes)

```powershell
# ===== PASSO 1: Validar localmente =====
cd "C:\Users\Windows\Desktop\Roleta Cloud"
python -m pytest tests/ -v --tb=short
# SE FALHOU → parar aqui

# ===== PASSO 2: Commit + Push =====
git add -A
git --no-pager status
git commit -m "feat: descrição das mudanças

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push origin main

# ===== PASSO 3: Backup no servidor =====
ssh root@187.45.181.75 "docker exec roleta-cloud cp /app/data/decisions.db /app/data/decisions_backup_$(date +%Y%m%d_%H%M%S).db 2>/dev/null; echo 'Backup OK'"

# ===== PASSO 4: Pull + Rebuild + Restart =====
ssh root@187.45.181.75 "cd /root/roleta-cloud && git pull origin main && docker compose down && docker compose build && docker compose up -d"

# ===== PASSO 5: Aguardar e verificar =====
Start-Sleep -Seconds 15
ssh root@187.45.181.75 "docker inspect roleta-cloud --format='{{.State.Health.Status}}' && docker logs roleta-cloud --tail 10"
```

### 7.3 Deploy com Docker sem cache (mudanças em requirements.txt)

```powershell
# Quando requirements.txt mudou, o cache do Docker layer de pip precisa ser invalidado
ssh root@187.45.181.75 "cd /root/roleta-cloud && git pull origin main && docker compose down && docker compose build --no-cache && docker compose up -d"
```

---

## 8. REFERÊNCIA DE VARIÁVEIS DE AMBIENTE

| Variável | Default | Descrição | Onde configurar |
|----------|---------|-----------|----------------|
| `WS_HOST` | `0.0.0.0` | Host do WebSocket server | `.env` ou `docker-compose.yml` |
| `WS_PORT` | `8765` | Porta do WebSocket server | `.env` ou `docker-compose.yml` |
| `SSL_ENABLED` | `false` | Ativar SSL/TLS (wss://) | `.env` |
| `SSL_CERT` | *(vazio)* | Caminho do certificado SSL | `.env` |
| `SSL_KEY` | *(vazio)* | Caminho da chave privada SSL | `.env` |
| `AUTH_ENABLED` | `false` | Ativar autenticação por API Key | `.env` |
| `ROLETA_API_KEY` | *(vazio)* | Chave de API para autenticação | `.env` (nunca no código!) |
| `PYTHONUNBUFFERED` | `1` | Logs sem buffer (Docker) | `Dockerfile` |

### Arquivo `.env` de produção (template)

```bash
# /root/roleta-cloud/.env — Produção
WS_HOST=0.0.0.0
WS_PORT=8765
SSL_ENABLED=false
AUTH_ENABLED=false
ROLETA_API_KEY=
```

---

## 9. TROUBLESHOOTING

### Container não inicia

```powershell
# Ver logs completos
ssh root@187.45.181.75 "docker logs roleta-cloud 2>&1"

# Verificar se a porta está em uso por outro processo
ssh root@187.45.181.75 "ss -tlnp | grep 8765"

# Forçar remoção e recriar
ssh root@187.45.181.75 "cd /root/roleta-cloud && docker compose down -v && docker compose up -d"
```

### Conflito de merge no servidor

```powershell
# Reset forçado para o estado do GitHub
ssh root@187.45.181.75 "cd /root/roleta-cloud && git fetch origin && git reset --hard origin/main"
```

### Banco de dados corrompido

```powershell
# Verificar integridade do SQLite (via Docker exec)
ssh root@187.45.181.75 "docker exec roleta-cloud python3 -c ""import sqlite3; conn = sqlite3.connect('/app/data/decisions.db'); print(conn.execute('PRAGMA integrity_check').fetchone())"""

# Se corrompido, restaurar backup dentro do volume Docker
ssh root@187.45.181.75 "docker exec roleta-cloud ls /app/data/decisions_backup_*.db"
ssh root@187.45.181.75 "docker exec roleta-cloud cp /app/data/decisions_backup_YYYYMMDD.db /app/data/decisions.db"
```

### Container fica em "unhealthy"

```powershell
# Verificar o que o healthcheck reporta
ssh root@187.45.181.75 "docker inspect roleta-cloud --format='{{range .State.Health.Log}}{{.Output}}{{end}}'"

# Reiniciar container
ssh root@187.45.181.75 "docker restart roleta-cloud"
```

### Espaço em disco cheio

```powershell
# Verificar espaço
ssh root@187.45.181.75 "df -h / && docker system df"

# Limpeza agressiva (remove tudo não utilizado)
ssh root@187.45.181.75 "docker system prune -af --volumes"
```

### state.json corrompido

```powershell
# Resetar estado (o sistema recria com valores padrão)
ssh root@187.45.181.75 "echo '{}' > /root/roleta-cloud/state.json && docker restart roleta-cloud"
```

### Logs excessivos

```powershell
# Docker já limita via logging config (10MB × 3 arquivos)
# Verificar tamanho dos logs do container
ssh root@187.45.181.75 "docker inspect roleta-cloud --format='{{.LogPath}}' | xargs ls -lh"
```

---

## DIAGRAMA DO FLUXO CI/CD

```
   DESENVOLVEDOR (Windows)                    GITHUB                         SERVIDOR DEBIAN
   ═══════════════════════                    ══════                         ═══════════════
                                                                            
   1. Alterar código               ┌─────────────────┐                      
      ↓                            │                 │                      
   2. pytest tests/ -v             │   Repository    │                      
      ↓ (passa?)                   │   main branch   │                      
   3. git add + commit             │                 │                      
      ↓                            └────────┬────────┘                      
   4. git push origin main ──────────────── │                               
                                            │                               
                              ┌─────────────▼──────────────┐               
                              │   GitHub Actions (CI)       │               
                              │   • checkout                │               
                              │   • pip install             │               
                              │   • pytest                  │               
                              │   • (opcional) build Docker │               
                              └─────────────┬──────────────┘               
                                            │                               
   5. ssh root@server ─────────────────────────────────────► 6. git pull    
                                                                ↓           
                                                             7. docker compose build
                                                                ↓           
                                                             8. docker compose down
                                                                ↓           
                                                             9. docker compose up -d
                                                                ↓           
                                                            10. healthcheck  
                                                                ↓           
   11. Verificar ◄──────────────────────────────────────── container UP ✅  
       logs/status                                                          
```

---

## CHECKLIST DE DEPLOY

```
PRÉ-DEPLOY:
  [ ] Testes passando localmente (pytest)
  [ ] Sem secrets hardcoded no diff
  [ ] VERSION atualizado (se release)
  [ ] Commit message descritiva

DEPLOY:
  [ ] git push origin main
  [ ] Backup do banco no servidor
  [ ] git pull no servidor
  [ ] docker compose build
  [ ] docker compose down && up -d

PÓS-DEPLOY:
  [ ] Container status: healthy
  [ ] Porta 8765 restrita a 127.0.0.1 (NÃO 0.0.0.0)
  [ ] WSS respondendo via nginx (wss://roleta.xma-ia.com/ws)
  [ ] Logs sem erros
  [ ] Versão correta em produção
  [ ] Teste funcional (conexão WS via localhost)
```

---

> **Documento gerado em:** 19/03/2026  
> **Referência:** `Manutenabilidade_iso.md` (Análise ISO/IEC 25010)  
> **Servidor:** `root@187.45.181.75` (Debian)  
> **Repositório:** `github.com/ivandirfilho/roleta-cloud`
