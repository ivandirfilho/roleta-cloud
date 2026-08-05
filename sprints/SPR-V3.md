# SPR-V3 · Preflight técnico do vídeo/iframe (GO/NO-GO) — zero autoridade · Bloco BLK-D/extensão · Pri P1

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte: `proposta_seletor_sentido_03_08.md` §10.2 (contrapontos visão/MV3), §10.4, §10.5, §11.3, §11.4-C.

## Meta
```text
blocked_by: [SPR-V2]                # mesmo lock de extensão/manifest; medição real exige o cliente blindado
locks:      [tools/vision_spike]     # NÃO toca extension/ de produção → não colide com V2/V5/X*
touches:    [tools/vision_spike/** (novo, inclui manifest de diagnóstico próprio),
             sprints/SPR-V3.md]
base_sha:   origin/main             # rebasear em origin/main após o merge do SPR-V2
branch:     spr/SPR-V3
```
**Este sprint NÃO produz autoridade.** Nada aqui pode alterar `direcao`, `seed_parity`, `spin_seq`,
timeline, decisão ou stake. Se você se pegar editando `server/` ou `state/`, **pare**: saiu do escopo.

## Setup (worktree próprio)
```text
git -C "C:\Users\Windows\Desktop\Roleta Cloud" worktree add ..\rc-SPR-V3 spr/SPR-V3
cd ..\rc-SPR-V3
```

## Objetivo (1 frase)
Responder, com números falseáveis e custo baixo, **se existe um caminho técnico** para observar o
sentido físico da roleta a partir do `<video>` da mesa — antes de investir num sensor (SPR-V5) que
carrega manutenção perpétua sobre o layout de um terceiro.

## Contexto mínimo (por que existe)
Hoje o sentido é **inferido** por alternância, não observado. A única fonte capaz de observar sem
clique humano é a **sequência de frames do vídeo**. A auditoria derrubou o desenho original
(`captureVisibleTab` em burst): `MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND = 2` no Chromium, e o bucket
de quota é **global por extensão** (compartilhado com o `captureAndSendFrame` do OCR,
`extension/background.js:311-337`). O desenho candidato é ler o **`<video>` dentro do iframe**
(o repo já injeta content script cross-origin com `all_frames: true`, `extension/manifest.json:28-34`)
via `requestVideoFrameCallback`. Além disso: a bolinha **não** é mensurável (aliasing — a 1-3 rev/s
ela anda 180-540° entre frames), mas o **rotor** (disco central dos bolsos, 0,2-0,5 rev/s) anda apenas
36-90° em 600ms. Tudo isso é **hipótese** até este spike medir.

## Escopo em duas fases (leia antes de começar)
- **V3-A — automatizável (é a DoD deste PR).** Ferramental, protocolo, preflight técnico e replay
  offline. Você entrega isto sozinho, **sem mesa ao vivo**.
- **V3-B — evidência de campo (NÃO é DoD deste PR).** Exige mesa ao vivo, sessão autenticada, Chrome
  com a extensão carregada e um operador anotando giros. Ao terminar V3-A, o sprint fica
  **`WAITING_HUMAN_EVIDENCE`**: você escreve o protocolo, prepara o coletor e **para**, avisando o
  Diretor. **Não declare GO/NO-GO sem os dados.** GO/NO-GO é decisão do operador (§10.6-1).
- ⚠️ **Regra de fronteira (não a viole):** *executar* as probes E0/E0b exige mesa real ⇒ isso é **V3-B**.
  V3-A entrega **a probe rodável + o RESULTADO.md com os campos vazios**. Se você se pegar precisando
  abrir a mesa de produção, autenticar ou pedir credenciais, **você saiu do escopo: pare e avise o
  Diretor.** Nunca acesse a operação real para "fechar a DoD".

## Âncoras (onde entrar)
- `extension/manifest.json:28-34` — content script no iframe cross-origin (`deal_capture.js`,
  `all_frames: true`) — **o padrão a imitar**.
- `extension/manifest.json:35-40` — `content.js` roda **só no top frame** (por isso um
  `MutationObserver` no status da rodada olharia o DOM errado: o status vive **dentro** do iframe).
- `extension/background.js:311-337` — `captureVisibleTab` do OCR: quota global e falha com janela
  minimizada (`:326-329`); falta guard de `tab.active`.
- `extension/background.js` (poll de 2s) — já computa `isOpen`/`OPEN|CLOSED` e extrai `round_id`:
  a transição OPEN→CLOSED é o "bolinha lançada" com ±2s **de graça**.
- `extension/deal_capture.js` — exemplo real de content script no iframe.

## Tarefa

### V3-A (DoD deste PR)
1. **`tools/vision_spike/`** — ferramental isolado, **fora** do caminho de produção:
   - ⚠️ **Manifest**: se a probe precisar de content script próprio, crie **`tools/vision_spike/manifest.json`**
     (extensão de diagnóstico separada, carregada por "Load unpacked" só na máquina do spike).
     **Não altere `extension/manifest.json` de produção** — ele não tem flag e é distribuído ao operador.
   - **E0 · acesso e taint (probe entregue rodável; a EXECUÇÃO é V3-B):** script/content script de
     diagnóstico que responde, por escrito:
     o `<video>` existe no iframe? `srcObject` (WebRTC) ou MSE? `createImageBitmap` +
     `OffscreenCanvas` + `getImageData` funcionam **sem** `SecurityError` (taint)? Um `try/catch`
     único detecta o caso HLS cross-origin sem CORS → fallback limpo. A probe **grava evidência bruta
     em arquivo local**; em V3-A os campos ficam **vazios** no `RESULTADO.md`.
   - **E0b · cobertura (probe entregue rodável; a MEDIÇÃO é V3-B):** instrumento que mede se o player
     continua entregando frames com a aba **oculta** e com a janela **minimizada**
     (`requestVideoFrameCallback` continua disparando? a que taxa?). Ele deve **contar callbacks por
     segundo e gravar a série**. **Não presuma** — `captureVisibleTab` é cego com janela minimizada,
     mas o `<video>` pode não ser.
   - **E1 · calibração + replay:** formato de calibração (centro + 3-4 pontos da borda → ajuste de
     **elipse**, pois a roda em vista oblíqua é elipse; sem Hough) persistido com thumbnail da cena e
     invalidação automática por NCC < 0,6. Um **replay offline** que roda o algoritmo sobre uma
     sequência de frames gravada, para permitir iteração sem mesa ao vivo.
   - **Algoritmo de referência a validar** (documente o que implementou e o que ficou fora):
     crop na ROI → guards de cena (luma, NCC contra a thumbnail) → **unwrap elíptico**
     (720 ângulos × 16 raios) → perfil angular no **canal cromático** (o verde do zero quebra a
     periodicidade dos 37 bolsos e mata o aliasing de padrão) → high-pass temporal (mata trava em
     overlay estático) → correlação circular 1D ±120° → consistência entre 3 pares + prior de
     magnitude. **Qualquer guard disparado ⇒ confidence ≤0,5 ⇒ abstenção. Nunca palpite.**
   - **Trigger:** probe de movimento a ~1 FPS **na própria ROI do vídeo** (o trigger e o sensor são o
     mesmo pixel; zero seletor novo para apodrecer), confirmado pela transição OPEN→CLOSED que o
     poll de 2s já entrega. **Não** implemente `MutationObserver` de status.
2. **Protocolo de campo (documento executável)**: o que anotar por giro (timestamp, `round_id`,
   direção anotada pelo operador, veredito do sensor, confidence, guards disparados), quantos giros
   (40-60), como anotar sem interferir na operação, e como o coletor grava (arquivo local — **frames
   nunca saem da máquina**).
3. **Orçamento e custo**: medir custo por frame (alvo: 1-3ms no renderer do iframe) e confirmar que o
   spike **não** toca o service worker nem o read-loop de 2s.
4. **Relatório `tools/vision_spike/RESULTADO.md`** com os campos vazios/preenchidos de E0/E0b/E1 e a
   tabela de gates (abaixo) pronta para receber os números de campo.

### V3-B (pós-PR, com o operador — o Diretor conduz)
Coleta de 40-60 giros anotados + soak de 2h. Preenche os gates.

## Gates de GO (falseáveis — decidem se o SPR-V5 destrava)
> Todos com **denominador explícito**. Percentual sem denominador não conta.
- **H2 confirmada:** o rotor alterna **1:1** com a âncora em **≥40 giros anotados** (denominador =
  giros anotados pelo operador, não vereditos emitidos).
- **Acurácia ≥29/30** — e **mínimo absoluto de 30 vereditos emitidos** com anti-cena ativo. Se o
  sensor abstiver tanto que não chegue a 30, o gate é **NO-GO por escassez**, não "acurácia alta".
- **Sinal ≥98%** no replay offline (denominador = frames processados no replay).
- **Cobertura ≥50%**: `vereditos_emitidos / giros_anotados` ≥ 0,50, medida **antes** de qualquer
  cálculo de acurácia. O resto é abstenção (o toggle cobre).
- **NO-GO** ⇒ o programa de vídeo **para**; o valor fica coberto por SPR-V4 + SPR-V6A
  (sunk cost = 1 spike S/M). NO-GO é um **resultado válido e barato**, não fracasso.
- **Registro obrigatório**: os 4 números, o denominador de cada um, a data da coleta e o `sha` do
  algoritmo usado ficam em `tools/vision_spike/RESULTADO.md`, **versionado**. É esse arquivo que o
  Diretor cita ao destravar (ou não) o SPR-V5.

## Critério de "pronto" (Definition of Done — só V3-A)
- [ ] `tools/vision_spike/` roda isolado, **sem** import a partir de `server/`, `state/` ou do
      `background.js` de produção.
- [ ] E0 respondido por escrito com evidência bruta (acesso, srcObject/MSE, taint sim/não).
      **Em V3-A: a probe existe, roda e grava — o campo em `RESULTADO.md` fica VAZIO.**
- [ ] E0b: instrumento de medição entregue e testado contra um `<video>` local/fixture.
      **A medição em mesa real (aba oculta / janela minimizada) é V3-B.**
- [ ] Replay offline reproduz o algoritmo sobre frames gravados e emite `{direction, confidence,
      guards}` — com **abstenção** quando qualquer guard dispara.
- [ ] Protocolo de campo escrito e executável por um humano não-autor.
- [ ] `RESULTADO.md` criado com a tabela de gates e os campos de V3-B explicitamente **vazios**.
- [ ] `pytest tests/` completo verde (nada do spike entra no caminho de produção).
- [ ] Sprint termina em **`WAITING_HUMAN_EVIDENCE`** no Log, com a mensagem ao Diretor.

## Guardrails (inviolável)
- **Zero autoridade.** Nenhum `direction_event` é emitido para produção a partir deste sprint.
  Nada altera `direcao`, seed, `spin_seq`, timeline, decisão ou stake. **INV-3** intocado.
- **Frames nunca saem da máquina** (zero upload; só metadados/veredito, e neste sprint nem isso).
- **Offscreen document rejeitado**: o SW MV3 tem `createImageBitmap` + `OffscreenCanvas` nativos.
  Não peça permissão nova no manifest sem justificar no PR.
- `captureVisibleTab` só como **diagnóstico manual**, nunca como fonte de autoridade — e ciente de que
  divide quota global com o OCR.
- **Não declare GO** sem os números de campo. Honestidade do estimador é o produto deste sprint.
- **Git**: só no worktree/branch `spr/SPR-V3`; **NUNCA** main; entregue por **PR**; sem SSH/host.
- **Não commitar `graphify-out/`** nem frames/vídeos capturados (adicione ao `.gitignore` do spike).

## Validação
```
node --test tools/vision_spike/    # se houver lógica pura testável
python -m pytest tests/            # suíte completa (deve seguir verde e intocada)
```
+ evidência bruta de E0/E0b colada no `## Log`.

## Rollback (ISO)
O spike vive em `tools/vision_spike/` e não é importado por produção ⇒ rollback = `git revert` do PR
(ou simplesmente não usar). Se tocar `extension/manifest.json`, o rollback é o zip da versão anterior
(mesma disciplina do SPR-V2).

## Conformidade ISO
- [ ] Nada default-ON; nada no caminho de produção.
- [ ] **INV-3** intacto; `pytest tests/` verde.
- [ ] Mexeu em `extension/` → bump de versão + nota de reload (se aplicável).
- [ ] ADENDO ISO registra: decisão de investimento pendente de humano (§10.6-1) e aceite formal da
      cobertura medida (§10.6-2).

## Closeout
1. Validação → `## Log`. 2. **ADENDO ISO**. 3. `code-review`. 4. Append no Log.
5. `graphify update .` local (não commitar). 6. Commit em `spr/SPR-V3` com trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
7. `git push -u origin spr/SPR-V3` + **abrir PR**. 8. `store_memory` + avisar o Diretor:
*"PR de SPR-V3 aberto — V3-A pronto, aguardando evidência de campo (V3-B)"*.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
