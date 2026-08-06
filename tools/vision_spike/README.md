# SPR-V3 · `tools/vision_spike/` — preflight técnico do vídeo/iframe

> **Spike de decisão, não produto.** Existe para responder, com números falseáveis e custo
> baixo, **se existe um caminho técnico** para observar o sentido físico da roleta a partir
> do `<video>` da mesa — antes de investir num sensor (SPR-V5) que carrega manutenção
> perpétua sobre o layout de um terceiro.

## O que este diretório NÃO faz

- ❌ Não emite `direction_event`. Não fala com o servidor. Não abre WebSocket. Não faz upload.
- ❌ Não altera `direcao`, `seed_parity`, `spin_seq`, timeline, decisão ou stake. **INV-3 intocado.**
- ❌ Não é importado por `server/`, `state/`, `extension/` nem por nenhum caminho de produção.
- ❌ Não usa `captureVisibleTab` (quota global de 2 chamadas/s dividida com o OCR da extensão
  de produção, e cego com a janela minimizada). Só serve como diagnóstico manual, nunca como fonte.
- ❌ **Não declara GO/NO-GO.** GO/NO-GO é decisão de investimento do operador (§10.6-1),
  tomada sobre os números de campo do V3-B.

## Estado do sprint

**V3-A entregue. `WAITING_HUMAN_EVIDENCE`.** As probes existem, rodam e gravam; o replay
offline roda; o protocolo está escrito. Os campos de campo em [`RESULTADO.md`](RESULTADO.md)
estão **vazios** e só um humano com mesa ao vivo pode preenchê-los.

## Mapa

| Caminho | O que é |
|---|---|
| `lib/ellipse.js` | ajuste de elipse (centro fixo + ≥4 pontos, QR de Householder) e NCC |
| `lib/unwrap.js` | unwrap elíptico 720×16, perfil cromático do rotor, assinatura de cena, grade do trigger |
| `lib/direction_core.js` | estimador: high-pass temporal, correlação circular ±120°, guards, abstenção |
| `lib/rvfc_meter.js` | medidor de cobertura da probe E0b (callbacks/s, gaps, visível×oculto) + **decimador de cadência** |
| `lib/motion_trigger.js` | trigger de movimento a ~1 FPS na própria ROI |
| `lib/pipeline.js` | cola frames→perfis→janelas→sumário **com denominadores explícitos** |
| `lib/synthetic.js` | gerador determinístico de cena (⚠️ `evidence_class: synthetic`) |
| `lib/evidence.js` | envelope de evidência: `synthetic` / `fixture` / `field` |
| `lib/algo_sha.js` | receita ÚNICA do `algorithm_sha` (EOL normalizado), compartilhada por Node e service worker |
| `lib/export_stream.js` | transferência da captura: wire **base64** (JSON-safe), ACK, backpressure, retomada e orçamento de bytes |
| `replay.js` | CLI do replay offline (E1) |
| `manifest.json` + `probe/` | extensão de **diagnóstico separada** (probes E0/E0b, calibração, coletor) |
| `PROTOCOLO_CAMPO.md` | roteiro executável por humano não-autor (V3-B) |
| `FORMATO_CAPTURA.md` | formato da captura que o replay lê |
| `ORCAMENTO.md` | custo por frame medido e o que ele não prova |
| `RESULTADO.md` | **o arquivo que o Diretor cita para destravar (ou não) o SPR-V5** |

## Rodar

```bash
# testes da lógica pura (104 testes, sem Chrome). É o MESMO comando do job
# `extension-tests` do ci.yml, que roda os dois globs:
node --test "tests/js/*.test.js" "tools/vision_spike/tests/*.test.js"
# só o spike:
node --test "tools/vision_spike/tests/*.test.js"
# NB: `node --test tools/vision_spike/` NÃO funciona — o Node tenta carregar o diretório
# como módulo.

# replay offline sobre uma captura gravada
node tools/vision_spike/replay.js --capture caminho/da/captura
# captura gravada na taxa NATIVA do stream (25-30 fps) precisa ser decimada:
node tools/vision_spike/replay.js --capture caminho/da/captura --decimate

# cenário-controle sintético (⚠️ NÃO vale para gate de GO)
node tools/vision_spike/replay.js --synthetic cw --count 300
node tools/vision_spike/replay.js --synthetic cw --case noGreen
# custo p50/p95/máx por frame e por medição
node tools/vision_spike/replay.js --synthetic cw --count 300 --bench
```

Casos sintéticos disponíveis: `clean`, `noise`, `blur`, `overlay`, `noGreen`, `lowLuma`,
`occlusion`, `mirror`.

## Extensão de diagnóstico

1. `chrome://extensions` → modo desenvolvedor → **Load unpacked** → selecione
   `tools/vision_spike/`. **Não substitui a Escuta Beat**: são duas extensões, e esta não
   tem autoridade nenhuma.
2. Abra o popup → escolha a classe da sessão (`fixture` = bancada, `field` = mesa real) →
   **Armar probes**. As probes nascem **desarmadas** (`vsProbePolicy: 'off'`).
3. **Calibração** (obrigatória antes do coletor): popup → *Abrir calibração* → *Capturar
   snapshot* → clique o **centro** e **4-8 pontos da borda externa do disco de bolsos** →
   *Ajustar elipse* → *Salvar*.
4. Bancada sem mesa: sirva este diretório (`python -m http.server` a partir de
   `tools/vision_spike/`) e abra `probe/fixture_video.html`. Ela gera uma roda sintética
   num `<canvas>`, converte com `captureStream()` num `<video>` real e permite exercitar
   E0 (taint), E0b (cobertura) e o custo por frame **no renderer**.
5. **Exportar captura**: popup → *Exportar captura* abre `probe/export.html` numa ABA.
   A transferência tem ack, backpressure e **retomada** — se a conexão cair, o botão
   *Retomar* continua do primeiro frame que falta. (O popup não serve para isso: ele fecha
   ao primeiro clique fora dele e levaria a transferência junto.)
   O fio é **base64**: `chrome.runtime.Port` serializa em JSON, e uma typed array crua
   chegaria do outro lado como `{"0":12,…}` — objeto sem `.length`. Qualquer frame que não
   decodifique é **recusado** (não é confirmado, não conta como recebido), então a
   transferência nunca se declara completa com dado corrompido.

## Fronteira de evidência (a regra que o resto do sprint depende)

| classe | de onde vem | vale para gate de GO? |
|---|---|---|
| `synthetic` | `lib/synthetic.js` | **não** — testa o CÓDIGO, não o mundo |
| `fixture` | `<video>` local da bancada | **não** — testa o INSTRUMENTO, não a mesa |
| `field` | mesa Evolution ao vivo, com operador | **sim** |

O service worker de diagnóstico **rebaixa** automaticamente evidência marcada `field` numa
sessão declarada `fixture`. Rebaixar é seguro; promover, nunca.

## Convenção CW/CCW (declarada, não implícita)

Coordenadas de imagem têm **y para baixo**. O unwrap amostra
`centro + R(φ)·(ρ·a·cos θ, ρ·b·sin θ)`, então **θ crescente percorre a elipse no sentido
horário NA TELA** e um lag positivo de correlação é rotulado `cw`. *Na tela* ≠ *físico*:
se o feed estiver espelhado, marque `mirrored: true` na calibração. **Quem arbitra o rótulo
físico é a anotação humana do V3-B** (gate H2) — nenhum código aqui decreta CW/CCW do mundo.
