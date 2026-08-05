# SPR-V5 · Sensor de direção shadow-only (`direction_sense.js`) · Bloco BLK-D/extensão · Pri P2 **condicional**

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte: `proposta_seletor_sentido_03_08.md` §10.2.1/10.2.2 (redesenho Sensor R), §10.4, §10.5, §11.3.

## 🚫 STATUS: BLOCKED — não execute
```text
blocked_by: [SPR-V2 (merged), SPR-V3 com veredito GO do operador, SPR-V4 (merged)]
```
Este brief **só destrava** quando **todas** as condições abaixo estiverem escritas no `sprints/BOARD.md`
pelo Diretor:
1. **SPR-V3 = GO**, com os quatro números de campo preenchidos em `tools/vision_spike/RESULTADO.md`:
   H2 confirmada (rotor alterna 1:1 com a âncora em ≥40 giros anotados) · acurácia ≥29/30 nos
   vereditos emitidos com anti-cena ativo · sinal ≥98% no replay · cobertura projetada ≥50%.
2. **SPR-V4 mergeado** (contrato `event_id + round_id + target_spin_seq + TTL + one-shot` e trilha
   `phase_events`) — sem ele o evento velho trava a direção autoritativa.
3. **SPR-V2 mergeado** (senão a evidência de ingestão continua ruim).
4. **GO/NO-GO é decisão de investimento do operador** (§10.6-1): o spike entrega os números; o humano
   decide se a latência de correção (1-3 giros vs. 30-60min do V6) paga um sprint L **mais manutenção
   perpétua de visão sobre o layout de um terceiro**.
Se você é um executor e chegou aqui sem essas condições no board: **pare e avise o Diretor.**

## Meta (preencher quando destravar)
```text
blocked_by: [SPR-V2, SPR-V3(GO), SPR-V4, SPR-V6A]   # V6A também edita popup/background → serializa
locks:      [extensão-JS, manifest, popup]
touches:    [extension/direction_sense.js (novo), extension/manifest.json,
             extension/background.js, extension/popup.js, tests/js/]
base_sha:   origin/main             # rebasear após o merge de V2, V4 e V6A
branch:     spr/SPR-V5
```
**Colisão:** `extension/background.js` e `extension/popup.js` são tocados por SPR-V2, SPR-V6A e pelos
SPR-X1/X2/X3/X4 do backlog (lock `extensão (JS)` ≡ `extensão-JS`). **Nunca** rode dois deles em
paralelo — serialize e rebaseie.

## Objetivo (1 frase)
Produzir uma **observação física do sentido** a partir do vídeo da mesa e enviá-la ao servidor
**somente como evidência de shadow** — para que, meses depois e sob gate estatístico, ela possa
corrigir a **âncora** (nunca o giro).

## Desenho aprovado (o que sobreviveu aos contrapontos)
- **Fonte:** `<video>` dentro do iframe da Evolution, lido por content script `all_frames: true`
  (padrão de `extension/manifest.json:28-34` / `extension/deal_capture.js`), via
  `requestVideoFrameCallback` (timestamps reais do stream, 10-15 FPS). **Zero quota**, ROI em
  coordenadas do vídeo (invariante a zoom/janela/overlay), custo 1-3ms/frame no renderer do iframe.
- **Mede o ROTOR, não a bolinha.** A bolinha, a 1-3 rev/s, anda 180-540° entre frames → o
  deslocamento aparente é ruído (Nyquist). O rotor anda 36-90° em 600ms → mensurável.
- **Pipeline:** crop na ROI calibrada → guards de cena (luma, NCC contra a thumbnail da calibração) →
  **unwrap elíptico** (720 ângulos × 16 raios; a roda em vista oblíqua é elipse — sem Hough) → perfil
  angular no **canal cromático** (o verde do zero quebra a periodicidade dos 37 bolsos e mata o
  aliasing de padrão) → high-pass temporal (mata trava em overlay estático) → correlação circular 1D
  ±120° → consistência entre 3 pares + prior de magnitude.
- **Confidence honesta:** qualquer guard disparado ⇒ confidence ≤0,5 ⇒ **abstenção**. Nunca palpite.
  "Consistência entre pares" **sozinha é desonesta**: aliasing é erro sistemático, os pares erram
  juntos e concordam entre si.
- **Trigger:** probe de movimento a ~1 FPS **na própria ROI** (trigger e sensor no mesmo pixel; zero
  seletor novo para apodrecer), confirmado pela transição OPEN→CLOSED que o poll de 2s já entrega.
  **Não** implementar `MutationObserver` de status (o `content.js` roda só no top frame; o status vive
  dentro do iframe).
- **Offscreen document: rejeitado.** O SW MV3 tem `createImageBitmap` + `OffscreenCanvas` nativos.
- **`captureVisibleTab`: só diagnóstico manual**, nunca autoridade (quota global compartilhada com o
  OCR, `extension/background.js:311-337`; cego com janela minimizada).
- **Fallback de taint:** `SecurityError` (HLS cross-origin sem CORS) é detectável em **um** try/catch
  → desliga o sensor com métrica, sem quebrar nada.
- **Calibração:** operador clica centro + 3-4 pontos da borda → ajuste de elipse, salvo com thumbnail;
  invalidação automática por NCC <0,6.
- **Policy client-side:** `visionSensorPolicy` em `storage.local`, default `'off'` (espelho do padrão
  `fotoCapturePolicy` já existente) + kill-switch por constante.

## Tarefa (quando destravar)
1. `extension/direction_sense.js` — content script `all_frames`, rVFC, ROI/algoritmo acima, ring
   buffer local de vereditos (evidência auxiliar).
2. Emissão de `direction_event` **no contrato do SPR-V4** (`event_id`, `round_id`, `direction`,
   `confidence`, `captured_at_ms`, `frame_count`, `sensor_version`, `calibration_id`) via
   `background.js` → WS. **Sem `target_spin_seq` autoritativo do cliente** — quem atribui é o servidor.
3. UI de calibração + badge de estado do sensor no popup.
4. Telemetria: cobertura (giros com veredito ÷ giros elegíveis), abstenções por guard, taint,
   custo por frame.
5. Bump de `manifest.version` + **comando reproduzível + `sha256`** que reconstrói o pacote da versão
   anterior (o agente não anexa binário a PR).
6. **Controle positivo (dono é ESTE sprint, não o V7):** entregue, junto do sensor, um harness de
   **replay/sessão sintética** que roda o pipeline com a âncora deliberadamente **espelhada** e prova
   que o sensor discorda de forma consistente. Sem esse artefato, o gate T4 do SPR-V7 é
   inverificável e ninguém depois saberá de quem era a tarefa. ⚠️ **Nunca** espelhe o seed produtivo:
   com INV-3 a aposta sai, então isso mudaria o lado da aposta real com dinheiro.

## Critério de "pronto" (Definition of Done)
- [ ] **Shadow-only provado**: teste/monkeypatch que **falha** se algo neste sprint alterar `direcao`,
      `seed_parity`, `seed_n`, `spin_seq`, `timeline_cw/ccw`, decisão ou stake.
- [ ] `SDA_DIRECTION_VISION` continua **congelada em 0**; o evento só alimenta a trilha do SPR-V4.
- [ ] Abstenção real: com guard disparado, **nada** é enviado (teste do módulo puro + replay).
- [ ] Taint/`SecurityError` → sensor desliga com métrica, sem exceção não tratada.
- [ ] **Cobertura medida e reportada ANTES de qualquer número de concordância.**
- [ ] **Custo e beat com limiar numérico** (não "sem degradação mensurável"): custo por frame **p95
      ≤3ms** no renderer do iframe; **zero** tick do alarme de 2s perdido em uma janela de 30min de
      replay; ocupação do SW medida antes × depois. Cole os números no Log.
- [ ] **Frames nunca saem da máquina**: teste que inspeciona o payload emitido e **falha** se contiver
      `ImageData`, blob, base64 ou qualquer campo >1KB. "Verificado a olho" não conta.
- [ ] Controle positivo (item 6) roda em CI/replay e produz relatório versionado.
- [ ] `pytest tests/` completo verde; `node --test` verde para a lógica pura.

## Guardrails (inviolável)
- **Sem autoridade antecipada.** Este sprint **não** corrige nada, **não** chama `set_seed`, **não**
  influencia a fusão. Qualquer atalho aqui contamina timeline, população estratégica e a **aposta
  real** (INV-3 garante que a aposta sai — não há abstenção do lado da estratégia).
- **INV-3** intacto. Flags default-OFF, leitura por chamada. Policy client-side default `'off'`.
- **Git**: só no worktree/branch `spr/SPR-V5`; **NUNCA** main; entregue por **PR**; sem SSH/host/prod.
- **Não commitar `graphify-out/`**, frames ou vídeos.

## Validação (rode e cole o resultado no Log)
```
node --test tests/js/                         # lógica pura do sensor + controle positivo
python -m pytest tests/                       # suíte COMPLETA do servidor
python tools/lint_silent_except.py --update   # só se criou except Exception
```
+ roteiro manual do popup (calibração, badge do sensor, abstenção) com resultado esperado por passo.

## Rollback (ISO — 3 camadas; execução é do **operador**)
1. `visionSensorPolicy = 'off'` no popup. 2. Kill-switch por constante + reload (~30s).
3. Reconstruir o pacote da versão anterior pelo comando documentado no PR (~3min).
Servidor: nada a desligar (o sensor é cliente).

## Stop-conditions após ativar o shadow
`stale + selfcontradict` ≥1% · cobertura <60% dos giros com aba visível · aba visível <30% do tempo de
operação (⇒ **o programa não paga: encerrar**) · degradação do beat de 2s ou do SW.

## Closeout
Igual aos demais: Validação → ADENDO ISO → `code-review` → Log → `graphify update` local →
commit em `spr/SPR-V5` (trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`)
→ push → **abrir PR** → `store_memory` → avisar o Diretor.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
