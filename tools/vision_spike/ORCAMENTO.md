# SPR-V3 · Orçamento e custo

> Alvo do brief: **1-3 ms por frame no renderer do iframe**, e **zero impacto** no service
> worker e no read-loop de 2 s da extensão de produção.

## 1. Onde o custo cai (e onde não cai)

| Componente | Frequência | Onde roda |
|---|---|---|
| Trigger de movimento (grade 12×12 de luma na ROI) | ~1 Hz | renderer do iframe |
| Unwrap elíptico (720 ângulos × 16 raios) + assinatura de cena | por frame **aceito** da medição (6 por giro) | renderer do iframe |
| Correlação circular ±120° × 3 pares + guards | **1 vez por giro** | renderer do iframe |
| Service worker MV3 | — | **nada**: o spike não usa o SW da extensão de produção |
| Read-loop de 2 s / `captureVisibleTab` | — | **nada**: o spike não consome a quota de captura |

**Decimação (por que o custo não escala com o fps do feed).** O `requestVideoFrameCallback`
dispara na taxa nativa do stream (25-30 fps numa mesa ao vivo), mas o coletor só **aceita**
um frame a cada ~90 ms — cadência mínima para que o guard `stride_too_small` não seja
inevitável (`Direction.recommendedFrameIntervalS()`). Os frames rejeitados custam apenas o
callback: não há `getImageData`, não há unwrap. Ou seja, dobrar o fps do feed **não** dobra
o custo da medição.

O ponto do desenho: o `<video>` é lido **dentro do renderer do iframe**, com
`requestVideoFrameCallback`. Não há quota (`captureVisibleTab` tem
`MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND = 2`, **bucket global por extensão**, compartilhado
com o OCR da produção), não há mensagem por frame para o SW, e não há novo seletor de DOM.

## 2. Números medidos (V3-A, bancada)

Medição em Node 24.13, frame 320×260 RGBA, 720 ângulos × 16 raios, 300 frames com
aquecimento de JIT — reproduzível por
`node tools/vision_spike/replay.js --synthetic cw --count 300 --bench`:

| Etapa | p50 | p95 | máx |
|---|---|---|---|
| unwrap do rotor + assinatura de cena (**por frame**) | **0,74 ms** | 1,02 ms | 1,57 ms |
| correlação + guards (**por medição**: 6 frames, 3 pares) | **8,78 ms** | 13,59 ms | 15,87 ms |

Orçamento por giro, com 6 frames por medição:
`6 × 0,74 ms + 8,78 ms ≈ **13,2 ms por giro**` — num ciclo de mesa de ~44 s.

⚠️ **O que estes números NÃO provam.** São de **bancada em Node**, sobre buffers já em
memória. Faltam nessa conta, e só a mesa real fecha:

1. o custo de `createImageBitmap` + `drawImage` + `getImageData` **no renderer** (decode e
   cópia GPU→CPU), que costuma dominar;
2. a resolução real do `<video>` da Evolution (a ROI recortada pode ser maior que 320×260);
3. a contenção com o próprio player e com o resto da aba.

Para medir no renderer: abra `probe/fixture_video.html` → **Medir 120 frames**. Ele reporta
p50/p95/máx do unwrap **no navegador** e o custo de uma medição. Ainda assim é `fixture`:
mede o instrumento, não a mesa.

## 3. Memória

| Item | Tamanho |
|---|---|
| perfil angular (720 × Float64 × 2 canais) | ~11,5 KB por frame |
| janela de 6 frames (só perfis) | ~69 KB |
| captura opcional em memória (6 frames de ROI 320×260 RGBA) | ~2 MB por giro |
| gravação para replay (300 frames, mesma ROI) | ~100 MB, com teto de 350 MB |
| ring de vereditos em `chrome.storage.local` | 500 registros de metadados |
| ring de intervalos do medidor E0b | 7200 amostras (teto fixo) |

A captura só existe se o operador marcar *guardar captura* ou usar *Gravar p/ replay*. Sem
isso, os pixels são descartados assim que o perfil é extraído.

## 4. Custo de manutenção (o item que o §10.6-1 manda pesar)

O que o spike **elimina** de dívida futura, comparado ao desenho original:

- sem `MutationObserver` em status de rodada ⇒ **zero seletor de DOM novo** para quebrar
  quando a Evolution mudar o layout;
- sem `offscreen document` ⇒ sem permissão nova, sem lifecycle de singleton, sem messaging;
- sem `captureVisibleTab` no caminho de medição ⇒ sem disputa de quota com o OCR.

O que **permanece** como manutenção perpétua se o SPR-V5 for aprovado:

- a **calibração** depende do enquadramento: mudou a janela ou a mesa, recalibra (o NCC < 0,6
  denuncia sozinho, mas alguém tem de clicar de novo);
- a **premissa cromática**: o estimador depende do setor verde do zero ser único e visível.
  Um redesign visual da mesa (ou um overlay novo por cima da roda) derruba a cobertura —
  e é por isso que a saída é **abstenção**, não palpite;
- a **premissa H2** (rotor alterna 1:1 com a âncora) precisa continuar valendo; se a mesa
  mudar a regra de lançamento, o sensor mede certo e o *rótulo* fica errado.

## 5. Custo do NO-GO

Se os gates reprovarem, o gasto total é **1 spike S/M** e o programa de vídeo para. O valor
operacional fica coberto por SPR-V4 + SPR-V6A, que não dependem de pixel nenhum. **NO-GO é
um resultado válido e barato, não fracasso.**
