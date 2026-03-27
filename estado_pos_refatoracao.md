# 📊 Estado Pós-Refatoração do Banco de Dados

> **Data:** 27/Mar/2026  
> **Commit:** `1c044c0` — refactor: database audit + session lifecycle fix + schema migration  
> **Deploy:** ✅ Produção (187.45.181.75) — container healthy  
> **Testes:** 56/56 passing

---

## O QUE FOI FEITO

### Bugs Corrigidos (14 de 16)

| Bug | Descrição | Status | Como |
|-----|-----------|:------:|------|
| **DB-01** 🔴 | Banco host stale causava confusão | ✅ Corrigido | Removido do servidor |
| **DB-02** 🟡 | Backup duplicado host + volume | ✅ Corrigido | Removido do host |
| **DB-03** 🟡 | `data/decisions.db` vazio no Git | ✅ Corrigido | `.gitkeep` + confirmado `.gitignore` |
| **DB-04** 🟡 | `microservico_previsoes.db` órfão | ✅ Corrigido | Removido |
| **DB-05** 🟢 | Archive com DBs vazios | ✅ Corrigido | Removidos 2 DBs de 0 bytes |
| **DB-06** 🟢 | `deployci_cd.md` paths errados | ✅ Corrigido | Atualizado para `docker exec` |
| **DB-07** 🟢 | `test_db_query.py` referência errada | ✅ Corrigido | Reescrito para schema atual |
| **DB-08** 🟡 | `total_stops` sem sentido no Smart Gale v4 | ✅ Documentado | Marcado DEPRECATED no schema |
| **DB-09** 🔴 | Sessions NUNCA atualizadas (0/0/0) | ✅ Corrigido | `update_session_stats()` + `end_session()` + migração retroativa de 48 sessões |
| **DB-13** 🟢 | Computed properties redundantes em `to_dict()` | ✅ Corrigido | Removidos `current_bet`, `multiplier`, `gale_display` |
| **DB-14** 🟢 | Falta validação de versão no state.json | ✅ Corrigido | `try/except` no version parsing |
| **DB-16** 🟡 | `calibration_offset` com 1298 valores antigos | ✅ Documentado | Marcado DEPRECATED no schema |

### Novas Funcionalidades

| Feature | Descrição |
|---------|-----------|
| `update_session_stats()` | Recalcula stats da sessão a cada 10 decisões |
| `end_session()` | Finaliza sessão com `end_time` + stats no shutdown e reset |
| `total_resets` column | Nova coluna em sessions para Smart Gale v4 |
| Auto-migration | `total_resets` adicionado automaticamente em DBs existentes |
| Documentação DB | Seção completa de banco de dados na `Manutenabilidade_iso.md` |

### Resultados da Migração Retroativa

```
48 sessões atualizadas de 0/0/0 para stats reais.

Exemplos (sessões de hoje):
  session_1774643222435: 36 spins, 30 bets, 18 hits (60.0%)
  session_1774641226090: 44 spins, 38 bets, 25 hits (65.8%)
  session_1774640086794: 26 spins, 20 bets, 13 hits (65.0%)
```

---

## BUGS PENDENTES PARA PRÓXIMA FASE

### 🟡 BUG-DB-10: "PULAR" ainda acontece apesar do Smart Gale "sempre apostar"

**Situação:** Quando o SDA retorna `should_bet=False` (< 5 forças válidas na timeline), o engine.py ainda emite "PULAR". Hoje foram 30 decisões "PULAR" em 169 totais (17.8%).

**Causa:** `engine.py` linhas 98-114 — o `if result.should_bet` ainda governa a decisão final.

**O que seria necessário:** Modificar `engine.py` para que, quando `should_bet=False`:
- Ainda aposte com G1 (R$21) como aposta mínima de segurança
- Use o último centro válido ou um centro default
- Marque a decisão como "baixa confiança"

**Risco da mudança:** Médio — pode impactar taxa de acerto global se apostarmos em momentos com dados insuficientes.

**Decisão necessária:** O comportamento de "sempre apostar" é realmente desejado mesmo com < 5 forças? Ou manter "PULAR" como proteção é preferível?

---

### 🟡 BUG-DB-11: SDA-19 fallback com centro `[0]`

**Situação:** 30/169 decisões de hoje usaram SDA-19 (1 centro) com `sda_centers=[0]`. O número 0 (zero da roleta) pode ser o valor default quando nenhum centro válido é calculado.

**O que verificar:** Se `result.center` retorna 0 como default legítimo ou como fallback de erro.

**Ação sugerida:** Adicionar log detalhado quando SDA-19 fallback é ativado, incluindo o motivo (< 5 forças) e o centro calculado.

---

### 🟡 BUG-DB-12: Smart Gale v4 raramente escala para G2/G3

**Situação:** Dos 169 decisions de hoje, 158 foram G1, 10 G2, 1 G3. A Rule 3 (miss → reset a G1) impede escalação prática porque a taxa de acerto (~60%) não sustenta streaks longos.

**Análise:** Com 60% de acerto:
- P(2 hits seguidos) = 0.6² = 36% → escalar para G2
- P(3 hits seguidos) = 0.6³ = 21.6% → escalar para G3
- A maioria das apostas fica em G1 (R$21) — conservador

**Opções futuras:**
1. Manter como está (conservador, baixo risco)
2. Relaxar Rule 3: permitir 1 miss sem reset (ex: 2 hits em 3 jogadas mantém nível)
3. Usar score do SDA como gatilho de escalação (score ≥ 5 → permitir G2)

---

### 🟡 BUG-DB-15: Non-atomic state.json write no Docker

**Situação:** O `os.replace()` falha em bind mounts Docker (EXDEV). O fallback faz read→write não-atômico.

**Risco real:** Baixo — só causa problema se container crashar durante a janela de ~1ms do write. O `GameState.load()` já trata erros e retorna estado fresh.

**Solução futura:** Mover `state.json` para o Named Volume (junto com decisions.db) ou usar `shutil.copy2()` como fallback mais robusto.

---

### 🟢 Melhorias Futuras (Baixa Prioridade)

| ID | Melhoria | Complexidade | Quando |
|:--:|----------|:------------:|--------|
| M-01 | Criar tabela `gale_events` (substituir `gale_windows`) | Média | Próxima versão |
| M-02 | Remover colunas `calibration_*` do schema | Baixa | Quando não houver mais necessidade de dados históricos |
| M-03 | Limitar `chrome.storage.local.results[]` a 100 itens | Baixa | Próxima atualização da extensão |
| M-04 | Criar `scripts/backup_db.sh` automatizado | Baixa | Quando automatizar deploys |
| M-05 | Migrar `gale_window_hits/count` para nomes semânticos | Baixa | Próxima migração de schema |

---

## ESTADO ATUAL DO ECOSSISTEMA DE DADOS

```
PRODUÇÃO (Docker Volume roleta-data):
  ├── decisions.db  — 2555+ decisions, 48 sessions (ALL com stats reais)
  └── backup files  — apenas dentro do volume

ESTADO (Bind Mount):
  └── state.json    — Smart Gale v4 + timelines CW/CCW

CHROME EXTENSION:
  ├── chrome.storage.local  — escutaState, currentDirection, overlayUIState
  └── chrome.storage.session — wsReconnectAttempts

LEGADO (archive/):
  ├── sda_datalake.db  — 15K rows (referência histórica)
  └── microservico_datalake.db — 90 rows (referência)

REMOVIDOS: ✅
  ✗ /root/roleta-cloud/data/decisions.db (stale host)
  ✗ /root/roleta-cloud/data/decisions_backup_pre_reset.db (duplicado)
  ✗ microservico_previsoes.db (0 bytes)
  ✗ archive/legado_bancos/microservico_previsoes.db (0 bytes)
  ✗ archive/RoletaV11/microservico_datalake.db (vazio)
```

---

> Próximos passos dependem de aprovação dos bugs DB-10, DB-11 e DB-12 acima.
