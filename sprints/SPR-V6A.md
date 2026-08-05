# SPR-V6A · Consistência operacional: alertas, confirmação de seed e badge — sem ação automática · Bloco BLK-D/obs · Pri P1

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte: `proposta_seletor_sentido_03_08.md` §10.2.3-5, §10.5, §11.3 (V6A = maior ganho por custo), §11.4-E.

## Meta
```text
blocked_by: [SPR-V1, SPR-V2, SPR-V4]
locks:      [popup, extensão-JS, alerts, health_server, message_handler-fase, phase_metrics,
             settings, compose]
touches:    [extension/popup.js, extension/popup.html, extension/background.js, extension/manifest.json,
             obs/alerts.yml, server/health_server.py, server/message_handler.py,
             state/phase_metrics.py, app_config/settings.py, docker-compose.yml, tests/]
base_sha:   origin/main             # rebasear após o merge de V1, V2 e V4
branch:     spr/SPR-V6A
```
**Por que os locks são amplos:** este sprint precisa **ingerir** o `client_health` que o SPR-V2 emite
no keepalive e transformá-lo em counter/gauge — isso toca `message_handler`, `phase_metrics`,
`health_server` e o set exato de `tests/test_dir12_metrics_exporter.py`. Como ele só começa **depois**
de V1, V2 e V4 **mergeados**, não há paralelismo a proteger: nenhum outro sprint da família estará em
voo nesses arquivos. Se o Diretor colocar SPR-X1/X2/X3/X4 (lock `extensão-JS`) em voo, **serialize**.

## Setup (worktree próprio)
```text
git -C "C:\Users\Windows\Desktop\Roleta Cloud" worktree add ..\rc-SPR-V6A spr/SPR-V6A
cd ..\rc-SPR-V6A
git rev-parse --show-toplevel   # confirme que você NÃO está no worktree do Diretor
```

## Objetivo (1 frase)
Fazer com que uma inversão de sentido, uma ingestão parada ou uma âncora suspeita **apareçam em
minutos para o operador**, em vez de virarem auditoria manual em D+7 — **sem** que o sistema tome
qualquer decisão sozinho.

## Contexto mínimo
V1 e V2 fecham as causas; V4 cria a trilha. Ainda assim, o operador não tem **nenhum** sinal
operacional: o popup mostra elements/numbers/error, e `obs/alerts.yml` só ganhou as regras do V1.
Este sprint é o de **maior ganho por custo** segundo a auditoria (§11.3) e **não depende de pixels**.

## Escopo em dois blocos (entregue os dois no mesmo PR, commits separados)
- **V6A-base** (depende de V1+V2): gap por tamanho, ingestão parada, descarte não alinhado,
  confirmação dupla de seed, badge de `direction_source`.
- **V6A-events** (depende de V4): `stale`/`missing`/`selfcontradict` do `direction_event` e a
  heurística de espelho.

## Âncoras
- `server/health_server.py:120-218` — `_PROM_METRICS` e refresh (é onde as gauges de V1/V4 vivem).
- `obs/alerts.yml:1-170` — grupos existentes; o grupo de fase foi criado no SPR-V1.
- `state/phase_metrics.py:10-14` — dict fechado de counters (V1 e V4 já adicionaram os deles).
- `state/game.py:1114-1115` — bloco `sentido` do state_sync expõe `locked` e `source`
  (`direction_source`) — é o que o badge do popup consome.
- `extension/popup.js` / `popup.html` — o SPR-V2 já expôs `skippedUnaligned`/`rebaselines`/
  `unalignedStreak`/versão; aqui entram seed e badge.
- `extension/background.js:1241-1255` — `setDirection` (o caminho do toggle/`set_seed` do operador).
- `server/message_handler.py:1696-1715` — `handle_set_seed` (após o SPR-V1, passa por `_apply_seed`).

## Tarefa

### Bloco 1 — alertas que distinguem causa de ruído (V6A-base)
0. **Ingestão do `client_health` (pré-requisito dos itens 1-3).** O SPR-V2 já emite, no keepalive
   existente, o bloco aditivo
   `client_health: {ext_version, unaligned_streak, skipped_unaligned, rebaselines, last_reason, frame_id, ts_ms}`.
   Aqui você o **consome**: parse tolerante (chave ausente ⇒ ignora, nunca levanta), atrás da flag
   `SDA_CLIENT_HEALTH_INGEST` (default **OFF**, leitura por chamada), alimentando counters novos no
   dict **fechado** `state/phase_metrics.py:10-14` + gauges em `server/health_server.py` +
   **atualização do set exato** em `tests/test_dir12_metrics_exporter.py` (senão a suíte fica vermelha).
   Falha de parse **nunca** afeta o keepalive nem a aposta.
1. **Gap por tamanho**: expor a distribuição de `k` recuperado (buckets em gauge; `k∈{1,2,3-5,6-9,>9}`
   — o topo casa com o `min_overlap=3` do SPR-V1, acima do qual `phase_uncertain` é o resultado
   correto). Exige um counter novo por bucket, alimentado no ponto de recuperação de gap do
   `message_handler` (por isso o lock `message_handler-fase`). Alerta por `increase()` em gaps grandes.
2. **Ingestão parada**: alerta quando não chega `novo_resultado` por N minutos **com sessão ativa**,
   usando também o `client_health` do item 0 (durante uma sequência unaligned **nenhum** giro é
   enviado — este é exatamente o caso perigoso). Defina `N` explicitamente (sugestão: 6min ≈ 8 ciclos
   de ~44s) e justifique no ADENDO.
3. **Descarte não alinhado**: alerta por `increase()` de `skipped_unaligned`/`spin_implausivel_total`
   acima do limiar.
4. **Segmentação obrigatória**: reset de sessão, troca de mesa e correção manual do operador geram
   violações de alternância **legítimas**. Os alertas de fase são por **janela** e a auditoria fina é
   **particionada por sessão** — nenhum alerta pode contar troca de mesa como corrupção física.
5. Regras sempre com `increase()`/`rate()` (counters em memória zeram a cada restart do container).
6. Cada alerta novo carrega, na anotação, **o que o operador deve fazer** (runbook de uma linha).

### Bloco 2 — o operador vê e confirma a âncora (V6A-base)
1. **Badge de `direction_source`** no popup: `operator_seed` / `manual_fix` / `auto_seed` / `reset` —
   e o estado de `locked`. O operador precisa saber **de onde veio** a fase vigente.
2. **Confirmação dupla do seed**: definir/alterar a âncora exige confirmação explícita no popup e
   mostra o **estado resultante confirmado pelo servidor** (não o otimista local). Se o servidor não
   confirmar, o popup mostra divergência — nunca "sucesso" presumido.
3. **Aviso de flatline**: **N = 6 giros consecutivos sem flip** do seletor (≈4,4min; com alternância
   1:1 a probabilidade de 6 repetições legítimas é desprezível) = sinal de que a alternância parou de
   ser aplicada. Só aviso visual, parametrizável, default 6 — registre a escolha no ADENDO.

### Bloco 3 — sinais da trilha (V6A-events, depende de V4)
1. Alertas para `vision_stale_total`, `vision_missing_total`, `vision_selfcontradict_total`.
2. **Sinal preliminar `anchor_review_hint`** (⚠️ **não** chame de `mirror_suspect`): apresentar como
   **dica de revisão**, com o texto deixando claro que **não há sensor externo** e que estatística
   sozinha não prova qual rótulo é fisicamente CW/CCW. Nunca apresentar como diagnóstico físico.
   **Nenhuma ação automática.**
   *Por que o nome muda:* `mirror_suspect` é o **artefato do SPR-V6B** (monitor estatístico segmentado
   por mesa/dealer/roda/regime, com baseline e curva de falso-positivo). Usar o mesmo nome aqui criaria
   dois algoritmos e dois limiares com o mesmo rótulo, divergindo em produção. Quando o V6B existir,
   este painel passa a **exibir o `mirror_suspect` produzido por ele** e o `anchor_review_hint` é
   aposentado.
3. O limiar do `anchor_review_hint` é **decisão humana** (§10.6-3): exponha-o como parâmetro
   configurável com default conservador e registre a escolha no ADENDO.

## Critério de "pronto" (Definition of Done)
- [ ] Alertas novos passam em `promtool check rules obs/alerts.yml` (ou validação YAML equivalente,
      registre qual usou) e usam `increase()`/`rate()`.
- [ ] `client_health` é ingerido atrás de `SDA_CLIENT_HEALTH_INGEST` (default OFF); payload malformado
      ou ausente **não** derruba o keepalive (teste); counters/gauges novos existem e
      `tests/test_dir12_metrics_exporter.py` está atualizado e verde.
- [ ] Cada alerta tem runbook de uma linha e é **segmentado por sessão** onde aplicável.
- [ ] Popup mostra badge de `direction_source` + `locked` + confirmação **do servidor** ao definir seed.
- [ ] Aviso de flatline aparece após **6** giros sem flip (parâmetro documentado).
- [ ] Sinais de `stale`/`missing`/`selfcontradict` visíveis (métrica + popup/alerta).
- [ ] `anchor_review_hint` é **somente informativo**; teste/monkeypatch que **falha** se este sprint
      chamar `_apply_seed`, `set_seed`, `process_spin` ou alterar `direcao`/`seed_parity`/`spin_seq`.
- [ ] **Não-interferência**: replay determinístico com **fixture congelada** e asserção campo a campo
      (decisões, cobertura, stake, timelines, seed, `spin_seq`), antes × depois, flags novas OFF.
- [ ] `pytest tests/` completo verde; `node --test` verde (se tocou lógica pura da extensão).
- [ ] Mexeu em `extension/` → bump de `manifest.version` (minor a partir da versão vigente) + nota de
      reload no Chrome + **comando reproduzível + `sha256`** que reconstrói o pacote da versão anterior
      (o agente não anexa binário a PR).

## Guardrails (inviolável)
- **NENHUMA ação automática.** Este sprint só observa, exibe e alerta. Ele **não** corrige âncora,
  não chama `set_seed`, não muda direção. Correção automática é o SPR-V7 (bloqueado).
- **INV-3** intacto; nada toca indicação, cobertura ou stake.
- **Todo comportamento novo do lado servidor nasce atrás de flag default-OFF na `docker-compose.yml`**,
  leitura por chamada — inclusive a ingestão de `client_health` e a confirmação de seed (que **altera
  fluxo**). Não existe "só quando alterar fluxo": se está no diff do servidor, nasce OFF.
- **Falha de telemetria/alerta nunca altera aceitação de giro nem a aposta.**
- **Git**: só no worktree/branch `spr/SPR-V6A`; **NUNCA** main; entregue por **PR**; sem SSH/host/prod.
- **Não commitar `graphify-out/`**; sem `except Exception: pass`.

## Validação
```
python -m pytest tests/                  # suíte completa
promtool check rules obs/alerts.yml      # ou validação YAML equivalente
node --test tests/js/                    # se aplicável
```
+ roteiro manual do popup (badge, confirmação de seed, flatline) com resultado esperado por passo.

## Rollback (ISO)
Alertas: `git revert` do PR (regras não alteram o app). Popup: kill-switch/flag do SPR-V2 + reload,
ou zip da versão anterior. Nenhuma migração, nenhum estado novo persistido no motor.

## Conformidade ISO
- [ ] Flags default-OFF onde houver mudança de fluxo; leitura por-chamada.
- [ ] **INV-3** intacto; suíte completa verde.
- [ ] `extension/` → bump de versão + nota de reload + zip anterior.
- [ ] ADENDO ISO registra o limiar de `anchor_review_hint` escolhido (decisão humana §10.6-3), o `N`
      do flatline, o `N` de ingestão parada, e a distinção explícita entre **suspeita estatística** e
      **prova física** — além do motivo de o nome `mirror_suspect` ficar reservado ao SPR-V6B.

## Closeout
1. Validação → `## Log`. 2. **ADENDO ISO**. 3. `code-review`. 4. Append no Log.
5. `graphify update .` local (não commitar). 6. Commit em `spr/SPR-V6A` (trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`).
7. `git push -u origin spr/SPR-V6A` + **abrir PR**. 8. `store_memory` + avisar o Diretor.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
