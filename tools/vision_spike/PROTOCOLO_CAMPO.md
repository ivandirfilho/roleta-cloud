# SPR-V3-B · Protocolo de campo — coleta de 40-60 giros anotados

> **Para quem:** um operador com a mesa ao vivo. Não é preciso ter escrito o código.
> **Quanto tempo:** ~45-60 min de coleta (ciclo da mesa ≈ 44 s ⇒ 50 giros ≈ 37 min) + 2 h
> de soak opcional, que pode rodar em segundo plano.
> **O que sai daqui:** os quatro números do `RESULTADO.md`. Sem eles não há GO nem NO-GO.

---

## Antes de começar (checklist de 2 minutos)

- [ ] A **Escuta Beat de produção** está rodando normalmente. Este protocolo **não a
      substitui, não a desliga e não interfere** nela.
- [ ] A extensão de diagnóstico `tools/vision_spike/` está carregada (`Load unpacked`).
      São duas extensões ao mesmo tempo — é esperado.
- [ ] Você tem onde anotar 50 linhas: papel, planilha ou o bloco de notas. **A anotação é
      a única fonte de verdade do gate H2.**
- [ ] Você entendeu que **frames não saem da máquina**: nada é enviado a lugar nenhum.
- [ ] Você **não vai** ajustar nenhum limiar durante a coleta. Se ajustar, esta coleta
      vira "desenvolvimento" e o gate exige uma coleta nova (ver `FORMATO_CAPTURA.md`).

---

## Etapa 0 — declarar a sessão e armar

1. Popup da extensão de diagnóstico → marque **mesa real (`field`)**.
2. Clique em **Armar probes**.
3. Anote no cabeçalho da sua folha: data, mesa, dealer (se identificável), e o
   `algorithm_sha` que aparece ao rodar `node tools/vision_spike/replay.js --synthetic cw`.

> Se você marcar `fixture` por engano, toda a evidência é rebaixada e **não vale gate**.
> É intencional: é mais barato repetir a coleta do que descobrir depois que o número era de bancada.

## Etapa 1 — E0: acesso, entrega e taint (2 minutos, uma vez por mesa)

Com a mesa aberta e visível, abra o popup → **Baixar evidência (JSON)**. Procure o registro
`kind: "E0"` e copie para o `RESULTADO.md`:

| Campo do JSON | Vai para o RESULTADO.md |
|---|---|
| `payload.videos[].video_width/height` | resolução intrínseca do `<video>` |
| `payload.videos[].delivery.delivery` | `mediastream` / `blob_url` / `url_https` / `none` |
| `payload.videos[].delivery.mse_confirmed` | `false` ou `null` (**`null` = "não sei", e é uma resposta válida**) |
| `payload.videos[].rvfc_supported` | `requestVideoFrameCallback` existe? |
| `payload.taint.pixel_read_ok` | leu pixel sem erro? |
| `payload.taint.tainted` | `true` ⇒ `SecurityError` ⇒ **o caminho de vídeo morre** |
| `payload.verdict` | `pixels_readable` / `tainted_security_error` / `read_failed_other` / `no_video_in_frame` |

> **`taint: true` é um resultado tão válido quanto `false`** — e é o mais barato de todos:
> encerra o programa de vídeo em 2 minutos em vez de 2 sprints.

## Etapa 2 — E0b: cobertura com aba oculta e janela minimizada (12 minutos)

Cada fase dura **3 minutos**. Não pule nenhuma: `captureVisibleTab` é cego com a janela
minimizada, mas **o `<video>` pode não ser** — é exatamente isso que se está medindo.

1. Popup → seção E0b → **Iniciar**.
2. **Fase A (3 min)** — aba da mesa **visível e em foco**. Não mexa.
3. **Fase B (3 min)** — mude para **outra aba** na mesma janela (a mesa fica *hidden*).
4. **Fase C (3 min)** — **minimize a janela** inteira.
5. **Fase D (3 min)** — volte a janela e a aba (visível de novo).
6. Popup → **Parar** → **Baixar evidência (JSON)**.

Copie do registro `kind: "E0b"` para o `RESULTADO.md`:
`summary.callbacksPerSecond`, `summary.byVisibility.visible.fpsMean`,
`summary.byVisibility.hidden.fpsMean`, `summary.gapCount`, `summary.longestGapMs`,
`summary.mediaTimeAdvancedS`, `summary.missedPresentedFrames`.

> Anote **também** o que você observou na fase C separadamente. `visibilityState` nem sempre
> vira `hidden` ao minimizar, dependendo do sistema — por isso a fase C é anotada à mão.

## Etapa 3 — calibração (3 minutos, refazer se a janela mudar de tamanho)

1. Popup → **Abrir calibração** → **Capturar snapshot**.
2. Clique **1×** no **centro** da roda.
3. Clique **6 a 8 pontos** na **borda externa do disco de bolsos** (o *rotor* — o disco que
   gira, **não** o aro externo onde a bolinha corre). Distribua um por quadrante.
4. **Ajustar elipse**. Leia os avisos:
   - `residual_high` ⇒ o **centro** provavelmente está errado. Recomece.
   - `poor_angular_coverage` ⇒ seus cliques ficaram todos de um lado. Recomece.
   - `few_points` ⇒ tolerável, mas prefira 6-8.
5. **Salvar calibração**. Anote o `calibration_id`.

> Recalibre sempre que redimensionar a janela, trocar de mesa, ou o NCC começar a reprovar
> cenas legítimas.

## Etapa 4 — os 40-60 giros anotados (o coração do V3-B)

1. Popup → **Iniciar** o coletor. (Marque *guardar captura* apenas se for gravar um giro
   específico para replay — cada captura ocupa ~2 MB por giro.)
2. **Para cada giro**, anote **UMA linha** — antes de olhar qualquer saída do sensor:

| # | hora | `round_id` | **sentido do ROTOR** (anotado por você) | veredito | conf | guards |
|---|------|-----------|------------------------------------------|----------|------|--------|
| 1 | 20:14:03 | 1a2b3c | horário | | | |

- **Colunas 1-4 você preenche olhando a MESA.** Anote o sentido de rotação do **disco dos
  bolsos** (rotor) — **não** o da bolinha, que gira ao contrário e é irrelevante aqui.
- **Colunas 5-7 você preenche depois**, do JSON de vereditos. **Nunca antes.** Ver o
  palpite do sensor antes de anotar contamina a anotação, e a coleta inteira perde valor.
- `round_id` você lê no popup da **Escuta Beat de produção** (que já o extrai). Se estiver
  difícil sem atrapalhar a operação, anote só a hora: o pareamento por timestamp basta.

3. Popup → **Baixar vereditos (JSON)**. Cada registro traz `ts`, `direction`
   (`null` = abstenção), `confidence`, `guards`, `deg_per_s`, `visibility`, e os campos
   `operator_direction` / `round_id` **vazios** — que são os que você preenche.

### Etapa 4b — gravar uma captura para o replay (5 minutos, uma vez)

O gate de **sinal** roda sobre uma captura gravada, e exige **≥ 250 frames**. Uma medição
normal tem 6 — insuficiente por construção.

1. Popup → **Gravar p/ replay** com `300` frames. A gravação leva ~30 s (o coletor decima
   os frames para ~11 fps efetivos; frames mais rápidos que isso são inúteis para a medida).
2. Popup → **Baixar captura (replay)** → salva `capture.json` + `frames.bin` (~100 MB).
3. Anote qual era o sentido do rotor durante a gravação e preencha
   `"truth": {"direction": "cw"|"ccw"}` no `capture.json` — **à mão, antes de rodar o replay**.
4. Rode: `node tools/vision_spike/replay.js --capture <pasta>`.

> A captura fica **no seu disco** e não entra no git (`.gitignore` do spike). Copie apenas
> os números para o `RESULTADO.md`.

## Etapa 5 — soak de 2 horas (opcional, roda sozinho)

Deixe o coletor e o E0b ligados por 2 h com a mesa aberta. No fim, baixe evidência e
vereditos e anote: total de vereditos, abstenções, `gapCount`, e se o navegador degradou
(memória, travamentos, beat de 2 s da extensão de produção).

## Etapa 6 — fechar os números

Com a tabela preenchida, calcule **nesta ordem** (a ordem importa: cobertura **antes** de
acurácia, senão um sensor que abstém quase sempre exibe "acurácia alta"):

```
giros_anotados      = linhas da sua tabela                     (denominador de H2 e da cobertura)
vereditos_emitidos  = linhas com veredito != null
cobertura           = vereditos_emitidos / giros_anotados       (gate: >= 0,50)
acuracia            = acertos / vereditos_emitidos              (gate: >= 29/30 E >= 30 emitidos)
H2                  = giros em que o rotor alternou 1:1 com a âncora / giros_anotados (gate: >= 40 giros)
sinal (replay)      = node replay.js --capture <captura>        (gate: >= 98%, >= 250 frames)
```

> Se você usou uma ferramenta externa para gravar (sem decimação), rode com `--decimate`.
> Sem isso, um feed de 25-30 fps dispara `stride_too_small` em toda janela e o resultado é
> 0% de cobertura — defeito de ferramental, não do mundo.

Se `vereditos_emitidos < 30`, o resultado é **NO-GO por escassez** — não "acurácia alta".

Transcreva os quatro números, **cada um com seu denominador**, a data e o `algorithm_sha`
para `RESULTADO.md`. E **pare aí**: GO/NO-GO é decisão de investimento do operador
(§10.6-1), não conclusão automática da planilha.

---

## Regras que não se negociam durante a coleta

1. **Não** interfira na operação para "ajudar" o sensor (reposicionar janela no meio da
   coleta, esperar a cena ficar boa, descartar giro "estranho"). Descarte enviesado é a
   forma mais comum de fabricar um GO.
2. **Não** anote o sentido depois de ver o veredito.
3. **Não** ajuste limiares no meio da coleta.
4. Giro que você não conseguiu anotar com certeza: marque **`?`** e conte no denominador
   como não-anotado (ele sai de H2, mas **fica** registrado — some-o do total, não o apague).
5. Qualquer anomalia (mesa trocou, dealer trocou, stream caiu, janela redimensionada)
   entra numa linha de observação. É isso que explica um número esquisito depois.
