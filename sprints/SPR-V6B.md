# SPR-V6B · Monitor estatístico de espelho (`mirror_suspect`) — sem correção · Bloco BLK-E/dados · Pri P2

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte: `proposta_seletor_sentido_03_08.md` §10.2.3-6, §10.5, §11.3 (HOLD), §11.4-E.

## 🚫 STATUS: BLOCKED — não execute
```text
blocked_by: [SPR-V1 (merged+ativo), SPR-V2 (merged+instalado), >=30 dias corridos de dados limpos]
```
Destrava **somente** quando o Diretor registrar no `sprints/BOARD.md`:
1. V1 e V2 **em produção e ativos** (buffer-sync ligado, extensão instalada);
2. **≥30 dias corridos** de dados coletados **após** essa ativação — o relógio começa na data em que
   `SDA_PHASE_BUFFER_SYNC=1` **e** a extensão 3.10.0 estavam simultaneamente ativos, registrada pelo
   Diretor no board (não "quando o PR mergeou");
3. o período é limpo por **critério consultável, não por impressão**:
   `increase(roleta_phase_uncertain_total[1d]) ≤ 5` em todos os dias da janela **e**
   `increase(roleta_phase_alternancia_violada_total[1d]) ≤ 1` com **causa registrada** (reset/troca de
   mesa/correção manual) em cada ocorrência. O Diretor cola as duas queries e os resultados no board.
4. O Diretor fornece um **snapshot sanitizado, imutável e local** do PG (com `sha256`), porque este
   sprint **não pode** consultar o PostgreSQL produtivo.
**Motivo do HOLD** (§11.3): os dados atuais ainda podem conter espelho/contaminação. Treinar baseline
sobre dados contaminados produz um detector que **confirma o próprio erro**.

## Meta (preencher quando destravar)
```text
blocked_by: [SPR-V1, SPR-V2, janela de 30 dias limpos, snapshot sanitizado do Diretor]
locks:      [job-auditoria]
touches:    [scripts/ ou workers/ (job novo), obs/alerts.yml, docs]
base_sha:   origin/main
branch:     spr/SPR-V6B
```

## Objetivo (1 frase)
Emitir **suspeita** de âncora espelhada a partir de assinatura estatística por segmento — um alarme
que funciona **sem pixels e com a janela minimizada** — sabendo que ele **não prova** qual rótulo é
fisicamente CW ou CCW.

## Contexto mínimo (o que estatística consegue e o que não consegue)
A infraestrutura já existe: `SDA_DNA_REALIZE` calcula `realized_lift_pp` por sentido e espelha ao
PostgreSQL; há volume segregado (`spin_features`: CW 3.160 / CCW 2.928; DNA: CW 23.086 e CCW 21.215
realizadas). Uma inversão **pode** produzir assinatura mensurável. Mas **sem referência externa**, a
estatística encontra *inversão de comportamento*, não *verdade física*. Logo: a saída é
`mirror_suspect`, e **nunca** `set_seed`.

## Tarefa (quando destravar)
1. **Baseline segmentado** por **mesa, dealer, roda e regime** — sem segmentação, sazonalidade de
   dealer vira falso positivo.
2. Job de auditoria **offline**, rodando sobre o **snapshot sanitizado local** entregue pelo Diretor.
   **Este sprint não abre conexão com o PostgreSQL produtivo** e **não cria tabela nenhuma** (nem
   SQLite, nem PG): o resultado é um relatório/arquivo versionado + métricas. Persistir resultado é
   sprint futuro e exigiria o lock `schema/alembic` — que este sprint **não** possui.
3. Saída única: `mirror_suspect` (score + janela + segmento + evidência), exposta como métrica e
   alerta. **Nenhuma** chamada a `set_seed`/`_apply_seed`/`process_spin`.
   Este é o **dono canônico do nome** `mirror_suspect`; o SPR-V6A usa `anchor_review_hint` justamente
   para não criar dois algoritmos com o mesmo rótulo.
4. **Limiar é decisão humana** (§10.6-3): trade-off falso-positivo × latência. Proponha um default
   conservador, mostre a curva medida e registre a escolha no ADENDO.
5. **Sensibilidade demonstrada, não presumida**: gere um **conjunto sintético espelhado** a partir do
   próprio snapshot (inverta os rótulos de um segmento) e prove que o detector o encontra acima do
   limiar escolhido; e um **controle negativo** (segmento não invertido) que fica abaixo. Um detector
   que nunca viu um positivo não é um detector.
6. Documentar honestamente a limitação: latência típica de 30-60min e **zero prova física**.

## Critério de "pronto" (Definition of Done)
- [ ] Job roda offline sobre o snapshot local; **zero** conexão com o PG produtivo; **zero** DDL.
- [ ] Baseline segmentado por mesa/dealer/roda/regime; segmentos com amostra insuficiente são
      **abstenção declarada**, não score baixo (limiar mínimo de amostra explícito no código e no ADENDO).
- [ ] Saída exclusivamente `mirror_suspect`; teste/monkeypatch que **falha** se o job chamar qualquer
      caminho de mutação de fase.
- [ ] Curva falso-positivo × latência medida sobre a janela limpa, com o limiar escolhido justificado.
- [ ] **Controle positivo sintético detectado** e **controle negativo não detectado** (ambos em teste
      automatizado, com o dataset versionado).
- [ ] `pytest tests/` completo verde; alerta valida em `promtool check rules` (ou equivalente,
      registre qual usou); `python tools/lint_silent_except.py --update` se criou `except Exception`.
- [ ] **Não-interferência**: nada no motor muda (replay com fixture congelada, antes × depois).

## Validação (rode e cole o resultado no Log)
```
python -m pytest tests/                       # suíte COMPLETA
promtool check rules obs/alerts.yml           # ou validação YAML equivalente
python tools/lint_silent_except.py --update   # só se criou except Exception
```

## Guardrails (inviolável)
- **Nunca corrige.** Nenhuma ação automática, nenhuma escrita de fase. Correção é SPR-V7 (bloqueado).
- **INV-3** intacto; nada toca indicação, cobertura ou stake.
- **Nenhum acesso a produção**: sem SSH, sem conexão ao PG produtivo, sem host. O único dado de
  entrada é o snapshot sanitizado local entregue pelo Diretor.
- **Zero DDL** neste sprint (não possui o lock `schema/alembic`).
- Comportamento novo do lado servidor, se houver, nasce atrás de flag default-OFF na
  `docker-compose.yml` — e então `touches` e `locks` precisam ser ampliados **com aval do Diretor**.
- **Git**: só no worktree/branch `spr/SPR-V6B`; **NUNCA** main; entregue por **PR**.
- Sem `except Exception: pass`; **não commitar `graphify-out/`** nem o snapshot de dados.

## Rollback (ISO — execução é do **operador**)
Desligar o agendamento / flag default-OFF + `git revert` do PR. Nenhuma tabela quente é tocada.

## Closeout
Validação → **ADENDO ISO** (incl. limiar escolhido e a limitação "suspeita ≠ prova") → `code-review` →
Log → `graphify update` local → commit em `spr/SPR-V6B` (trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`) → push → **abrir PR** →
`store_memory` → avisar o Diretor.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
