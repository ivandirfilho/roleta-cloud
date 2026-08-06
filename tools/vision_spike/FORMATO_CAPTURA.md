# SPR-V3 · Formato de captura (v1) — o que o `replay.js` lê

> Uma captura é o par **frames crus + contexto que os torna interpretáveis**. Frames sem
> calibração, sem `mediaTime` e sem o `algorithm_sha` congelado não são evidência: são
> bytes. Este documento é o contrato entre quem coleta (navegador) e quem analisa (Node).

## Layout no disco

```
minha-captura/
  capture.json      # manifesto (obrigatório)
  frames.bin        # RGBA concatenado  (modo `data_file`, exportado pelo popup)
  000000.rgba ...   # OU um arquivo por frame (modo `file`)
```

**Nada disto entra no git** — `tools/vision_spike/.gitignore` bloqueia. Frames nunca saem
da máquina do operador.

## `capture.json`

```jsonc
{
  "format": "vision_spike_capture",
  "version": 1,

  // ⚠️ o campo mais importante do arquivo
  "evidence_class": "field",          // "synthetic" | "fixture" | "field"
  "eligible_for_go_gates": true,      // só true quando evidence_class == "field"

  "created_at": "2026-08-05T21:30:00.000Z",

  // intrínsecas do RECORTE gravado (não do <video> inteiro, se houve crop na ROI)
  "video": { "width": 320, "height": 260 },

  // SHA dos arquivos do algoritmo no momento da coleta. O replay AVISA se divergir:
  // comparar números medidos com algoritmos diferentes é comparar coisa nenhuma.
  "algorithm_sha": "f7062d25ffffc35c",

  // thresholds CONGELADOS antes da coleta (ver "disciplina", abaixo)
  "config": { "pairStride": 3, "emitFloor": 0.7 },

  "calibration": {
    "version": 1,
    "calibration_id": "cal-m1x2y3",
    "center": { "x": 160, "y": 130 },   // coordenadas do RECORTE gravado
    "a": 90, "b": 60, "phi": 0.15,
    "rotorBand": [0.55, 0.95],
    "sceneBand": [1.15, 1.45],
    "degPerBin": 0.5,
    "mirrored": false,
    "sceneSignature": [ /* 180 números: anel estático, referência do NCC */ ],
    "thumbnail": "data:image/jpeg;base64,...",   // para o humano reconhecer a cena
    "fit_quality": { "residualRms": 0.004, "condition": 12.3, "angularGapDeg": 71, "pointCount": 8, "warnings": [] },
    "video": { "width": 1280, "height": 720 }    // intrínsecas do <video> original
  },

  // anotação HUMANA. `null` significa "ninguém anotou" — e o replay então NÃO calcula
  // acurácia nem sinal. Ausência de verdade não vira verdade conveniente.
  "truth": { "direction": "cw", "annotated_by": "operador", "round_id": "..." },

  // modo `data_file`: `offset` é o índice do frame dentro do arquivo (stride = w*h*4)
  "data_file": "frames.bin",
  "frames": [
    { "file": null, "offset": 0, "wallMs": 0,    "mediaTimeS": 12.340, "visibilityState": "visible" },
    { "file": null, "offset": 1, "wallMs": 98,   "mediaTimeS": 12.437, "visibilityState": "visible" }
  ]
}
```

Modo alternativo (um arquivo por frame): omita `data_file` e preencha `file` com
`"000000.rgba"`, `"000001.rgba"`, …

## Campos obrigatórios e por quê

| Campo | Por que é obrigatório |
|---|---|
| `video.width/height` | o `.rgba` é cru: sem dimensões, os bytes não têm forma. O replay recusa arquivos com tamanho ≠ `w*h*4` |
| `calibration` | sem elipse não há unwrap; sem `sceneSignature` o guard de NCC vira decorativo |
| `mediaTimeS` | é a **régua do stream**. Sem ele o Δt cai para wall-clock e o estimador registra o guard `dt_from_wall_clock`. É também a régua da **decimação** |
| `algorithm_sha` | um número de gate sem o SHA do algoritmo que o produziu não é reproduzível. O coletor o preenche a partir de `lib/algo_sha.js`, a **mesma receita** que o `replay.js` usa — com **EOL normalizado**, senão o mesmo commit daria hashes diferentes no Windows (CRLF na cópia de trabalho) e no Linux/CI (LF). Se der `null`, o replay avisa que não dá para comparar |
| `evidence_class` | separa bancada de campo. O coletor grava aqui **o que o operador declarou no popup** — nunca um literal `field` |

## Disciplina de coleta (contra tuning-no-avaliado)

1. **Congele** `config` e `algorithm_sha` **antes** de coletar. Anote os dois no
   `capture.json` e no `RESULTADO.md`.
2. Se você ajustar qualquer limiar depois de olhar os dados, a coleta vira **conjunto de
   desenvolvimento** e o gate exige uma **coleta nova e independente**. Ajustar e avaliar
   nos mesmos 40-60 giros produz um número que só descreve o próprio ajuste.
3. Uma captura para o gate de sinal precisa de **≥250 frames** — abaixo disso o teto
   aritmético (`(n−5)/n`) fica sob 98% e o gate é inalcançável por construção. O replay
   avisa quando a captura é curta demais.

## Transferência da captura (navegador → disco)

`chrome.runtime.Port` **serializa em JSON**. Uma typed array mandada crua chega do outro
lado como `{"0":12,"1":34,…}`, um objeto **sem `.length`** — e um montador ingênuo produz um
`frames.bin` de **0 byte** se dizendo completo. Por isso o fio é:

```jsonc
{ "type": "frames", "wire": "base64", "from": 0, "to": 0,
  "frames": [ { "index": 0, "b64": "AAEC…", "length": 333312 } ] }
```

| Formato | Custo no fio (frame de 330 KB) | Por quê |
|---|---|---|
| **base64** (escolhido) | **1,333×** → 440 KB | JSON-safe, codec próprio (sem `btoa`/`Buffer`), 13,4 ms para codificar e 3,3 ms para decodificar |
| `Array` de números em JSON | ~3,57× → 1,18 MB | mesmo resultado, quase 3× o tráfego |
| typed array crua | **corrompe** | vira objeto sem `length` |
| structured clone | — | não assumido: exigiria versão mínima de Chrome sem requisito formal |

Numa captura de 300 frames isso é **+34 MB** no fio e **~5 s** de CPU no total — uma vez, e
offline. O receptor valida `length` declarado contra o decodificado; frame que não bate é
**recusado**, não confirmado e continua contando como faltante, então a transferência jamais
se declara completa com dado corrompido.

## Como gerar

- **Navegador (gravação para o gate de sinal)**: popup → **Gravar p/ replay** com ≥ 250
  frames → **Exportar captura** (abre uma aba durável, com ack/retomada) → *Salvar*. Saem
  `capture.json` + `frames.bin` no seu disco. O coletor **decima** os frames até a cadência
  segura (~92 ms entre frames aceitos), então 300 frames ≈ 28 s de vídeo, e a captura já
  vem com `algorithm_sha` e `config` preenchidos pelo próprio coletor. A gravação respeita
  um **teto de memória cumulativo**: se a ROI for grande, ela para cedo e registra
  `record.stopped_by: "memory_budget"` — nunca aloca além do teto para cortar depois.
- **Navegador (um giro só)**: marque *guardar captura* antes de *Iniciar* o coletor. Sai uma
  captura de 6 frames — serve para depurar uma medição, **não** para o gate de sinal
  (teto aritmético de 6 frames = 16,7%).
- **Captura gravada na taxa nativa** (por outra ferramenta, sem decimação): rode o replay com
  `--decimate`. Sem isso, um feed de 25-30 fps dispara `stride_too_small` em toda janela e a
  cobertura sai 0.
- **Bancada/CI**: `node replay.js --synthetic cw` gera a sequência em memória (não grava
  arquivo) e roda o pipeline. É `evidence_class: synthetic` e **não vale gate**.
