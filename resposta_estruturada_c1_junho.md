# 🧭 Resposta Estruturada — C1 = ForceLast / força17 (Junho/2026)

> Levantamento profundo pedido pelo operador: **(Q1)** a estratégia vencedora implantada é "17 números
> SEM sobreposição"? **(Q2)** ou a base de lucro é *acertar, em momentos, números que pagam ~o dobro da
> aposta numa cobertura menor*? **(Q3)** o que está implantado está de acordo com a proposta de
> substituição do C1 feita no estudo? Fontes: `analise_400_junho.md` (citações por linha) + grafo do
> projeto (`SDA17Strategy` é o god-node) + código real (`strategies/c_selection.py`, `server/message_handler.py`).

---

## 1. Respostas curtas (TL;DR)

| # | Pergunta | Resposta |
|--:|---|---|
| **Q1** | É "17 sem sobreposição"? | **NÃO.** A proposta vencedora é a **união real ~15 COM sobreposição** — e a sobreposição é **benéfica** (reduz N → breakeven menor). Forçar disjunção/17 **PIORA** (estudo, linha 940). |
| **Q2** | Base de lucro = acerto ~dobro em cobertura menor? | **SIM, em essência.** Cobertura **menor** ⇒ **breakeven menor** (união ~15 → **42,8%**); um acerto paga **36u** sobre ~15u ≈ **2,4×** a aposta. Quanto menor a cobertura, maior o múltiplo e menor o breakeven. |
| **Q3** | O implantado bate com a proposta do C1? | **PARCIALMENTE.** A **substituição C1=ForceLast** e a **geometria 17#** estão **fiéis**. MAS o **force17-EXATO** (padding p/ 17, ligado dia 18/06) **DIVERGE** — sobe o breakeven (42,8%→47,2%), contra a recomendação explícita do estudo. E o **edge** (anti-only + após-red + confiança) é **disciplina do usuário**, não do motor. |

> **Síntese:** a base de lucro do estudo é **cobertura menor (breakeven baixo) + C1 balístico + timing** — exatamente
> a sua opção (Q2), **não** "17 disjuntos" (Q1). O force17-exato que ligamos a pedido de "sempre 17" **trabalha
> contra** esse lever (alarga a cobertura). Detalhe e correção abaixo.

---

## 2. O modelo financeiro do estudo (a matemática do lucro)

`analise_400_junho.md` §1 (L17) e §24.1 (L462-469):
- **Payout 36:1** por número; **stake = 1u por número distinto** (N números ⇒ N unidades).
- **Breakeven = N / 36** (hit-rate mínimo p/ EV≥0):

| Cobertura | Stake | Ganho líquido (green) | Breakeven | Múltiplo do acerto (36/N) |
|---|:--:|:--:|:--:|:--:|
| 21 números | 21u | +15u | 58,33% | 1,71× |
| **17 números** (nominal) | 17u | +19u | **47,22%** | 2,12× |
| **união ~15** (real, c/ overlap) | ~15u | +21u | **42,8%** | **~2,4×** |
| 14 números | 14u | +22u | 38,89% | 2,57× |

> **A base de lucro (Q2 confirmada):** o lucro vem de **acertar 1 número numa cobertura ENXUTA** — o
> pagamento (36u) é ~**2,4×** o que se arrisca (~15u), e o **breakeven cai para 42,8%**. **Cobertura menor =
> breakeven menor = mais fácil lucrar** (se o hit-rate não despencar). É o **"lever de breakeven"** do estudo
> (§30 Achado #1, L545): encolher de 21#→17# corta os 4 piores números e o ROI melhora sistematicamente.

---

## 3. A "proposta final" da estratégia vencedora (texto do estudo)

`analise_400_junho.md` §52 (L822-833) e §56 (L873):
> **🏆 ANTI-horário · 17# (C2-7 ∪ C3-5 ∪ C1=ForceLast-5) · gate após-red · flat, sem gale · horário = abster.**

1. **Sentido:** **só ANTI-horário**; **horário ABSTÉM** (−EV robusto, t=−2,99; L733/L756).
2. **C2** = cluster mais denso das últimas 4 anti → 7 números (±3).
3. **C3** = região mais fria das últimas 5 (ambos) → 5 números (±2).
4. **C1 = ForceLast** = `roda[pos(último anti) + (último − penúltimo)]` → 5 números (±2). Extrapolação
   balística (velocidade constante da força do crupiê).
5. **União ≈ 17 nominal, cobertura REAL ~15** (sobreposição em 54% das jogadas, perde ~1,65 nº — L940).
6. **Gate após-red** = **DRIVER do edge** (só aposta se a jogada anti anterior foi red). **Sem o gate, ROI ≈ 0%** (L830).
7. **Stake flat** 1u/número (~15-17u/aposta); **sem gale**.
8. **Camada de sessão:** warmup 3, janela jogada **4–40 anti**, **stop-loss 15u/sessão** (§54).

**A sobreposição é PROPOSITAL e BENÉFICA** (L940, citação literal):
> *"As regiões SE SOBREPÕEM — em 54% das jogadas há sobreposição (perde-se ~1,65 número), e a cobertura
> real média é ~15,4 (não 17). E isso é **bom**: aceitar a sobreposição **reduz N** (menor breakeven:
> 15,4/36 = 42,8% vs 17/36 = 47,2%). **Forçar regiões disjuntas (espalhar) piora** (+0,63%) — alarga a
> aposta e sobe o breakeven. **Recomendação: permitir sobreposição (apostar a união real, ~15 números)."*

E o stake (L985): *"Use 1u por número distinto na união (~15 números). A sobreposição já te beneficia ao
reduzir N (~15 = breakeven 42,8% em vez de 47,2%); não precisa dobrar nada."*

---

## 4. Validação: o que está IMPLANTADO × a PROPOSTA do estudo

| # | Componente | Proposta (estudo) | Implantado (código) | Veredito |
|--:|---|---|---|:--:|
| 1 | **C1 = ForceLast** | `roda[pos(últ)+força]`, ±2 | `force_last_center` (idêntico), raio 2 | ✅ **FIEL** |
| 2 | **C2 / C3** | denso-4 (±3) / frio-5 (±2), `sda_centers` produção | `coverage3` usa `centers[1]`(±3) e `centers[2]`(±2) | ✅ **FIEL** |
| 3 | **Geometria 17#** | C2-7 ∪ C3-5 ∪ C1-5 | mesmos raios 3/2/2 | ✅ **FIEL** |
| 4 | **Sobreposição / N real ~15** | **permitir overlap, união ~15** (benéfico) | união real (força17 puro) **OU** padding p/ 17 (force17-EXATO, default ON 18/06) | ❌ **DIVERGENTE** (com EXATO) |
| 5 | **Stake flat 1u/número, sem gale** | 1u/distinto, sem gale | block_gale cap=1 (flat-equiv.), 1u×N | ✅ **FIEL** |
| 6 | **Só ANTI (horário abster)** | **anti-only; horário ABSTER** | aposta **os 2 sentidos**; `dir_bias` marca horário=desfavorável (não suprime — INV-3) | ⚠️ **DIVERGENTE** (por design da proposta_nova: gate é do usuário) |
| 7 | **Gate após-red (driver do edge)** | **obrigatório** (sem ele ROI~0%) | **não** no motor; `last_core_result`/`ultimo_acerto` é telemetria p/ o usuário | ⚠️ **DIVERGENTE** (por design: disciplina do usuário) |
| 8 | **Gate confiança (≤3)** | salto p/ +14% (PARTE IX) | **não** implementado | ⚠️ ausente (insight futuro) |
| 9 | **Stop-loss 15u/sessão** | 15u (ótimo) | default **30u** | ⚠️ **DIVERGENTE** (config) |
| 10 | **Cap ~40 jogadas/sessão** | parar no 40 (evita colapso 41+) | **não** existe | ⚠️ ausente |

### 4.1 O veredito honesto
- **A COBERTURA (geometria C1=ForceLast/17#) está implantada fielmente** — exceto pelo **force17-EXATO**,
  que **diverge** (sobe o breakeven).
- **O EDGE do estudo NÃO está no motor.** O ganho de +2% (e +5% com sessão) **exige**: (a) apostar **só
  anti**, (b) **só após um red**, (c) **stop-loss 15u**, (d) **parar no ~40**. O motor **sugere sempre, nos 2
  sentidos, sem gate** (decisão da `implantação_c1_proposta_nova_junho.md`: INV-3 — a estratégia sempre indica;
  os gates são **disciplina do operador**, sinalizada por `dir_bias` e `ultimo_acerto`).
- **Consequência crítica:** **seguir a sugestão crua do motor (os 2 sentidos, toda jogada, sem gate) ≈ 0% de
  edge** — ou **negativo no horário** (−EV t=−2,99). O motor entrega a **cobertura**; o **lucro** depende da
  **disciplina** (anti + após-red + stop-loss 15u + janela 4–40).

---

## 5. 🔴 A divergência crítica — force17-EXATO contradiz a base de lucro

O que ligamos dia 18/06 (`SDA_FORCE17_EXACT=1`, default ON) para atender "apostar sempre 17":
- **Completa a união para EXATAMENTE 17** (padding dos números não-cobertos mais próximos).
- Efeito: **N sobe de ~15 para 17** ⇒ **breakeven sobe de 42,8% para 47,2%** (+4,4 pontos).
- **Re-adiciona os ~1,65 números** que a sobreposição removia de propósito.
- **É exatamente o que o estudo diz para NÃO fazer** ("forçar regiões disjuntas/espalhar PIORA; alarga a
  aposta e sobe o breakeven", L940). Padding p/ 17 é a mesma classe de erro: **alarga a cobertura**.

> **Conclusão:** o **force17-EXATO trabalha CONTRA a base de lucro** (cobertura menor/breakeven baixo) que
> é o lever central do estudo. Para ficar **como projetado**, o default correto é a **união ~15** (overlap
> permitido). O EXATO deve ser **opt-in** (consistência visual ao custo de +4,4 pontos de breakeven).

---

## 6. 🧬 Sprints / evolução do pensamento (a jornada — documentada)

| Etapa | Estado | Fidelidade ao estudo |
|---|---|:--:|
| Pré-17/06 | produção `c2c3` = 14# (C2+C3), **2 sentidos, sem gate** | parcial (geometria 14#, sem C1/anti/gate) |
| 18/06 manhã | **force17** (C1=ForceLast + 17# **união ~15**), PR #14 | ✅ cobertura fiel (união) |
| 18/06 tarde | auditoria front+fluxo: 4 bugs corrigidos (overlay-null, etc.) | ✅ |
| 18/06 (pergunta "por que N varia?") | diagnóstico: era a **união** (overlap) — comportamento **correto** do estudo | — |
| 18/06 (pedido "sempre 17") | **force17-EXATO** (padding p/ 17), PR #15, default ON | ❌ **divergência** (sobe breakeven) |
| 18/06 (pergunta "17 unidades?") | confirmado stake = N unidades (1u/número); EXATO fixa em 17u | — |
| **Agora** | **este levantamento** — validação + correção da divergência (§5) + auditoria (§7+) | → realinhar ao estudo |

> A evolução foi **fiel ao estudo até o force17-união**. O **force17-EXATO** (a pedido de "17 fixos")
> introduziu a **única divergência de cobertura** — corrigida nesta sprint (§ seguinte).

---

## 7. Correção da divergência + auditoria de bugs

### 7.1 Correção aplicada — realinhamento ao estudo
**force17-EXATO rebaixado a opt-in (default OFF = união ~15).**

| Arquivo | Mudança |
|---|---|
| `app_config/settings.py` | `force17_exact_enabled()` **default `0` (OFF)** + docstring explicando o porquê (estudo L940) |
| `docker-compose.yml` | `SDA_FORCE17_EXACT=${SDA_FORCE17_EXACT:-0}` (default OFF) |

- **OFF (novo default):** o motor aposta a **união real ~15** (sobreposição permitida) — **fiel ao estudo**
  (breakeven ~42,8%). É a base de lucro correta (cobertura menor).
- **ON (`SDA_FORCE17_EXACT=1`):** opt-in p/ consistência visual de 17 (custo: breakeven +4,4pts).
- **Verificação e2e:** com o default, a cobertura volta a variar (~12–17, união) — `{12:3, 13:1, 14:2,
  15:3, 17:7, 21:2}` (os 21 são o fallback de calibração; os 17 são jogadas naturalmente disjuntas).

### 7.2 Auditoria de bugs (code-review dedicado + fuzz)
**0 bugs reais.** Auditoria de alto sinal sobre `_signed_dist`, `force_last_center`, `coverage3`,
`pad_to_n`, `force_select`, o wiring (`_engine_apply_selection`/`_ensure_nonempty_coverage`/fallback) e
settings, com **fuzz**: 2.000 pares (sinal/range −18..+18 ✅), **5.000** casos de ForceLast (0 divergências
da spec ✅), **20.000** entradas de `force_select` (nunca vazio; `target_n=17`⇒17 exatos; sem duplicatas;
C2∪C3 sempre cobertos ✅). **70 testes** dedicados verdes (suíte completa **566 passed**).

| Risco auditado | Resultado |
|---|:--:|
| Sinal/off-by-one na distância circular | ✅ correto (idêntico a `sda17._signed_dist_idx`) |
| Ordem `r[-2]`/`r[-1]` no ForceLast | ✅ correto |
| Mapeamento C2=`centers[1]` / C3=`centers[2]` | ✅ correto |
| `pad_to_n` loop infinito / não atingir n | ✅ finito, atinge n, aditivo, determinístico |
| Aposta (`result.numbers`) × resolução (`hit`) | ✅ batem (`hit = bola ∈ numbers` apostados) |
| Isolamento causal (look-ahead) | ✅ lê history do `target` (oposto ao spin) |
| INV-3 (nunca suprime indicação) | ✅ preservado (try/except + rede B1) |
| Persistência `cw/ccw_history` | ✅ validada |

**Nuance (por design, não-bug):** o `slot` da telemetria (`_attribute_hit_region`) mede a região pelos
**centros geométricos do SDA17** (não pelo ForceLast) — afeta só analytics, **não** a aposta/resolução/PnL
(o veredito green/red usa o `hit` real na cobertura apostada).

### 7.3 Veredito final — "como projetado" × divergente (pós-correção)

| Componente | Estado pós-correção |
|---|:--:|
| C1=ForceLast, geometria 17#, base sda_centers, flat/sem-gale | ✅ **como projetado** |
| **Cobertura união ~15 (overlap)** | ✅ **como projetado** (default OFF) — corrigido |
| Anti-only / horário abster | ⚠️ **disciplina do usuário** (motor sugere ambos; `dir_bias` marca) |
| Gate após-red / confiança | ⚠️ **disciplina do usuário** (motor não gateia; INV-3) — **é o DRIVER do edge** |
| Stop-loss 15u, cap 40 jogadas | ⚠️ **recomendações de operação** (config; 15u não setado, cap inexistente) |

> **A base de lucro está correta de novo** (cobertura enxuta/breakeven baixo). Mas reforçando o ponto
> mais importante: **o motor entrega a COBERTURA, não o EDGE.** O lucro do estudo (+2% base, +5% com
> sessão) **exige a disciplina do operador**: (a) apostar **só anti-horário** (`dir_bias=favoravel`);
> (b) **só após um red** (`ultimo_acerto.green=false` no sentido); (c) **stop-loss 15u/sessão**; (d)
> **parar por volta da jogada 40**. Seguir a sugestão crua nos 2 sentidos, toda jogada, **≈ 0% de edge**
> (e −EV no horário). Isso é **intencional** (`implantação_c1_proposta_nova_junho.md`: INV-3 — a estratégia
> sempre indica; os gates são do usuário), mas precisa estar **explícito** para a operação ser lucrativa.

### 7.4 Recomendações (1 env cada, sem código novo)
1. **`PROFIT_STOP_LOSS_UNITS=15`** — o estudo mostra +5,5% (15u) vs +1,4% (30u atual). Ganho grande, risco menor.
2. **Operar a janela jogada ~4–40 anti** e **abster no horário** — disciplina (o motor já sinaliza `dir_bias`).
3. (Futuro) **gate de confiança** (ForceLast≈ForceMean ≤3) — o salto p/ +14% do estudo (PARTE IX), hoje ausente.

---

*Documento gerado em 18/06/2026 (levantamento C1). Fontes: `analise_400_junho.md` (PARTES V–XV), grafo do
projeto (`SDA17Strategy`), código real. Correção: `SDA_FORCE17_EXACT` default OFF (união ~15, fiel ao
estudo). Auditoria: 0 bugs reais (fuzz + 566 testes). Cross-ref: `implantação_efetuada_17_junho.md` §12.*
