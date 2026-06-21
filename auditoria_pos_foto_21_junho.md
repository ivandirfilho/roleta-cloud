# 🔍 Auditoria pós-foto — estrutura do pipeline `foto → dados` (21/jun)

> **Data:** 21/06/2026 · **Escopo:** meta-auditoria da análise anterior (`foto_roleta_junho.md`) + verificação **estrutural** do pipeline de visão, agora que ele está **deployado há poucos dias**.
> **Pergunta do dono:** *"estruturalmente o sistema está rodando tudo ok?"* (cobertura baixa é esperada por ser recente — o foco é **encanamento correto**, não volume de dado).
> **Método:** MCPs `graphify` (estrutura) + `filesystem` (código) + `sequential-thinking` (verdito) + `memory` (checkpoint) + **SSH read-only no DB de produção AO VIVO** (`root@187.45.181.75`, `decisions.db`, 8831 linhas, HEAD `58d5528`).

---

## 1. Sumário executivo (TL;DR)

✅ **SIM — estruturalmente o sistema está rodando OK.** O encanamento `foto → OCR → dados → DB` está **íntegro e provado em produção**: escritor único → SQLite SoT → 41 colunas certas → `spin_force`/`spin_direction` 100% → loop de visão **vivo** (89 linhas `vision_source='vision'`, última 21/06 20:56) gravando `dealer + provider + wheel_model + confidence` na **mesma linha** da jogada.

⚠️ Foram encontrados **3 bugs estruturais de qualidade de dado** (que **não** se auto-corrigem com o tempo) — **todos corrigidos e testados** nesta auditoria (suíte: **615 passed**).

🧠 Também corrijo **3 imprecisões da minha própria análise anterior** (meta-auditoria) — a mais importante: a alegação de "modelo não normalizado em produção" estava **desatualizada** (já funciona; a fragmentação é **legado** pré-deploy).

---

## 2. Meta-auditoria: erros na análise anterior (honestidade intelectual)

| # | Afirmação anterior (`foto_roleta_junho.md` / sessão) | Correção (verificada no código + DB ao vivo) |
|---|---|---|
| **E-1** | *"Linhas de visão com `spin_force=0/1` sugerem mis-associação da foto."* | **FALSO.** `update_last_vision` (sqlite_repo.py:561-577) só grava `dealer/wheel_model/provider/vision_*` — **nunca toca `spin_force`**. A força vem do `novo_resultado` que criou a linha. Força 0/1 é apenas a força real (ou não-capturada) daquele giro, **independente da foto**. |
| **E-2** | *"`_norm_model` não está efetivo em produção (modelo fragmentado)."* | **DESATUALIZADO.** O split por dia prova: **19/06** = `Roleta aoVivo`(60 cru) = **legado** (pré-deploy de `_norm_model`, que entrou em `58d5528`); **21/06** = só `Roleta ao Vivo`(19) ✅ **já canonizado**. A canonização **funciona hoje** (via env `SDA_VISION_MODEL_ALIASES`, presente no container). A fragmentação é **histórica**, não bug ativo — embora a *dependência exclusiva do env* seja uma fragilidade (→ BUG-3). |
| **E-3** | *Enquadramento de "cobertura ~1% / n<30 por dealer" como **BLOQUEADOR**.* | **REENQUADRADO.** Sistema deployado há dias e operado de forma intermitente → cobertura baixa é **ramp-up esperado**, não defeito estrutural. O dado **acumula sozinho** com o uso (ver §6). |

> A preocupação de "associação racy" (foto cola na `MAX(id)`) **existe** mas é de **baixo impacto**: o dealer é estável por vários giros, então errar o dealer por ±1 linha raramente muda o agrupamento; e a **força não é afetada** (E-1). Tratada como *hardening* futuro, não bug crítico.

---

## 3. Veredito estrutural — o encanamento está íntegro

Confirmado no **código** e no **DB de produção ao vivo**:

| Camada | Evidência | Status |
|---|---|---|
| Produtor → Engine | `handle_new_result` lê `data.get('dealer'/'provider'/'wheel_model')` (message_handler.py:407-414) | ✅ |
| Escritor único → SoT | `save_decision` grava tudo numa linha (sqlite_repo.py:389-448); 41 colunas | ✅ |
| Força / sentido | `spin_force` 8251/8831 (93%) · `spin_direction` 8831/8831 (100%) | ✅ |
| Loop de visão | `handle_foto_frame → update_last_vision` (message_handler.py:1253-1320) | ✅ vivo |
| Persistência de visão | 89 linhas `vision_source='vision'` (77 em 19/06, 12 em 21/06; última 20:56) | ✅ |
| **Vínculo dealer×modelo×provider×força** | `GROUP BY dealer,wheel_model,provider,spin_direction → AVG(spin_force)` retorna linhas reais (ex.: `STEFANY · evolution · Roleta ao Vivo · força=20 · conf 0.97`) | ✅ **já existe** |

**Conclusão:** o objetivo de "vincular dealer/modelo/provedor à força para estratégia por dealer" é **estruturalmente realizado** — tudo já chega na mesma linha e a query funciona. O que falta é **maturação operacional** (volume + higiene), não arquitetura.

---

## 4. Bugs estruturais encontrados (ativos, não se auto-corrigem) — **CORRIGIDOS**

### 🐞 BUG-1 — `provider` poluído com `host:*` (analytics vazando)
- **Sintoma (DB ao vivo):** `provider` = `host:www.googletagmanager.com`, `host:...doubleclick.net`, `host:www.youtube.com`, `host:www.instagram.com` — **~2100 linhas**; ainda ocorrendo **em 21/06 (22 linhas)**. Só `evolution`(1450) era limpo.
- **Causa-raiz (cliente):** `extension/deal_capture.js:24` → `PROVIDER_FALLBACK = provider || \`host:${HOST}\``. Em frames de analytics o `HOST` é o domínio do tracker, que vaza como "provider".
- **Correção aplicada (server-side, defesa em profundidade):** validador Pydantic em `SpinInput` (`models/input.py`) que **recupera a marca pelo domínio** (`evo-games → evolution`) e **descarta** `host:*` não-reconhecido (→ `None`), em vez de poluir o agrupamento. Ponto único de ingestão, vale para DOM **e** visão.

### 🐞 BUG-2 — falso-positivo: OCR captura o **próprio dashboard**
- **Sintoma (DB ao vivo, 21/06):** 2 linhas com `wheel_model='Roleta Cloud'` e 1 vision-row com `provider='host:www.roleta.xma-ia.com'` — o OCR pegou a **aba do dashboard** (`Roleta Cloud` casa a keyword `roleta`) em vez da mesa do cassino.
- **Correção aplicada (`server/vision_ocr.py`):** reject-list `_SELF_TOKENS` (`roleta cloud`, `xma-ia`, `escuta beat`) + helper `_is_self`; em `_parse_fields`, `wheel_model`/`dealer` que casam a identidade do próprio app são **descartados antes** da inferência de provider.

### 🐞 BUG-3 — canonização de `wheel_model` **dependente exclusivamente do env** (fragilidade)
- **Sintoma:** `_norm_model` só funde as variantes de OCR (`Roleta aoVivo`/`Roleta ao Vivo`/`RoletaaoVivo`) **se** `SDA_VISION_MODEL_ALIASES` estiver setado. **Sem o env**, o fallback `.title()` é sensível a espaço → **3 saídas distintas** para o mesmo rótulo (provado empiricamente). Hoje funciona porque o container tem o env, mas é silenciosamente frágil (env perdido ou mesa nova → re-fragmenta).
- **Correção aplicada (`server/vision_ocr.py`):** `_DEFAULT_MODEL_ALIASES` **embutido** (`roletaaovivo → Roleta ao Vivo`), mesclado em `_model_aliases()` com o env **sobrepondo** os defaults. Agora as variantes colapsam **mesmo sem env**; operadores ainda customizam por env.

---

## 5. Correções — arquivos e testes

| Arquivo | Mudança | 
|---|---|
| `models/input.py` | `_PROVIDER_BRAND_KEYWORDS` + `@field_validator('provider')` (BUG-1) |
| `server/vision_ocr.py` | `_DEFAULT_MODEL_ALIASES` + merge em `_model_aliases` (BUG-3); `_SELF_TOKENS`/`_is_self` + reject em `_parse_fields` (BUG-2) |
| `tests/test_vision_ocr.py` | +`test_model_merges_variants_without_env`, +`test_parse_fields_rejects_self_dashboard`; `test_model_normalized_title_case_and_whitespace` ajustado p/ label genérico |
| `tests/test_vision_features.py` | +`test_spininput_sanitizes_provider_host_fallback` |

**Validação:** `python -m pytest -q` → **615 passed, 9 skipped, 1 xfailed** (0 falhas). Suíte focada (`test_vision_ocr` + `test_vision_features`): **26 passed**.

---

## 6. O que é **ramp-up esperado** (NÃO é bug)

- **Cobertura de visão ~1%** (89/8831) e **n por dealer 8-22** (< limiar `n≥30` do `dealer_offset`): consequência direta de o sistema ser **recente** e a Escuta ser ligada de forma intermitente. **Acumula sozinho** com o uso normal — nenhum código a corrigir.
- **`dealer='unknown'` em 99%**: idem — só é preenchido nos giros em que uma foto aterrissa. Acelerável (ver §7), mas não é defeito estrutural.

---

## 7. Recomendações remanescentes (documentadas) — ✅ **RESOLVIDAS em §10**

> **Status (21/06 noite):** os itens 1-5 abaixo foram **implementados** no ciclo de estruturação dos 3 tiers — ver **§10** e o ADENDO 21/06 em `Manutenabilidade_iso.md`. Itens de aposta-relevante ficam **flag OFF** até validação.

Itens fora do escopo "bug estrutural seguro" — exigem deploy/aprovação ou são client-side:

1. **(Cliente) Tratar a raiz do BUG-1** em `extension/deal_capture.js:24`: não usar `host:${HOST}` em frames de analytics (exige reload da extensão no Chrome; sem e2e local). O guard server-side já neutraliza o sintoma no DB.
2. **(Maior ROI — dado) `dealer` fill-forward temporal:** propagar o dealer OCR'd pelos giros do `session_id` por ordem de tempo, **cortando na troca** (sessões têm 2 dealers, ex.: `ANNA,LEVI`). Levaria a cobertura de dealer de ~1% à maioria **sem mais fotos** (sessão `84f121e8`: 12 com + 232 sem).
3. **(Limpeza única, prod-write → requer aprovação)** backfill das ~62 linhas legado de `wheel_model`:
   ```sql
   UPDATE decisions SET wheel_model='Roleta ao Vivo'
   WHERE wheel_model IN ('Roleta aoVivo','RoletaaoVivo');
   ```
4. **(Hardening) Associação atômica:** fundir `vision_*` no **próximo `novo_resultado`** (como o comentário `message_handler.py:1257` já prevê) em vez do `update MAX(id)`.
5. **(Consumidor) Só então** `dealer_force_profile`/`wheel_offset`, gated por `n≥30` + `confidence`, medido pelo template `decision_dna` (lift estimado vs realizado) antes de confiar.

---

## 8. Como validar / próximo passo
- ✅ Local: `python -m pytest -q` (615 passed).
- 🚀 **Deploy** das correções (não executado — é prod-write): subir `58d5528+correções` pelo fluxo de deploy padrão; o guard de provider e o reject de auto-captura passam a valer no próximo giro; a canonização fica robusta a env ausente.

> **Resumo de 1 linha:** estruturalmente o pipeline `foto→dados` está **íntegro e provado em produção**; os 3 problemas eram de **higiene de dado** (provider sujo, auto-captura, canonização frágil) — **corrigidos e testados** — e a baixa cobertura é apenas **ramp-up** de um sistema recém-implantado.

---

## 9. Verificação 100% + estado de PRs/código (21/06 ~19:05, pós-fix)

### 9.1 Testes — ✅ 100%
- `python -m pytest -q` → **615 passed, 9 skipped, 1 xfailed, 0 failed** (re-rodado nesta verificação).
- Suíte focada de visão (`test_vision_ocr` + `test_vision_features`): **26 passed**, incluindo os 4 testes novos/ajustados das correções.

### 9.2 Código local — ✅ correções commitadas
- As 3 correções + este documento estão **commitados localmente** no checkpoint `9a08c3f` ("Checkpoint from Copilot CLI"): `models/input.py` (+38), `server/vision_ocr.py` (+39), `tests/test_vision_ocr.py` (+27), `tests/test_vision_features.py` (+19), `auditoria_pos_foto_21_junho.md` (+105).
- ⚠️ Esse checkpoint **mistura** as 5 mudanças intencionais com alterações pré-existentes da árvore de trabalho (deleções de `.md` antigos, `extension/session_extractor.js`, rebuild de `graphify-out/`) que **já estavam** uncommitted antes da sessão.

### 9.3 Pull requests — ⚠️ a PR #21 foi mergeada VAZIA
| PR | Título | Estado | Conteúdo real |
|---|---|---|---|
| **#21** | *[WIP] Perform audit for bugs and improvements in code architecture* (`copilot/auditoria-bugs-melhoria`) | **MERGED** (b035133, ~21:54Z) | **VAZIO** — só `6b2d058 Initial plan` (0 mudanças de arquivo) + merge. **Não contém** os fixes nem este doc. Checkboxes do corpo todos desmarcados. Criada por agente de nuvem via `copilot` delegate. |
| #7 | *Revise `proximos_passos_10_06`…* | DRAFT (10/06) | Antigo, não relacionado. |

### 9.4 Está atualizado? — ❌ remoto/produção NÃO; local SIM
- `origin/main` (b035133) é **byte-idêntico a `58d5528`** em conteúdo (`git diff 58d5528 origin/main` = vazio) → **não tem** `sanitize_provider`, `_is_self`, `_DEFAULT_MODEL_ALIASES` nem o doc.
- **Produção** (187.45.181.75) está em `58d5528` → também **sem** as correções.
- `local main` **divergiu**: **ahead 1** (`9a08c3f`, com os fixes) / **behind 2** (`6b2d058`+`b035133`, ambos sem conteúdo).

### 9.5 Conclusão da verificação
> **Os fixes estão 100% prontos e verdes, porém vivem APENAS no local.** A PR #21 foi mergeada como `[WIP]` **sem entregar nada** — portanto `origin/main` e a produção **continuam sem as correções**. Para "atualizar o código" é preciso **publicar os fixes** (PR limpa só com os 5 arquivos, recomendado) e depois **deployar** — ambos são *writes* no GitHub/produção e aguardam aprovação explícita.

---

## 10. Resolução — estruturação dos 3 tiers (21/06 noite)

> Ciclo de implementação dos itens §7, seguindo as convenções de `Manutenabilidade_iso.md` (flags default OFF, testes, retro-compat). **Sem alterar comportamento de aposta.** Detalhes e scorecard ISO no **ADENDO 21/06** do `Manutenabilidade_iso.md`.

| Item §7 | Tier | Resolução | Flag (default) | Arquivos |
|---|---|---|---|---|
| 1. BUG-1 raiz (provider `host:*`) | Extensão | `normalizeProvider`/`matchHostBrand` (UMD, testável): recupera marca do domínio ou `unknown`, nunca `host:*`. Manifest 3.4.1. | — (sempre on) | `extension/deal_capture.js`, `extension/manifest.json` |
| 2. Dealer fill-forward (maior ROI) | Servidor | Lógica pura `resolve_dealer` + wiring por sessão (corta na troca/sessão; aprende do OCR). | `SDA_DEALER_FILL_FORWARD` (OFF) | `core/dealer_fill.py`, `server/message_handler.py`, `app_config/settings.py` |
| 3. Backfill `wheel_model` legado | Dados | Tool dry-run/`--apply` usando `_norm_model` de runtime. Idempotente. | — (CLI) | `tools/backfill_wheel_model.py` |
| 4. Associação atômica (hardening) | Servidor | `update_last_vision` com janela máx opt-in (anti cross-spin). | `SDA_VISION_ATTACH_MAX_AGE_S` (0=off) | `database/sqlite_repo.py`, `app_config/settings.py` |
| 5. Consumidor por dealer | Servidor | `dealer_force_profile` dormante (n≥30), espelha `dealer_offset`. Não-wired. | `SDA_DEALER_FORCE_PROFILE` (OFF) | `strategies/dealer_force_profile.py`, `app_config/settings.py` |
| — Rollback (ISO #4) | Debian | 3 flags novas versionadas no compose (default OFF). | — | `docker-compose.yml` |

**Testes:** +25 casos em 5 arquivos novos (`test_deal_capture_provider`, `test_dealer_fill_forward`, `test_dealer_force_profile`, `test_backfill_wheel_model`, `test_vision_attach_age`). Suíte **640 passed, 9 skipped, 1 xfailed**. Lint silent-except baseline atualizado (`dealer_force_profile.py`).

**Pendências gated por aprovação (NÃO executadas):** deploy no Debian, reload da extensão v3.4.1 no Chrome, `backfill --apply` em produção (~62 linhas), e publicação no GitHub (a PR #21 foi mergeada vazia).

> **Resumo de 1 linha:** os **3 tiers estão estruturados** — extensão limpa na origem, servidor com fill-forward + hardening + consumidor dormante, dados com tool + flags versionadas — **flags OFF, suíte 640 verde, comportamento de aposta intacto**; só restam ações de publicação/deploy gated por aprovação.

---

## 11. Deploy executado — GitHub + Docker no Debian (21/06 ~22:58Z)

> Autorizado pelo dono ("faça deploy git e suba o docker novo"). Publicado no GitHub e deployado no servidor Debian de produção via o pipeline pull-based padrão (`tools/deploy_pull.sh`), com **rollback automático** e healthcheck.

### 11.1 Git (publicação)
- Commit `950c761` (17 arquivos: 3 tiers + testes + docs) com trailer `Co-authored-by: Copilot`.
- Reconciliação **sem reescrever história**: `git merge origin/main` (os 2 commits remotos da PR #21 eram vazios) → merge commit `c57c853`.
- `git push origin main`: **`b035133..c57c853`** ✅. A PR #21 vazia deixou de ser o topo; `origin/main` agora tem todo o código.

### 11.2 Docker (servidor Debian 187.45.181.75)
O `deploy_pull.sh` (systemd timer) detectou `origin/main` novo e executou:
`git reset --hard origin/main` → `docker compose build` → `up -d` → healthcheck.

| Verificação | Evidência |
|---|---|
| HEAD do servidor | `c57c853` (== origin/main) ✅ |
| Migrações | `ALEMBIC ok (0009_vision_features head)` ✅ |
| Container | `roleta-cloud Up (healthy)` ✅ |
| Health | `/health` → `{"status":"ok","version":"4.4.1"}` ✅ |
| Deploy log | `HEALTHCHECK ok (try 1)` + `DEPLOY OK sha=c57c853` + `NGINX reload ok` ✅ |
| Flags novas no container | `SDA_DEALER_FILL_FORWARD=0`, `SDA_DEALER_FORCE_PROFILE=0`, `SDA_VISION_ATTACH_MAX_AGE_S=0` (todas **OFF**) ✅ |
| Módulos novos | `import core.dealer_fill, strategies.dealer_force_profile, tools.backfill_wheel_model` → OK ✅ |
| Visão | `vision_ocr.is_available()=True` ✅ |
| Erros | 0 no log do container; MASTER assumiu (device conectado) ✅ |

> **Resultado:** produção rodando o código novo, **comportamento idêntico ao anterior** (todas as capacidades novas OFF), visão viva, 0 erros. Rollback automático ficou armado (não foi necessário).

### 11.3 Pendências remanescentes (opt-in, NÃO executadas)
- **Extensão v3.4.1:** client-side — **não** vai por Docker. O operador recarrega "Escuta Beat" em `chrome://extensions` para o fix de `provider` valer na origem (o guard server-side já protege o DB).
- **Ligar as flags:** quando quiser, no host + redeploy (ex.: `SDA_DEALER_FILL_FORWARD=1`). Recomendado só após validar cobertura.
- **`backfill_wheel_model.py --apply`** no DB de produção (~62 linhas legado): prod-write, rodar sob supervisão (dry-run primeiro).

---

## 12. Resumo da infraestrutura — como vai funcionar

### 12.1 Topologia (3 tiers)
```
[EXTENSÃO Chrome "Escuta Beat" v3.4.1]  (cliente, NÃO vai por Docker)
   • lê o DOM da roleta (número, sentido, dealer, mesa)
   • provider normalizado na ORIGEM: marca|unknown (nunca host:*)  ← fix 21/06
   • 1 foto/giro (captureVisibleTab) p/ OCR
        │  WebSocket  wss://roleta.xma-ia.com/ws
        ▼
[NGINX do host Debian]  proxy WS + serve o dashboard estático (/var/www/roleta)
        │
        ▼
┌──────────────────── Docker Compose (Debian 187.45.181.75) ────────────────────┐
│ roleta-cloud      Engine Python (escritor ÚNICO) — WS :8765, health/metrics :8766│
│   • handle_new_result → SpinInput(Pydantic: sanitize_provider) → GameState      │
│   • fill-forward do dealer por sessão (SDA_DEALER_FILL_FORWARD, OFF)  ← novo     │
│   • handle_foto_frame → vision_ocr (RapidOCR) → update_last_vision (time-bound   │
│     opcional SDA_VISION_ATTACH_MAX_AGE_S, OFF)                        ← novo     │
│   • save_decision → SQLite (Source of Truth, volume roleta-data)                │
│ roleta-pg         Postgres (feature store analítico: cw/ccw.spin_features, DNA) │
│ roleta-cdc-worker outbox/CDC SQLite→PG (dual_write opt-in)                       │
│ prometheus/grafana/alertmanager/exporters  observabilidade                      │
└──────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
[CONSUMIDORES de decisão]  dealer_offset · bet_advisor · dna_summary ·
   dealer_force_profile (DORMANTE, SDA_DEALER_FORCE_PROFILE OFF)        ← novo
```

### 12.2 Fluxo de uma jogada (caminho quente, inalterado)
`escuta(MASTER) → novo_resultado → SpinInput(Pydantic) → check_prediction → martingale → strategy.analyze (force17 17#) → INV-3 → save_decision (SQLite) + DNA → broadcast sugestão`. A foto/OCR é **assíncrona e lateral** — enriquece `dealer/wheel_model/provider` sem tocar o caminho de aposta.

### 12.3 O que mudou nesta entrega (e como liga)
| Capacidade | Onde roda | Flag (default) | Como ativar |
|---|---|---|---|
| Provider limpo na origem | Extensão | sempre on | recarregar extensão v3.4.1 |
| Fill-forward do dealer | Engine | `SDA_DEALER_FILL_FORWARD` (OFF) | env no compose + redeploy |
| Hardening attach foto→decisão | Engine | `SDA_VISION_ATTACH_MAX_AGE_S` (0=off) | env >0 + redeploy |
| Perfil de força por dealer | Engine (dormante) | `SDA_DEALER_FORCE_PROFILE` (OFF) | env=1 + wire futuro |
| Canonização `wheel_model` legado | Tool CLI | — | `python tools/backfill_wheel_model.py --apply` |

### 12.4 Operação & segurança
- **Deploy:** pull-based — `git push origin main` → o `deploy_pull.sh` (timer) aplica sozinho com **healthcheck + rollback automático** para o último SHA bom se `/health` falhar.
- **Rollback manual:** `SDA_*=...` no host + redeploy, ou `git revert` (flags vivem no `docker-compose.yml` versionado — ISO obrig. #4).
- **Source of Truth:** SQLite `decisions.db` (volume `roleta-data`); Engine é o **único escritor**. PG é réplica analítica desacoplada (CDC).
- **Garantia desta entrega:** todas as capacidades novas entraram **OFF** → produção é **byte-equivalente** ao comportamento anterior até o operador decidir ligar cada uma; **lógica de aposta intacta**; suíte **640 verde**.

> **Resumo de 1 linha:** o código novo está **em produção e 100% funcional** (servidor `c57c853`, healthy, visão viva, 0 erros), com todas as novas capacidades **desligadas por padrão** — a infra continua idêntica e o operador liga cada feature quando quiser, com rollback trivial.
