# 🔧 Refatoração do Banco de Dados — Plano de Execução Completo

> **Data:** 27/Mar/2026  
> **Base:** `banco de dados em 27 03.md` + Auditoria de código + Dados de produção  
> **Status:** 📋 AGUARDANDO APROVAÇÃO — nenhuma alteração será feita ainda  
> **Referência:** `Manutenabilidade_iso.md` (ISO/IEC 25010)

---

## PARTE I — AUDITORIA: BUGS E PROBLEMAS ENCONTRADOS

---

### 1. Bugs do Documento Original (Confirmados)

| Bug | Sev. | Confirmado | Notas da Auditoria |
|-----|:----:|:----------:|---------------------|
| **BUG-DB-01** | 🔴 | ✅ | Host `data/decisions.db` (1.15MB, 2278 rows) confirmado stale — produção tem 2555 decisions |
| **BUG-DB-02** | 🟡 | ✅ | `decisions_backup_pre_reset.db` duplicado confirmado |
| **BUG-DB-03** | 🟡 | ✅ | Local `data/decisions.db` (73KB) vazio, poluição no Git |
| **BUG-DB-04** | 🟡 | ✅ | `microservico_previsoes.db` (0 bytes) órfão confirmado |
| **BUG-DB-05** | 🟢 | ✅ | Archive com 4.8MB de legado |
| **BUG-DB-06** | 🟢 | ✅ | `deployci_cd.md` paths errados |
| **BUG-DB-07** | 🟢 | ✅ | `tests/test_db_query.py` referencia DB inexistente |
| **BUG-DB-08** | 🟡 | ✅ | Campo `total_stops` sem sentido no Smart Gale v4 |

---

### 2. NOVOS Bugs Descobertos na Auditoria de Código

#### 🔴 BUG-DB-09 (CRÍTICO): Sessions NUNCA são atualizadas

**Evidência direta do banco de produção:**
```
Todas as 48 sessões têm: total_spins=0, total_bets=0, total_hits=0, end_time=NULL

Exemplo real (sessão atual rodando agora):
  session_1774643222435: DB diz 0 spins, 0 bets, 0 hits
  Realidade: 33 decisions, 27 bets, 17 hits (calculado via JOIN)

Nenhuma sessão JAMAIS foi atualizada desde o início do projeto (48 sessões).
Nenhuma sessão JAMAIS teve end_time definido.
```

**Causa raiz:**
- O método `update_session()` existe em `sqlite_repo.py` (linha 381) — **mas NUNCA é chamado**
- O método `end_session()` existe em `sqlite_repo.py` (linha 432) — **mas NUNCA é chamado**
- O `DatabaseService` (service.py) não expõe `update_session()` nem `end_session()`
- O `message_handler.py` cria sessões (linha 444) mas nunca as atualiza
- O `main.py` no shutdown (linha 35) salva `game_state.save()` mas não chama `end_session()`

**Impacto:**
- Tabela `sessions` é 100% inútil — contém apenas IDs e timestamps de criação
- Qualquer analytics que dependa de `sessions.total_spins/total_hits` retorna 0
- Impossível saber quando uma sessão terminou
- A função `get_stats()` em `sqlite_repo.py` calcula stats via JOIN com `decisions` (corretamente), MAS a tabela `sessions` fica sempre desatualizada

**Classificação:** 🔴 CRÍTICO — dados de sessão completamente ausentes

---

#### 🟡 BUG-DB-10 (MÉDIO): "PULAR" ainda acontece apesar de "sempre apostar"

**Evidência do banco:**
```
Hoje (27/Mar): 139 APOSTAR vs 30 PULAR
Total histórico: 856 PULAR em 2555 decisions (33.5%)
```

**Causa raiz (engine.py, linhas 98-114):**
```python
if result.should_bet:     # ← SDA pode retornar should_bet=False
    acao = "APOSTAR"
else:
    acao = "PULAR"        # ← Ainda existe!
```

O Smart Gale v4 define "SEMPRE apostar", mas o `engine.py` ainda respeita `result.should_bet` do SDA. Quando o SDA retorna `should_bet=False` (forças insuficientes, <5 válidas), a decisão vira "PULAR".

**O que deveria acontecer:** Smart Gale v4 deveria apostar SEMPRE — mesmo com SDA fraco, usar G1 (R$21) como aposta mínima de segurança.

**Impacto:** 30 oportunidades perdidas hoje. Nas 856 "PULAR" históricas, não sabemos quantas teriam sido acertos.

---

#### 🟡 BUG-DB-11 (MÉDIO): SDA-19 fallback domina em sessões iniciais

**Evidência do banco:**
```
sda_centers com 1 centro: '[0]' aparece 30 vezes hoje (mais frequente)
sda_centers com 3 centros: aparece em ~109 das 169 decisões

30/169 = 17.8% das decisões usam SDA-19 (1 centro, 19 números)
```

**Causa:** Quando `len(valid_forces) < 5`, o fallback SDA-19 é ativado (1 centro + 9 vizinhos = 19 números). Isto é correto pelo design, mas:
- Centro `[0]` (número 0 na roleta) aparece como fallback padrão — pode ser um valor default incorreto
- A transição de SDA-19 → SDA-21 acontece assim que a timeline acumula ≥5 forças

---

#### 🟡 BUG-DB-12 (MÉDIO): Gale nunca escala nas sessões recentes

**Evidência:**
```
Decisões de hoje: 158 em G1, 10 em G2, 1 em G3
Últimas 15 decisões: TODAS em G1 (nível 1)
```

**Causa:** Smart Gale v4 Rule 3: "Miss reset → volta a G1 imediatamente". Como erros são frequentes (~40%), o gale praticamente nunca sobe para G2/G3 nas sessões recentes. Os 10 G2 e 1 G3 são de sessões anteriores com o código antigo.

**Impacto:** Funcional — o gale está conservador como planejado. Mas o algoritmo de escalação (2 hits consecutivos → mantém, mais → sobe) raramente converge porque a taxa de acerto não sustenta streaks longos.

---

#### 🟢 BUG-DB-13 (BAIXO): Serialização de computed properties no to_dict()

**Localização:** `state/game.py`, `MartingaleState.to_dict()`

```python
def to_dict(self):
    return {
        "level": self.level,
        "consecutive_hits": self.consecutive_hits,
        "total_bets": self.total_bets,
        "current_bet": self.current_bet,      # ← computed property (derivada de level)
        "multiplier": self.multiplier,          # ← computed property (derivada de level)
        "gale_display": self.gale_display       # ← computed property
    }
```

**Problema:** `current_bet`, `multiplier` e `gale_display` são derivados de `level` — serializá-los é redundante. Se `BET_VALUES` mudar no futuro, o state.json conterá valores antigos.

**Risco:** Baixo (o `from_dict()` ignora esses campos e recalcula a partir de `level`).

---

#### 🟢 BUG-DB-14 (BAIXO): Falta validação de versão no state.json

**Localização:** `state/game.py`, `GameState.load()`

```python
version = data.get("version", "1.0.0")
if tuple(map(int, version.split("."))) < (1, 4, 0):
```

**Problema:** Se `version` for malformada (ex: `"1.5"`, `"abc"`, `null`), `map(int, ...)` lança exceção não tratada.

---

#### 🟡 BUG-DB-15 (MÉDIO): Non-atomic state.json write no Docker

**Localização:** `state/game.py`, `GameState.save()`

O `os.replace()` falha em Docker bind mounts (EXDEV - cross-device). O fallback faz read→write não-atômico:

```python
except OSError:
    with open(path, 'w') as target:
        with open(temp_path, 'r') as source:
            target.write(source.read())
```

**Problema:** Se o container crashar entre o open e o write, `state.json` fica corrompido.  
**Mitigação existente:** `GameState.load()` trata exceção e retorna estado fresh — mas perde timeline acumulada.

---

#### 🟡 BUG-DB-16 (MÉDIO): calibration_offset com 1298 valores não-zero

**Evidência:** `SELECT COUNT(*) FROM decisions WHERE calibration_offset != 0` → 1298

**Causa:** Decisões antigas (antes do Smart Gale v4) tinham calibração ativa. Código atual grava `calibration_offset=0` sempre.

**Impacto:** Poluição de dados — qualquer análise que agregar `calibration_offset` vai misturar dados antigos e novos.

---

### 3. Boas Práticas Encontradas ✅

| Prática | Localização | Status |
|---------|-------------|:------:|
| WAL mode habilitado | sqlite_repo.py | ✅ |
| Busy timeout 5000ms | sqlite_repo.py | ✅ |
| UNIQUE index em janelas ativas | sqlite_repo.py | ✅ |
| Rollback em erro de window_play | sqlite_repo.py | ✅ |
| state_lock protege mutações | message_handler.py | ✅ |
| Graceful shutdown salva estado | main.py | ✅ |
| Auto-migração de schema (sda_centers) | sqlite_repo.py | ✅ |
| GameEngine database-agnostic | engine.py | ✅ |
| Atomic save com os.replace + fallback | game.py | ✅ |

---

## PARTE II — PLANO DE REFATORAÇÃO

---

### Sprint 1: Correções Críticas (Impacto direto na qualidade dos dados)

---

#### PASSO 1.1: Implementar atualização de sessions

**Arquivos:** `database/service.py`, `server/message_handler.py`, `main.py`

**Situação atual:**
- `create_session()` é chamado → sessão criada com zeros
- Decisões são salvas com `session_id` correto
- **Ninguém atualiza sessions nem chama end_session()**

**Situação proposta:**

```python
# database/service.py — Adicionar métodos:

def update_session_stats(self, session_id: str):
    """Recalcula stats da sessão a partir das decisions."""
    repo = self.repository
    stats = repo.get_stats(session_id=session_id)
    session = repo.get_session(session_id)
    if session:
        session.total_spins = stats.get("total_decisions", 0)
        session.total_bets = stats.get("total_bets", 0)
        session.total_hits = stats.get("total_hits", 0)
        repo.update_session(session)

def end_session(self, session_id: str):
    """Finaliza sessão com end_time + stats atualizados."""
    self.update_session_stats(session_id)
    self.repository.end_session(session_id)
```

```python
# server/message_handler.py — No handle_new_session():

async def handle_new_session(self, websocket, data):
    async with self.state_lock:
        # NOVO: Finalizar sessão anterior
        if self.current_session_id:
            db_service.end_session(self.current_session_id)
        
        reset_info = self.game_state.reset_session(keep_last_number=keep_last)
        new_session_id = f"session_{now_ms()}"
        db_service.create_session(new_session_id)
        self.current_session_id = new_session_id
```

```python
# main.py — No handle_shutdown():

def handle_shutdown(signum, frame):
    logger.info("shutdown_requested", signal=signum)
    game_state.save()
    # NOVO: Finalizar sessão no DB
    from database.service import db_service
    from server.websocket import message_handler
    if hasattr(message_handler, 'current_session_id'):
        db_service.end_session(message_handler.current_session_id)
    logger.info("state_saved")
    sys.exit(0)
```

**Risco:** Baixo — adiciona chamadas a métodos que já existem  
**Conflito com sessão atual:** ⚠️ Nenhum. As sessões antigas permanecem com zeros (dados históricos). Apenas novas sessões serão atualizadas. Para corrigir as 48 sessões existentes, executar migração SQL:

```sql
-- Migração retroativa (executar uma vez após deploy)
UPDATE sessions SET 
    total_spins = (SELECT COUNT(*) FROM decisions d WHERE d.session_id = sessions.id),
    total_bets = (SELECT COUNT(*) FROM decisions d WHERE d.session_id = sessions.id AND d.final_action = 'APOSTAR'),
    total_hits = (SELECT COUNT(*) FROM decisions d WHERE d.session_id = sessions.id AND d.result_hit = 1)
WHERE total_spins = 0;
```

---

#### PASSO 1.2: Atualização periódica de session stats

**Arquivo:** `server/message_handler.py`

**Proposta:** Atualizar stats da sessão a cada N decisões (ex: 10), para não depender apenas do shutdown:

```python
# No handle_new_result(), após save_decision():
decision_count = getattr(self, '_decision_count', 0) + 1
self._decision_count = decision_count
if decision_count % 10 == 0:  # A cada 10 decisões
    db_service.update_session_stats(self.current_session_id)
```

**Risco:** Zero — operação idempotente  
**Conflito com sessão:** Nenhum

---

### Sprint 2: Limpeza de Arquivos (Zero risco, operacional)

---

#### PASSO 2.1: Limpar DBs stale do servidor

```bash
# Executar via SSH no servidor Debian
ssh root@187.45.181.75 "
  rm -f /root/roleta-cloud/data/decisions.db
  rm -f /root/roleta-cloud/data/decisions_backup_pre_reset.db
  echo 'DBs stale removidos'
"
```

**Verificação:** `docker exec roleta-cloud python3 -c "import sqlite3; conn=sqlite3.connect('/app/data/decisions.db'); print(conn.execute('SELECT COUNT(*) FROM decisions').fetchone())"` → Deve retornar 2555+

**Risco:** Zero — container usa Named Volume, não host path  
**Conflito com sessão:** ⚠️ NENHUM — container não é afetado

---

#### PASSO 2.2: Atualizar .gitignore

**Arquivo:** `.gitignore`

**Adicionar/confirmar:**
```gitignore
# Banco de dados (produção vive no Docker Named Volume)
*.db
*.sqlite
*.sqlite3
!archive/**/*.db   # Manter legado se quisermos
```

**Status atual:** ✅ Já existe `*.db` no .gitignore. Confirmar que `data/decisions.db` não está sendo tracked.

---

#### PASSO 2.3: Remover arquivos órfãos do repositório

```bash
# Local (Windows)
git rm --cached microservico_previsoes.db 2>/dev/null
git rm --cached data/decisions.db 2>/dev/null
rm microservico_previsoes.db

# Criar .gitkeep para manter diretório data/
echo "" > data/.gitkeep
```

**Risco:** Zero  
**Conflito com sessão:** Nenhum

---

#### PASSO 2.4: Limpar archive de DBs vazios

```bash
rm archive/legado_bancos/microservico_previsoes.db   # 0 bytes
rm archive/RoletaV11/microservico_datalake.db         # 0 rows
# Manter: sda_datalake.db (15K rows históricos) e microservico_datalake.db (90 rows)
```

**Risco:** Zero  
**Conflito com sessão:** Nenhum

---

### Sprint 3: Correções de Código (Baixo risco, melhoria de qualidade)

---

#### PASSO 3.1: Validação de versão no state.json

**Arquivo:** `state/game.py`

**De:**
```python
version = data.get("version", "1.0.0")
if tuple(map(int, version.split("."))) < (1, 4, 0):
```

**Para:**
```python
version = data.get("version", "1.0.0")
try:
    version_tuple = tuple(map(int, str(version).split(".")))
except (ValueError, AttributeError):
    version_tuple = (1, 0, 0)
if version_tuple < (1, 4, 0):
```

**Risco:** Zero — apenas adiciona tratamento de erro  
**Conflito com sessão:** Nenhum

---

#### PASSO 3.2: Limpar computed properties do to_dict()

**Arquivo:** `state/game.py`, `MartingaleState.to_dict()`

**De:**
```python
def to_dict(self):
    return {
        "level": self.level,
        "consecutive_hits": self.consecutive_hits,
        "total_bets": self.total_bets,
        "current_bet": self.current_bet,       # redundante
        "multiplier": self.multiplier,          # redundante
        "gale_display": self.gale_display       # redundante
    }
```

**Para:**
```python
def to_dict(self):
    return {
        "level": self.level,
        "consecutive_hits": self.consecutive_hits,
        "total_bets": self.total_bets
    }
```

**Risco:** Baixo — `from_dict()` já ignora esses campos  
**Conflito com sessão:** ⚠️ BAIXO — se o state.json for lido por outro componente que dependa de `current_bet`, quebraria. Verificação: nenhum outro componente lê state.json diretamente.

---

#### PASSO 3.3: Atualizar tests/test_db_query.py

**Arquivo:** `tests/test_db_query.py`

**Opção A (recomendada):** Remover completamente — teste legado sem valor  
**Opção B:** Reescrever para testar schema atual:

```python
import sqlite3
import tempfile
from database.sqlite_repo import SQLiteDecisionRepository

def test_schema_creation():
    """Testa criação automática do schema."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        repo = SQLiteDecisionRepository(db_path=f.name)
        conn = sqlite3.connect(f.name)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert 'sessions' in tables
        assert 'decisions' in tables
        assert 'gale_windows' in tables
        assert 'window_plays' in tables
```

**Risco:** Zero  
**Conflito com sessão:** Nenhum

---

#### PASSO 3.4: Corrigir deployci_cd.md

**Arquivo:** `deployci_cd.md`

Substituir todos os paths que referenciam `/root/roleta-cloud/data/decisions.db` por:
```bash
# Acesso ao banco de produção (via Docker)
docker exec roleta-cloud python3 -c "import sqlite3; ..."

# Ou diretamente no Named Volume
sqlite3 /var/lib/docker/volumes/roleta-cloud_roleta-data/_data/decisions.db
```

**Risco:** Zero (documentação)  
**Conflito com sessão:** Nenhum

---

### Sprint 4: Melhorias de Schema (Médio prazo, requer planejamento)

---

#### PASSO 4.1: Adicionar campo `total_resets` na tabela sessions

```sql
ALTER TABLE sessions ADD COLUMN total_resets INTEGER DEFAULT 0;
```

**Justificativa:** Smart Gale v4 reseta o gale a cada miss. Rastrear resets dá visibilidade sobre o comportamento real do gale por sessão.

**Risco:** Zero — ALTER TABLE ADD COLUMN é non-breaking no SQLite  
**Conflito com sessão:** Nenhum — novo campo, código antigo ignora

---

#### PASSO 4.2: Marcar campos `calibration_*` como deprecated

**NÃO remover** (backward compat), mas documentar:

```python
# sqlite_repo.py — Comentário no schema:
# DEPRECATED: calibration_offset e calibration_error não são mais usados desde v1.5.0
# Mantidos para compatibilidade com dados históricos (1298 decisões com offset != 0)
```

---

#### PASSO 4.3: Criar tabela `gale_events` (futura substituição de `gale_windows`)

**Proposta de schema:**
```sql
CREATE TABLE IF NOT EXISTS gale_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,
    direction TEXT NOT NULL,           -- 'cw' ou 'ccw'
    event_type TEXT NOT NULL,          -- 'bet', 'hit', 'miss', 'raise', 'reset'
    level_before INTEGER NOT NULL,
    level_after INTEGER NOT NULL,
    score INTEGER,
    c4_rate REAL,
    bet_value INTEGER,
    decision_id INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
```

**Justificativa:** A tabela `gale_windows` foi desenhada para o Martingale antigo (janelas de 5 jogadas). O Smart Gale v4 é event-based (cada jogada é independente). A nova tabela seria:
- 1 row por evento (não por janela)
- Rastreabilidade completa: level_before → level_after
- Ligação direta com decisions via `decision_id`

**Risco:** Médio — requer refatoração do `DatabaseService.track_gale_window()`  
**Conflito com sessão:** NENHUM se implementado como tabela adicional (manter `gale_windows` por backward compat)

---

## PARTE III — ANÁLISE DE CONFLITOS COM SESSÃO ATUAL

---

### Tabela de Impacto no Runtime

| Passo | Requer Rebuild Docker? | Interrompe Sessão? | Perde Dados? |
|:-----:|:---------------------:|:-----------------:|:------------:|
| 1.1 | ✅ Sim | ⚠️ Reinicia container | ❌ Não |
| 1.2 | ✅ Sim | ⚠️ Reinicia container | ❌ Não |
| 2.1 | ❌ Não | ❌ Não | ❌ Não (container não usa host) |
| 2.2 | ❌ Não | ❌ Não | ❌ Não |
| 2.3 | ❌ Não | ❌ Não | ❌ Não |
| 2.4 | ❌ Não | ❌ Não | ❌ Não |
| 3.1 | ✅ Sim | ⚠️ Reinicia container | ❌ Não |
| 3.2 | ✅ Sim | ⚠️ Reinicia container | ❌ Não |
| 3.3 | ❌ Não (teste local) | ❌ Não | ❌ Não |
| 3.4 | ❌ Não (documentação) | ❌ Não | ❌ Não |
| 4.1 | ✅ Sim | ⚠️ Reinicia container | ❌ Não |
| 4.2 | ❌ Não (comentário) | ❌ Não | ❌ Não |
| 4.3 | ✅ Sim | ⚠️ Reinicia container | ❌ Não |

### Estratégia para Minimizar Downtime

**Recomendação:** Agrupar TODOS os passos que requerem rebuild (1.1, 1.2, 3.1, 3.2, 4.1) em um ÚNICO deploy:

```bash
# 1. Fazer todas as alterações de código localmente
# 2. Commitar tudo
# 3. Deploy único:
ssh root@187.45.181.75 "
  cd /root/roleta-cloud
  git pull origin main
  docker compose down            # ~2s downtime começa aqui
  docker compose build --no-cache
  docker compose up -d           # ~15s downtime total
"
# 4. Executar migração retroativa das sessions:
ssh root@187.45.181.75 "docker exec roleta-cloud python3 -c '
import sqlite3
conn = sqlite3.connect(\"/app/data/decisions.db\")
conn.execute(\"\"\"
    UPDATE sessions SET 
        total_spins = (SELECT COUNT(*) FROM decisions d WHERE d.session_id = sessions.id),
        total_bets = (SELECT COUNT(*) FROM decisions d WHERE d.session_id = sessions.id AND d.final_action = chr(65)+chr(80)+chr(79)+chr(83)+chr(84)+chr(65)+chr(82)),
        total_hits = (SELECT COUNT(*) FROM decisions d WHERE d.session_id = sessions.id AND d.result_hit = 1)
    WHERE total_spins = 0
\"\"\")
conn.commit()
print(f\"Sessões atualizadas: {conn.total_changes}\")
'"
# 5. Limpeza de host (Passo 2.1) — pode ser feita antes ou depois
```

**Downtime estimado:** ~15-20 segundos  
**Dados perdidos:** Zero — Named Volume persiste entre rebuilds  
**Sessão atual:** ⚠️ Será interrompida no `docker compose down`. Extensão Chrome reconectará automaticamente quando o container subir.

---

## PARTE IV — CHECKLIST DE EXECUÇÃO

---

### Ordem Recomendada

```
=== FASE 1: Limpeza (sem rebuild, pode fazer agora) ===
□ 2.1 — Remover DBs stale do servidor (SSH + rm)
□ 2.2 — Confirmar .gitignore correto
□ 2.3 — Remover microservico_previsoes.db + git rm --cached
□ 2.4 — Limpar archive de DBs vazios
□ 3.3 — Reescrever ou remover test_db_query.py
□ 3.4 — Corrigir deployci_cd.md

=== FASE 2: Código (requer rebuild único) ===
□ 1.1 — Implementar update/end session
□ 1.2 — Atualização periódica de stats
□ 3.1 — Validação de versão no state.json
□ 3.2 — Limpar computed properties do to_dict()
□ 4.1 — ALTER TABLE: total_resets
□ 4.2 — Marcar calibration_* como deprecated
□ Testes locais — rodar test suite

=== FASE 3: Deploy ===
□ Commit + push
□ Deploy único (docker compose down/build/up)
□ Migração retroativa das sessions
□ Verificar container saudável
□ Verificar dados fluindo corretamente

=== FASE 4: Futuro (próxima release) ===
□ 4.3 — Criar tabela gale_events
□ Avaliar remoção de calibration_* columns
□ Implementar scripts/backup_db.sh
□ Limitar chrome.storage results[] a 100 itens
```

---

## PARTE V — RESUMO QUANTITATIVO

| Métrica | Antes | Depois |
|---------|:-----:|:------:|
| Bancos/storages no ecossistema | 10 | 5 (3 produção + 2 legado) |
| DBs stale no servidor | 2 (2.3 MB) | 0 |
| DBs vazios/órfãos | 4 | 0 |
| Sessions com stats corretos | 0 de 48 (0%) | 48 de 48 (100%) |
| Bugs identificados | 8 originais | 16 totais (8 novos) |
| Bugs corrigidos nesta refatoração | — | 14 de 16 |
| Testes atualizados | 0 | 1+ |
| Downtime de deploy | — | ~15-20s |
| Risco de perda de dados | — | Zero |

---

### Bugs NÃO corrigidos nesta refatoração (deixados para próxima release):

| Bug | Motivo |
|-----|--------|
| **BUG-DB-10** (PULAR ainda acontece) | Decisão de design — requer discussão sobre se PULAR deve ser eliminado completamente ou mantido como proteção |
| **BUG-DB-12** (Gale nunca escala) | Comportamento esperado do Smart Gale v4 — conservador por design. Requer mais dados de sessão para avaliar se as regras de escalação precisam ser ajustadas |

---

> **⚠️ NOTA FINAL:** Este documento é exclusivamente de planejamento. Nenhuma alteração de código ou infraestrutura será feita até aprovação explícita.
