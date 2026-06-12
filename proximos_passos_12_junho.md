# Próximos Passos — 12/06/2026 (noite)

> **EXECUÇÃO D0/D1 (12/06 20:25 UTC):** ✅ 0.1 walk-forward INV-3 **APROVADO** (93.2%
> treino / 90.8% teste da economia do CUT — gate ≥90% batido; EV −0.161/−0.173 por
> aposta; bônus: ccw teste **EV+ +0.571**) · ✅ 1.2 orphans (resolvido sem ação: 1 única
> janela in-flight; os 49 antigos já tinham sido saneados pelo ISO-S6 no boot) · ✅ 3.2
> DNA sem hit (falso backlog: 318 são de decisões sem resultado — legítimo) · ✅ 3.4
> alertas `RoletaSessionPnlLow`+`RoletaAllTimePnlDropFast` ativos (16 rules) + dashboard
> `roleta-profit` provisionado · ✅ 3.5 restore drill **PASS** (SQLite: integrity ok,
> 5384 decisões; wal-g: cadeia WAL íntegra, backups 30/30min) · ✅ 4.4 joblib
> (`.gitignore` + cópia em `/root/backups/artifacts/`) · ✅ **3.1 DNA→PG LIGADO**
> (hooks outbox `dna_feature`/`dna_realized` + handlers CDC + backfill: **2051 rows**
> em `shared.decision_dna`; cdc-worker rebuilt healthy; suite 386) · ✅ 4.6
> DeprecationWarnings 139→4 (restam só `websockets.legacy` — upgrade de lib).
>
> **Restam:** 1.1 bisect EV · 1.3 backfill region (opcional) · 2.x gated (B4/controlador
> por região/oracle contínuo — aguardando amostra) · 3.3 DEAL fix (agendar com operador)
> · 4.1 DecisionPipeline · 4.2 coverage ramp · 4.3 remover AGE · 4.5 AsyncAPI.
>
> Consolidação de TUDO que está pendente após o ciclo de 12/06 (3 auditorias, 8 commits
> `86eda30..50261d8`, suite 376, CI verde, prod healthy, validação E2E ao vivo 67/67).
> Origens: `proximos_passos_10_06.md` (trilhas A/B/C), `analise_regioes_12_06.md` (A1–A3),
> `Manutenabilidade_iso.md` (ADENDO 12/06 §D), auditorias r1/r2/r3 e validação E2E 18:45.
>
> **Estado de partida:** estratégia e infra operando conforme projetado — zero divergência
> entre o que o sistema gravou e o recomputado. O que segue é o que FALTA, com gates.

---

## P0 — Validação pendente (único elo do dia sem número)

| # | Item | O quê | Gate/Critério | Esforço |
|---|---|---|---|---|
| 0.1 | **Walk-forward da política INV-3 real** | Simular no histórico (jan–abr → mai–jun, por sentido): stake ×0.10 em score<4/TR-veto + stop-loss 1u vs CUT puro (não apostar) vs baseline. A política em prod é o compromisso P11×CUT — precisa do número | EV/aposta INV-3 ≥ ~90% da economia do CUT puro nos DOIS períodos; senão recalibrar `stake_fraction` | 0.5d (dados e harness prontos: `pnl_units`, `tools/backtest_harness.py`) |

## P1 — Lucro com dados atuais (offline, sem esperar tráfego)

| # | Item | O quê | Por quê | Esforço |
|---|---|---|---|---|
| 1.1 | **SP-01 bisect re-baseado em EV** | Repetir o bisect da "regressão" 47.69→43.95 usando `pnl_units` (FeatureStore/Regime opt-in) | Hit rate enganou (março: melhor hit = pior P&L); agora dá pra decidir com dinheiro | 0.5–1d |
| 1.2 | **49 janelas `orphan` em `gale_windows`** | Query + classificação das janelas sem fechamento (contabilidade vazando desde §8.3 de 10/06) | Higiene do ledger de janelas; 30–60min | 0.5h |
| 1.3 | **Backfill `result_region`/`pnl_units` no histórico** (opcional) | Aplicar a atribuição offline (A1) às ~4131 decisões antigas direto no SQLite | Habilita queries diretas por região sem re-derivar; cuidado: rodar com app pausado ou via backup→swap | 0.5d |

## P2 — Estratégia (gated — só entram com critério batido)

| # | Item | Gate | Estado da coleta |
|---|---|---|---|
| 2.1 | **B4: religar `region_bandit` com `hit_region` real** | ≥20 amostras por região POR SENTIDO pós-reset | Coleta viva desde 17:40: C1=12 · C2=3 · C3=10 (total, não por sentido) — faltam dias de sessão |
| 2.2 | **Melhoria A: controlador por região** (corrigir off2/off3 pelo viés EMA de CADA região) | (a) `region_err_ema` com `n≥30`/região/sentido mostrando viés estável ≠0; (b) simulação offline melhora EV; (c) **walk-forward A4 por sentido aprova** | Telemetria implantada (`roleta_region_err_ema` + `region_err_n`); dado acumulando |
| 2.3 | **Melhoria B: micro-shift de C1** pela EMA de `dist_c1` da janela atual (freio ±1-2 casas) | Mesmos gates da 2.1/2.2 — A2 mostrou viés global ≈0; só faz sentido POR JANELA de dealer | Dados de `dist_c1` por decisão já gravados |
| 2.4 | **Oracle contínuo / regret por jogada** (métrica viva da pergunta "foi a melhor decisão?") | Nenhum (é telemetria) — portar o `region_efficiency` do script A2 para gauge por janela | Script offline pronto (`scripts/analyze_regions_offline.py`) |

## P3 — Fluxo de dados (gaps confirmados na validação E2E)

| # | Item | O quê | Evidência | Esforço |
|---|---|---|---|---|
| 3.1 | **Espelhamento DNA→PG nunca ligado** | `shared.decision_dna` (PG) = **0 rows** — tabela criada na migração 0008, mas `dna_logger` só grava SQLite. Ligar via outbox (padrão existente de `spin_features`) + replay dos failed (lição BUG-A1) | Validação E2E 12/06 18:45 | 0.5–1d |
| 3.2 | **288 features DNA sem `hit`** (backlog histórico pré-12/06) | Backfill realize: join `decision_dna`×`decisions.result_hit/calibration_error` | `SELECT count(*) FROM decision_dna WHERE hit IS NULL` | 1h |
| 3.3 | **DEAL capture fix** (C4 — única rota plausível de EV>0) | Checklist com o operador: 1) versão da extension carregada (`chrome://extensions`); 2) logar `_detectedFrames` num spin real; 3) revisar `all_frames`/host permissions se iframe Evolution ausente. Destrava SP-28 (pooling) e offset prior por dealer | dealer='unknown' em 100% até hoje; `table_id`/`provider` vêm na URL do iframe | 2–3d (depende do operador) |
| 3.4 | **Painel Grafana P&L + alerta `RoletaSessionPnlLow`** | Gauges já existem (`roleta_session_pnl_units`, `roleta_all_time_pnl_units`, `roleta_region_err_ema`); falta painel + regra em `obs/alerts.yml` (lembrar: bind-mount stale → `docker restart roleta-prometheus`) | B5 entregue sem visualização | 1–2h |
| 3.5 | **Restore drill** | Ensaiar ponta-a-ponta: `walg-restore-drill.sh` (PG) + restore de um `decisions_*.db.gz` (SQLite). Backup sem restore testado não é backup | wal-g voltou 12/06; SQLite diário 03:15 | 2h |

## P4 — Higiene ISO (de `Manutenabilidade_iso.md` ADENDO §D)

| # | Item | Por quê | Esforço |
|---|---|---|---|
| 4.1 | **Extrair `DecisionPipeline` puro do `message_handler`** (~1000 LOC) | Maior dívida de modificabilidade; `handle_new_result` concentra decisão+gates+stake+persistência+overlay. Mitigada por testes de integração, mas refactor destrava evolução segura | 2–3d |
| 4.2 | **Coverage ramp 50→75%** (SP-34.1) | CI verde permite subir o gate gradualmente; `server/` é a área descoberta | incremental |
| 4.3 | **Remover AGE** → voltar a `pgvector/pgvector:pg15` oficial | Decisão tomada (P1.3): schemas de grafo vazios, −40% de imagem, alinha prod↔CI (baseline já é best-effort) | 0.5d + janela de manutenção |
| 4.4 | `models/spin_autoencoder.joblib` → volume + `.gitignore` | Untracked no servidor = hazard de `git clean` no deploy | 0.5h |
| 4.5 | AsyncAPI do protocolo WS (+ avaliar REST de comando) | Único gap de Compatibilidade restante (7.5/10) | 1d |
| 4.6 | DeprecationWarnings: `datetime.utcnow()` (139 avisos) + `websockets.legacy` | Baratos, zero risco; `websockets` legacy será removido upstream | 2h |

## Descartados / fora de escopo (decisões já tomadas — não reabrir sem novo dado)

- **Segurança de host** — diretriz do owner 10/06 (achados preservados em `server_snapshot/08_seguranca.md`).
- **Filtro por hora do dia** — overfit comprovado (+1.81 treino → −2.09 teste).
- **Hit rate como KPI** — só EV/aposta (breakeven depende de N).
- **B3 modulação por volatilidade do sentido** — A3 provou assimetria EPISÓDICA (fix foi B1); reavaliar apenas se o gap cw×ccw persistir nas janelas pós-B1.
- **Especializar parâmetros por sentido** — viola P8 (estratégia genérica-adaptativa).
- **Mexer na geometria 7+5+5** — P4 é premissa; A2 mostrou efficiency 84-90% (teto baixo de ganho).
- **VECTOR/autoencoder (SP-20..22), OTel (SP-32)** — adiados (sem ligação com lucro agora).

## Sequência executiva sugerida

```
D0 (hoje/amanhã):  0.1 walk-forward INV-3 · 1.2 orphans · 3.2 backfill DNA hit · 3.4 painel+alerta
D1:                1.1 bisect EV · 3.1 DNA→PG via outbox · 3.5 restore drill
D2-D3:             3.3 DEAL fix com operador (agendar) · 4.4 joblib · 4.6 deprecations
semana seguinte:   4.1 DecisionPipeline (refactor) · 4.3 remover AGE · 4.2 coverage ramp
contínuo (gates):  2.1 B4 quando n≥20/região/sentido · 2.2/2.3 quando EMA n≥30 + walk-forward aprovar · 2.4 oportunista
```

**Plano B estratégico** (inalterado): se nem o dealer-bias (3.3 → SP-28) der EV>0 validado,
pivotar o ativo — pipeline tempo-real + extensão + DNA + observabilidade + ledger — para
produto de análise/disciplina de banca para terceiros. O PROFIT-LEDGER (entregue 12/06) era
o pré-requisito desse pivô.

---

## Apêndice — o que JÁ FOI entregue em 12/06 (não refazer)

B1 reset total no botão (P10) · B2 `result_region`+`dist_c1/c2/c3` · B5 CUT v1+stop-loss
sob **INV-3 global** (P11) + PROFIT-LEDGER (`pnl_units`, `sessions.total_profit`, gauges) ·
C1 alembic prod 0006→0008 + deploy com migrations/rollback · C2 **CI verde** (1ª vez desde
27/05) · C3 backup diário SQLite + **wal-g ressuscitado** (root cause: +x perdido no git
index) · A1–A3 offline (n=4131: sem lift por região; efficiency 84/90%; assimetria
episódica) · Feedback adaptativo pela **aposta real** (BUG-B) + center=0 (BUG-A) +
stop-loss sem lag (BUG-L) · `region_err_ema`+`n` (telemetria por região/sentido) ·
fallback com números no overlay/banco (121/121 estavam vazios) · ledger com stake efetivo ·
validação E2E ao vivo 67/67 · `Manutenabilidade_iso.md` ADENDO (scorecard 8.5/10).
