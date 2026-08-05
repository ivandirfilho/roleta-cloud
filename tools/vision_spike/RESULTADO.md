# SPR-V3 · RESULTADO — preflight técnico do vídeo/iframe

> **Este é o arquivo que o Diretor cita para destravar (ou não) o SPR-V5.**
> Versionado de propósito: número de gate sem denominador, sem data e sem `algorithm_sha`
> não é evidência.

| | |
|---|---|
| **Status** | 🟡 **`WAITING_HUMAN_EVIDENCE`** — V3-A entregue; falta a coleta de campo (V3-B) |
| **Veredito GO/NO-GO** | ⬜ **VAZIO — não declarado.** GO/NO-GO é decisão de investimento do operador (§10.6-1) |
| **V3-A (ferramental, protocolo, replay)** | ✅ entregue neste PR |
| **V3-B (40-60 giros anotados + soak 2 h)** | ⬜ **não executado** — exige mesa ao vivo e operador |
| `algorithm_sha` da entrega | `fc91867da0601918` (`lib/unwrap.js` + `lib/ellipse.js` + `lib/direction_core.js` + `lib/pipeline.js`) |

---

## 0. Como ler este arquivo

Três classes de evidência, e **só uma vale gate**:

| classe | origem | preenchido? | elegível a gate |
|---|---|---|---|
| `synthetic` | `lib/synthetic.js` (cena gerada) | ✅ sim (§3) | ❌ **não** |
| `fixture` | `<video>` local da bancada | ✅ parcial (§4) | ❌ **não** |
| `field` | mesa Evolution ao vivo, com operador | ⬜ **VAZIO** (§1, §2, §5) | ✅ sim |

Acertar na cena que o próprio código gerou não prova nada sobre a mesa. Está escrito no
topo de `lib/synthetic.js` e é repetido aqui porque é a diferença entre um spike e uma
profecia auto-realizável.

---

## 1. E0 — acesso, entrega e taint  ⬜ VAZIO (V3-B)

Probe entregue e rodável (`probe/probe_e0.js`, `all_frames: true`). **A execução em mesa
real é V3-B.** Roteiro: `PROTOCOLO_CAMPO.md` §Etapa 1.

| Pergunta | Resposta | Evidência bruta |
|---|---|---|
| Existe `<video>` no iframe da mesa? | ⬜ | |
| Resolução intrínseca (`videoWidth`×`videoHeight`) | ⬜ | |
| Entrega: `mediastream` / `blob_url` / `url_https` / `none` | ⬜ | |
| MSE confirmado? | ⬜ | *(`null` = "não sei" é resposta válida — do mundo isolado do content script não dá para inspecionar o `MediaSource`; `blob:` **não prova** MSE)* |
| `requestVideoFrameCallback` suportado? | ⬜ | |
| `createImageBitmap`+`OffscreenCanvas`+`getImageData` sem `SecurityError`? | ⬜ | |
| **Taint (canvas manchado)?** | ⬜ | |
| Veredito da probe | ⬜ | |

> Se `taint = true`, o caminho de vídeo **morre aqui** e o resultado do sprint é
> **NO-GO por indisponibilidade de pixels** — resultado válido, e o mais barato possível.

## 2. E0b — cobertura (aba visível, oculta e janela minimizada)  ⬜ VAZIO (V3-B)

Instrumento entregue (`probe/probe_e0b.js` + `lib/rvfc_meter.js`) e **testado contra
`<video>` local** (§4). **A medição em mesa real é V3-B.** Roteiro: `PROTOCOLO_CAMPO.md` §Etapa 2.

| Fase (3 min cada) | callbacks/s | `mediaTime` avançou (s) | gaps | maior gap (ms) | `presentedFrames` perdidos |
|---|---|---|---|---|---|
| A · aba visível e em foco | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| B · aba oculta (outra aba ativa) | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| C · **janela minimizada** | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| D · volta a visível | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

Observação livre do operador na fase C: ⬜

> **Não presuma.** `captureVisibleTab` é cego com a janela minimizada; o `<video>` pode não
> ser. O aceite formal desta cobertura é **decisão humana** (§10.6-2).

## 3. E1 — replay offline · cenários SINTÉTICOS  ✅ preenchido · ❌ `eligible_for_go_gates: false`

`node tools/vision_spike/replay.js --synthetic <dir> --case <caso>` · janela 6 frames ·
stride 3 · `algorithm_sha fc91867da0601918`. Referência de cena = primeiro frame
(modo de teste, denunciado pelo próprio replay).

| Caso | O que simula | Emitidos / janelas | Errados | Guards dominantes | Comportamento esperado |
|---|---|---|---|---|---|
| `clean` cw (300 frames) | cena limpa | 295 / 295 | 0 | — | mede +126°/s e emite `cw` |
| `clean` ccw | idem, sentido oposto | 9 / 9 | 0 | — | emite `ccw` |
| `noise` | ruído de compressão ±12 | 9 / 9 | 0 | — | robusto |
| `blur` | desfoque box r=1 | 9 / 9 | 0 | — | robusto |
| `overlay` | banner **estático** sobre a ROI | 9 / 9 | 0 | — | high-pass temporal mata o overlay |
| `mirror` | feed espelhado + `mirrored:true` | 9 / 9 | 0 | — | rótulo volta correto |
| `noGreen` | **sem o setor verde** | **0 / 9** | 0 | `zero_landmark_missing`, `alias_margin_low`, `zero_landmark_disagrees` | **abstém** — o pente de 37 bolsos empata os picos |
| `lowLuma` | cena quase preta | **0 / 9** | 0 | `luma_out_of_range` | **abstém** |
| `occlusion` | oclusão estática sobre o rotor | **6 / 9** | 0 | `zero_landmark_missing` quando o zero passa por baixo | **abstém no trecho ocluído** |
| `static` | roda parada | **0 / 9** | 0 | `low_energy`, `sign_inconsistent`, `magnitude_out_of_prior` | **abstém** |

O caso `noGreen` é o mais informativo da tabela: **sem a marca única, o estimador se cala**.
É a prova de que a defesa contra o aliasing de padrão (D4/D5) está ligada, e é também o
risco declarado do desenho — se a mesa real não entregar o verde de forma legível, a
cobertura despenca (e isso só o V3-B mede).

**Cadência é pré-requisito, não detalhe.** Um feed a 25-30 fps (o que uma mesa ao vivo
entrega) precisa ser **decimado** até ~11 fps efetivos antes da medição: 6 frames
consecutivos a 30 fps cobrem 167 ms, e o guard `stride_too_small` — que exige Δt de par
≥ 270 ms — dispararia em **toda** janela. O coletor decima por `mediaTime` e o replay
aceita `--decimate` para capturas gravadas na taxa nativa. Sem isso, a cobertura de campo
sairia 0/N e o V3-B leria como propriedade do mundo o que é defeito de ferramental.

| Feed | sem decimação | com decimação |
|---|---|---|
| 25 fps, 40 frames | 0 emitidos · `stride_too_small` em 35/35 janelas | 9/9 emitidos, 0 errados |
| 30 fps, 60 frames | 0 emitidos · `stride_too_small` | 15/15 emitidos, 0 errados |

## 4. Bancada — instrumento contra `<video>` local  ⚠️ parcial · ❌ não elegível a gate

| Item | Estado |
|---|---|
| `probe/fixture_video.html` gera roda sintética → `captureStream()` → `<video>` real | ✅ entregue |
| E0b exercitado contra esse `<video>` (rVFC, visível/oculto, gaps) | ✅ entregue e rodável |
| Teste de taint pelo mesmo caminho da probe | ✅ entregue e rodável |
| Benchmark p50/p95/máx **no renderer** | ✅ entregue (botão *Medir 120 frames*) |
| Números do renderer preenchidos | ⬜ dependem de quem rodar a bancada (ver `ORCAMENTO.md`) |
| Custo medido em Node (bancada, `--bench`, 300 frames) | unwrap p50 **0,74 ms** / p95 1,02 / máx 1,57 · análise p50 **8,78 ms** / p95 13,59 / máx 15,87 por medição |

## 5. Gates de GO  ⬜ TODOS VAZIOS — só `evidence_class: field` preenche

| Gate | Numerador | Denominador | Valor | Limiar | Passa? |
|---|---|---|---|---|---|
| **H2** — rotor alterna 1:1 com a âncora | ⬜ | ⬜ *(giros **anotados**, não vereditos)* | ⬜ | ≥ 40 giros anotados | ⬜ |
| **Cobertura** *(medida ANTES da acurácia)* | ⬜ vereditos emitidos | ⬜ giros anotados | ⬜ | ≥ 0,50 | ⬜ |
| **Acurácia** | ⬜ acertos | ⬜ vereditos emitidos | ⬜ | ≥ 29/30 **e** ≥ 30 emitidos | ⬜ |
| **Sinal (replay)** | ⬜ janelas corretas | ⬜ frames processados | ⬜ | ≥ 98% *(exige captura ≥ 250 frames)* | ⬜ |

| Metadado obrigatório da coleta | Valor |
|---|---|
| Data da coleta | ⬜ |
| Mesa / dealer | ⬜ |
| `calibration_id` | ⬜ |
| `algorithm_sha` usado na coleta | ⬜ |
| `config` congelada antes da coleta | ⬜ |
| Soak de 2 h executado? | ⬜ |

**Regras de leitura dos gates (congeladas, ver `lib/pipeline.js`):**

- `sinal = janelas que emitiram e acertaram / frames_processed`. O denominador inclui os
  5 frames de aquecimento **de propósito**: assim o gate de 98% é aritmeticamente
  inalcançável com captura curta (< 250 frames), e não dá para exibir "98%" de 30 frames.
- `acuracia` usa **todos** os vereditos emitidos — não os melhores 30.
- Se `vereditos_emitidos < 30`, o resultado é **NO-GO por escassez**, não "acurácia alta".
- Cobertura é medida **antes** de acurácia. A ordem não é estética: um sensor que abstém
  em 95% dos giros e acerta os 5% restantes exibiria "acurácia perfeita".
- Ajustar limiar depois de ver os dados transforma a coleta em conjunto de desenvolvimento
  e **exige nova coleta independente** (`FORMATO_CAPTURA.md` §Disciplina).

## 6. Decisões que exigem humano (registradas no ADENDO ISO)

1. **GO/NO-GO é decisão de investimento** (§10.6-1): o spike entrega os números; o operador
   decide se a latência de correção (1-3 giros, contra 30-60 min do V6) paga o esforço L do
   SPR-V5 **mais manutenção perpétua de visão sobre o layout de um terceiro**.
2. **Aceite formal da cobertura medida** (§10.6-2): o comportamento do `<video>` com a aba
   oculta e a janela minimizada **não pode ser presumido**. V6A/V6B não dependem de pixels.

## 7. Se der NO-GO

O programa de vídeo **para**. O valor operacional fica coberto por **SPR-V4 + SPR-V6A**, que
não dependem de pixel nenhum. Custo afundado: **1 spike S/M**. NO-GO é um resultado válido
e barato — e é justamente para poder dizê-lo cedo que este sprint existe.
