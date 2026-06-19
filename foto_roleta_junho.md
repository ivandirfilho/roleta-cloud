# 📸 Auditoria Técnica — Visão Computacional Nativa na Escuta Beat ("foto_roleta")

> **Data:** 19/06 (junho) · **Autor da auditoria:** revisão sênior assistida (MCPs: graphify, sequential-thinking, brave-search/web, memory, filesystem)
> **Escopo:** avaliar a proposta v3.5 de inserir um pipeline de visão computacional 100% dentro de `extension/` para, a cada novo número detectado, tirar uma "foto" da tela e extrair parâmetros (dealer, modelo da roleta, etc.) por um agente integrado.
> **Grafo consultado:** `graphify-out/graph.json` @ `built_at_commit 3858764` (= HEAD, fresco).

---

## 1. Sumário executivo (TL;DR)

**Veredito: APROVAR A DIREÇÃO ESTRATÉGICA, REPROVAR O PLANO TÉCNICO COMO ESCRITO.**

A ideia central — **mover a extração de metadados do DOM frágil para visão local no cliente, mantendo a Engine Python agnóstica** — é sólida, alinha-se ao desacoplamento que o projeto já persegue e habilita algo que o DOM **não** entrega (identificar o *modelo físico* da roleta). Porém, **4 premissas técnicas da proposta estão incorretas ou superestimadas** e **1 risco bloqueante (DRM) não é mencionado**. Seguir o plano literal levaria a retrabalho e possivelmente a um beco sem saída.

| # | Alegação da proposta | Realidade verificada | Veredito |
|---|----------------------|----------------------|----------|
| 1 | `chrome.tabCapture` captura "mesmo com a janela em segundo plano, oculta ou minimizada" | Só **inicia na aba ativa**; **janela minimizada → throttle/frames pretos**. Em SW exige `getMediaStreamId` → **offscreen** | ⚠️ Superestimado |
| 2 | Inferência via **WebGPU** no offscreen | **Não** existe WebGPU em service worker; em **offscreen é "parcial/não-garantido"** → precisa fallback WASM | ⚠️ Frágil |
| 3 | Micro-modelo **Florence-2 .onnx 4-bit** roda em **<80ms** | Florence-2-base ~345M params; q4 ≈ 86MB; latência real **100–500ms** | ❌ Irreal |
| 4 | Binários `.onnx` **commitados no git** garantem "zero-setup" | 86–172MB no git **incham o repo permanentemente**; conflita com `git clone` ágil | ❌ Anti-padrão |
| 5 | (omisso) | **DRM/EME (Widevine)** faz a captura devolver **frame preto** na área do vídeo | 🚨 Gate-zero |
| 6 | "Sem processar o DOM" | O **gatilho** ("recebeu um número") **é** detecção via DOM — visão é complemento, não substituição | ℹ️ Nuance |

**Recomendação:** adotar uma versão **replanejada e faseada** (Seção 6), começando por um **PoC de 1 dia** com `captureVisibleTab` + **probe de DRM** (Seção 9) antes de qualquer investimento em offscreen/WebGPU/Florence-2.

---

## 2. O que o sistema faz hoje (verdade do código, não da proposta)

Auditoria direta de `extension/` (MV3, `manifest.json` v3.3.2):

- **Arquitetura confirmada:** Engine Python (WebSocket) + Dashboard + Extensão "Escuta Beat". A extensão **não** fala com `localhost:8765` direto — conecta em `wss://roleta.xma-ia.com/ws` (`background.js:106-107`). A "porta 8765" da proposta é a porta **interna** da Engine atrás do proxy.
- **Como um novo número é detectado:** o **service worker** (`background.js`) faz *polling* injetando funções na aba via `chrome.scripting.executeScript({allFrames:true})` e compara hashes — novo resultado quando `newHash !== state.lastHash` (`background.js:1551`). **O gatilho é DOM/extração, não visão.**
- **Dealer / mesa / modelo JÁ são extraídos via DOM hoje** — dois caminhos:
  - *Legacy:* `deal_capture.js` — `MutationObserver` + `PROVIDER_SELECTORS` por provider (evolution/playtech/imagine/pragmatic), grava em `chrome.storage.local.dealMeta`.
  - *Data-driven (v18.2):* `extractSessionData` lê seletores de `extractorData.data.session` (de `providers/evolution.json`), consolidado em `background.js:1494-1548`.
  - Ambos alimentam o payload `novo_resultado` com `dealer / table / provider / round_id` (`background.js:1586-1599`; normalização em `extractor_meta.js`).
- **A dor é real e já documentada:** quando o seletor não casa, o código loga **"Dealer NAO capturado — candidatos no DOM (afinar seletores)"** (`background.js:1537-1543`). Ou seja, **há um custo recorrente de auditoria/refatoração de seletores** sempre que a casa muda o DOM — exatamente o problema que a proposta quer matar.

> **Conclusão da Seção 2:** a proposta resolve uma dor **verdadeira**. Mas como dealer/mesa já vêm do DOM, **visão não substitui o DOM — ela é (a) um fallback auto-curável quando o seletor quebra e (b) a única via para identificar o *modelo físico* da roleta**, que o DOM não fornece de forma confiável.

---

## 3. Objetivo declarado pelo usuário

> "Quando a Escuta Beat receber um número pelo DOM, tirar uma foto da tela e poder capturar qualquer coisa que a gente definir através de um agente integrado. Os objetivos são identificar o **dealer**, o **modelo da roleta** e outros possíveis parâmetros."

Pontos-chave que mudam o desenho:
1. **Event-driven, 1 frame por giro** — não é vídeo contínuo 30fps. Isso reduz o custo computacional em ~30× e **dispensa** stream contínuo no caminho comum.
2. **"Qualquer coisa que a gente definir"** — pede um agente com **tarefas plugáveis** (OCR de campos + classificação + VQA opcional), não um único modelo fixo.

---

## 4. Auditoria ponto-a-ponto

### 4.1 `chrome.tabCapture` "em segundo plano / oculto / minimizado" — ⚠️ superestimado
**Fatos (Chrome for Developers + grupos chromium):**
- Em MV3, `chrome.tabCapture` **não roda no service worker**. O padrão (Chrome ≥116) é: `chrome.tabCapture.getMediaStreamId()` no SW → usar o `streamId` num **offscreen document**. Exige permissões `offscreen` **e** `tabCapture` (hoje **ausentes** no `manifest.json`).
- "**Capture can only be started on the currently active tab after the extension has been invoked**" — comporta-se como `activeTab`. Não dá para iniciar captura silenciosa de uma aba qualquer em background.
- **Janela minimizada / aba não-visível:** o Chrome **faz throttling de renderização** → FPS despenca, podendo gerar **frames congelados ou pretos**. A promessa de captura robusta "oculta por outros programas do Windows" é **parcialmente falsa**.
- *Aba em segundo plano (outra aba focada, janela visível):* normalmente funciona, com possível throttle.

> Fonte: `developer.chrome.com/docs/extensions/reference/api/tabCapture`; discussões `chromium-extensions` sobre tabCapture+offscreen; síntese de testes (web).

### 4.2 Inferência via **WebGPU** no offscreen — ⚠️ frágil
- **Service worker (background MV3): WebGPU NÃO disponível.** (`navigator.gpu` indefinido — limitação rastreada no chromium.)
- **Offscreen document:** suporte **"parcial / incerto / anedótico"**, **não oficialmente garantido**. Funciona em Web Workers e documentos comuns, mas o ciclo de vida do offscreen e blocklist de GPU/aceleração desligada podem derrubá-lo.
- **Implicação:** WebGPU pode ser usado, mas **obriga fallback WASM** (`onnxruntime-web` / `transformers.js` com `device:'wasm'`). Sem fallback, a feature quebra em máquinas sem aceleração — justamente as "máquinas da universidade" citadas como requisito.

> Fonte: MDN `Web/API/GPU`; `developer.chrome.com/.../webgpu/troubleshooting-tips`; `chromium-extensions` "WebGPU API not accessible in service_worker".

### 4.3 Florence-2 `.onnx` 4-bit em **<80ms** — ❌ irreal
- **Florence-2-base ≈ 345M params.** Quantizado: **q4 ≈ 86MB**, **int8 ≈ 172MB**.
- **Latência realista (WebGPU, desktop):** q4 **~100–300ms**, int8 **~200–500ms**. **<80ms só** em GPU de ponta (RTX 30xx / Apple M-series) com entrada minúscula. Florence-2 **decodifica tokens autoregressivamente** (caption/OCR) → inerentemente mais lento que um OCR dedicado.
- Para **ler texto curto** (nome do dealer, id de mesa) há opções **ordens de grandeza melhores**:
  - **PaddleOCR ONNX:** 2–40MB, **10–30ms**.
  - **CNN de classificação pequena:** <5MB, **1–10ms** (ideal para "qual modelo de roleta", que é **classificação**, não geração de texto).

> Fonte: síntese técnica (web) sobre Transformers.js v3 / Florence-2 / PaddleOCR; `transformers.js` confirma WebGPU + quantização por `dtype` (context7 `/huggingface/transformers.js`).

### 4.4 Binários `.onnx` commitados no git ("zero-setup") — ❌ anti-padrão
- Commitar 86–172MB de pesos **incha o repositório para sempre** (cada clone baixa o histórico inteiro), **contradizendo** o requisito de `git clone` ágil em qualquer máquina.
- **Alternativas que preservam o "zero-setup manual":**
  1. **Lazy-download no 1º run** a partir do HF Hub/CDN, cacheado em **Cache API / OPFS / IndexedDB** (transformers.js já faz isso nativamente). O usuário ainda só faz "carregar pasta no Chrome".
  2. **Git LFS** se o binário precisar viajar com o repo.
  3. Empacotar como **`web_accessible_resources`** apontando `transformers.js` para `chrome.runtime.getURL(...)` — **mas** mantendo o blob fora do histórico principal (LFS/release asset).

### 4.5 🚨 DRM / EME (Widevine) — gate-zero **não mencionado**
- `tabCapture` **e** `captureVisibleTab` devolvem **frame preto** na região de **vídeo protegido por EME/Widevine** — por design, sem contornar.
- Cassinos ao vivo (Evolution/Pragmatic) **podem** usar EME no stream. Se usarem, a **roleta física vem preta** na captura. O **dealer/mesa**, por serem geralmente **overlay HTML/Canvas (DOM)**, tendem a aparecer — mas o objetivo "modelo da roleta" depende justamente do vídeo.
- **Portanto:** antes de qualquer build, é **obrigatório** um probe que confirme se a área do vídeo é capturável no provider-alvo (Seção 9).

### 4.6 "Sem processar o DOM" — ℹ️ nuance
A proposta vende "não depender do DOM", mas o **gatilho** ("a Escuta recebeu um número") **é** detecção via DOM/extração (`background.js`). O ganho real é **reduzir a superfície de dependência do DOM** (parar de raspar dealer/mesa por seletor), não eliminá-la. Mensagem honesta: **DOM continua sendo o relógio do sistema; visão vira a câmera.**

---

## 5. Riscos & gates

| Risco | Severidade | Mitigação |
|-------|-----------|-----------|
| DRM/EME → vídeo preto | 🚨 Bloqueante p/ "modelo da roleta" | **Probe DRM** antes de tudo (PoC dia 1) |
| WebGPU ausente/instável no offscreen | Alta | Fallback **WASM** obrigatório; detectar `navigator.gpu` e degradar |
| Captura minimizada/background falha | Média | Tratar como *best-effort*; manter DOM-first; não prometer 100% headless |
| Latência do modelo > orçamento | Média | Right-sizing (OCR/CNN no caminho comum; VLM sob flag) |
| Repo inchado por pesos | Média | Lazy-download/LFS — **nunca** blob no git |
| CPU/bateria (inferência por giro) | Baixa | 1 frame/giro + ROI crop; throttle; rodar só quando WS conectado |
| Custo de manutenção migra de "seletores" p/ "ROIs/modelo" | Baixa | ROIs versionadas por provider (reuso do conceito de `evolution.json`) |

---

## 6. Arquitetura recomendada (faseada, alinhada ao código atual)

Princípio-mestre: **DOM-first, visão como validador/fallback com `confidence`**, sem tocar na Engine Python (que permanece agnóstica — coerente com o invariante "Engine só faz matemática/decisão").

```
[background.js] novo número (newHash != lastHash)         ← gatilho DOM já existente
       │  emite evento {trace_id, ts}
       ▼
[Captura de 1 frame]
   FASE 1 (MVP):  chrome.tabs.captureVisibleTab → JPEG do viewport (aba ativa)
   FASE 2 (robust): tabCapture.getMediaStreamId (SW) → OFFSCREEN → grabFrame()
       │
       ▼
[Offscreen/Canvas] crop de ROIs por provider (faixa do dealer, status, mesa)
       │            (ROIs versionadas, mesmo espírito dos selectors do evolution.json)
       ▼
[Agente de visão]  transformers.js v3 / onnxruntime-web
       │            device: 'webgpu' → fallback 'wasm'
       │            tarefas plugáveis: OCR(dealer,mesa) + CLASSIFY(modelo) + [VQA opcional]
       ▼
[Fusão]  merge com dealMeta DOM → { value, source:'vision'|'dom', confidence }
       ▼
[WebSocket]  MESMO contrato novo_resultado.{dealer,table,round_id,...}
             + campos novos opcionais (vision_*). Engine inalterada.
```

**Por que assim:**
- **Fase 1 não precisa de offscreen, nem WebGPU, nem libs pesadas.** `captureVisibleTab` já é viável com `activeTab`/`<all_urls>` atuais e cobre o caso de uso real (operador olhando a mesa ativa). Entrega valor em dias e **valida o DRM**.
- **Fase 2** só é justificada se houver necessidade comprovada de captura headless/minimizada — e aceitando seus limites (throttle/DRM).
- **Fusão com `confidence`** evita regressão: se a visão errar, o DOM ainda manda. Reduz risco de "alucinar" um dealer e contaminar a atribuição por dealer (que já existe no projeto via `SDA_DEALER_OFFSET`).

---

## 7. Decisão de modelo (right-sizing)

| Tarefa | Recomendado (caminho comum) | Por quê | "Qualquer coisa" (opcional, sob flag) |
|--------|------------------------------|---------|----------------------------------------|
| Dealer / mesa / round (texto curto) | **OCR leve** (PaddleOCR-style ONNX) ou crop fixo + recognizer minúsculo | 10–30ms, 2–40MB, alta acurácia em ROI | Florence-2/SmolVLM em modo "pergunta aberta" |
| **Modelo da roleta** | **CNN de classificação** (<5MB) treinada nos N modelos conhecidos, ou embeddings + kNN | É classificação, não geração → <10ms | VLM com prompt "que roleta é esta?" |
| Parâmetros ad-hoc futuros | Definir ROI + tarefa específica | mantém latência baixa | VLM generalista |

**Conclusão:** **não** usar Florence-2 como motor padrão. Manter o **agente** com backbone leve por tarefa e expor um **modo VLM opcional** (sob flag, aceitando 200–500ms) para satisfazer o "capturar qualquer coisa que a gente definir" sem pagar latência no fluxo normal. transformers.js v3 suporta `device:'webgpu'` + `dtype` (q4/int8) e troca de modelo — bom para essa pluggabilidade.

---

## 8. Contrato de integração (não quebrar a Engine)

- Manter o payload `novo_resultado` **retrocompatível**: continuar enviando `dealer/table/provider/round_id`.
- Acrescentar metadados **opcionais** (a Engine ignora o que não conhece): por ex. `vision: { dealer:{value,confidence}, model:{value,confidence}, source, model_ms }`.
- **DOM-first na fusão:** usar visão para **preencher quando o DOM falhar** ou **validar** quando ambos existirem. Só sobrepor o DOM se `confidence` alta e divergência persistente.
- Zero mudança obrigatória no Python — preserva a manutenibilidade ISO que o projeto documenta e o princípio de Engine "agnóstica".

---

## 9. Plano de PoC (1 dia) — **gate-zero antes de qualquer investimento**

**Objetivo:** provar/derrubar a viabilidade com o menor custo possível.

1. **Probe de captura + DRM (2–3h):** num branch throwaway, no evento de novo número, chamar `chrome.tabs.captureVisibleTab` e salvar o JPEG. Inspecionar:
   - A **área do vídeo** vem preta? → DRM ativo → "modelo da roleta" inviável nesse provider (foco fica em dealer/mesa overlay).
   - O **nome do dealer** aparece legível no frame?
2. **OCR de ROI (2–3h):** recortar a faixa do dealer e rodar um OCR leve (PaddleOCR ONNX em WASM, sem WebGPU ainda). Medir acurácia vs o valor do DOM em ~30 giros.
3. **Decisão:** 
   - DRM bloqueia vídeo **e** OCR do dealer < DOM → **arquivar visão**, investir em melhorar seletores/observers.
   - OCR do dealer ≥ DOM e/ou vídeo capturável → **seguir para Fase 2** (offscreen + classificador de modelo + WebGPU c/ fallback).

**Roadmap (se PoC passar):**
- **F1 (MVP):** captureVisibleTab + OCR ROI + fusão `confidence` (sem offscreen/WebGPU).
- **F2:** offscreen + tabCapture (captura headless best-effort) + CNN classificador do modelo.
- **F3:** WebGPU c/ fallback WASM; modo VLM opcional; ROIs versionadas por provider.

---

## 10. Checklist técnico (quando avançar)

- [ ] `manifest.json`: adicionar `"offscreen"` e `"tabCapture"` (somente na Fase 2).
- [ ] `offscreen.html` + `offscreen.js` com `reason: ['DISPLAY_MEDIA' | 'WORKERS']`.
- [ ] Detecção de capacidade: `navigator.gpu` → WebGPU; senão WASM.
- [ ] Modelos **fora do git** (LFS ou lazy-download cacheado em OPFS/Cache API).
- [ ] `web_accessible_resources` se os pesos forem empacotados.
- [ ] Throttle: no máx. 1 inferência por giro; abortar se WS desconectado.
- [ ] Telemetria: `model_ms`, `source`, `confidence`, taxa DOM-hit vs vision-hit (reuso do padrão de métricas Prometheus do projeto).
- [ ] Privacidade/ToS: confirmar que screenshot local é aceitável; nada de upload de frame para 3º.

---

## 11. Veredito final

- **Aprovar a tese** (visão local cliente-side para desacoplar do DOM e habilitar identificação do modelo da roleta). ✅
- **Reprovar o plano como escrito** em 4 premissas (tabCapture headless garantido; WebGPU garantido no offscreen; Florence-2 <80ms; `.onnx` no git) e **adicionar o gate DRM** que faltava. ❌→🔧
- **Caminho recomendado:** começar **pequeno e mensurável** — PoC `captureVisibleTab` + probe DRM + OCR de ROI — e só então decidir sobre offscreen/WebGPU/VLM. Modelo padrão **leve** (OCR/CNN), VLM apenas sob flag. Integração **DOM-first com fusão por confiança**, **sem alterar a Engine Python**.

> **Próximo passo único e concreto:** rodar o **probe de DRM/captura (item 9.1)**. Ele decide, em poucas horas, se todo o resto do roadmap faz sentido para o provider-alvo.

---
---

# 🧠 Parte 2 — Auditoria do Motor de IA ("foto → dados")

> **Pergunta desta 2ª auditoria:** *qual motor de IA* integrar à extensão Chrome para, a partir da "foto" (frame capturado), **"traduzir" a imagem em dados estruturados** (dealer, modelo da roleta, parâmetros) e plugar na tecnologia atual **da forma mais otimizada**.
> **Método:** pesquisa web atual (jun/2026) sobre runtimes de inferência in-browser, modelos OCR/VLM e a IA nativa do Chrome; síntese com sequential-thinking.

## 12. Não existe "um" motor — existem três famílias

| Família | O que é | Bundle / modelo | Latência (frame pequeno) | Roda em "qualquer máquina"? | Papel ideal |
|--------|---------|------------------|--------------------------|------------------------------|-------------|
| **A. Runtime de modelo aberto local** | **ONNX Runtime Web** (baixo nível) + **Transformers.js v3** (alto nível, roda *sobre* o ORT-Web) | Runtime ~1.7–2MB; modelo 4–30MB (q4/q8) | WASM ~50–300ms · WebGPU ~10–80ms | ✅ Sim (WASM universal) | **Núcleo recomendado** |
| **B. IA nativa do Chrome** | **Gemini Nano** via **Prompt API multimodal** (`LanguageModel.create`) | **Zero bundle** (modelo é do Chrome) | ~centenas de ms–segundos | ❌ Não (16GB RAM, 22GB disco, flags, desktop) | Tier premium opcional |
| **C. OCR clássico** | **Tesseract.js** (LSTM em WASM) | 2–5MB, sem GPU | ~100–800ms | ✅ Sim | Fallback de emergência |

**Fato-chave que desfaz a falsa escolha "ORT-Web *vs* Transformers.js":** o Transformers.js v3 **foi construído em cima do ONNX Runtime Web** (runtime WebGPU reescrito em C++ junto com a equipe do ORT) e suporta ~200 arquiteturas (Florence-2, Moondream, SmolVLM, LLaVa, TrOCR) com `dtype` `fp32/fp16/q8/q4`. Logo: **ORT-Web é o motor; Transformers.js é a camada de conveniência/VLM** sobre o mesmo motor. Escolher um não exclui o outro.

*Fontes: huggingface.co/blog/transformersjs-v3 · github.com/huggingface/transformers.js (releases / dtype) · developer.chrome.com/docs/ai/prompt-api · chromestatus.com feature 5134603979063296.*

## 13. Veredito: **escada de capacidade** (degradação graciosa), não um único modelo

O motor **detecta em runtime** o melhor tier disponível e **cai para o próximo** se faltar suporte. Assim cumpre simultaneamente "otimizado" (usa GPU/IA nativa quando há) e "roda em qualquer máquina" (sempre tem o piso WASM).

| Tier | Motor + modelo | Quando ativa | Latência alvo | Tamanho | Serve para |
|------|----------------|--------------|---------------|---------|------------|
| **T0 — Baseline (sempre)** | **ORT-Web (WASM)** + **PaddleOCR-lite** (det+rec) + **CNN pequena** | sempre | 10–30ms (ROI) | <15MB | dealer/mesa/round (texto) + classificar modelo da roleta |
| **T1 — Aceleração** | mesmo modelo via **ORT-Web (WebGPU)** | `navigator.gpu` presente | 3–5× mais rápido | — | idem, mais rápido |
| **T2 — Pergunta aberta** | **Moondream2 / SmolVLM** via **Transformers.js v3** (q4) | flag `SDA_VISION_VLM` | 200–500ms | 8–15MB | "capturar qualquer coisa que a gente definir" (VQA) |
| **T3 — Premium zero-bundle** | **Gemini Nano** (Prompt API multimodal) | `LanguageModel.availability()==='available'` + hardware | centenas de ms | 0MB (Chrome) | OCR/descrição livre em máquinas potentes |

**Regra de ouro:** o motor **só traduz pixel → JSON**; ele **não decide aposta**. A fusão é **DOM-first + `confidence`**, e a **Engine Python permanece intacta** (coerente com o invariante "Engine só faz matemática/decisão").

## 14. Recomendação concreta do stack ("o motor")

- **Motor núcleo: ONNX Runtime Web** (backend **WASM** como piso, **WebGPU** quando disponível). É o mais maduro, robusto a ops incomuns, ~2MB, cold-start 50–200ms, e é exatamente o runtime sob o Transformers.js — então o investimento é reaproveitável.
- **Modelos ("o tradutor"):**
  - **Texto curto (dealer, mesa, round):** **PaddleOCR-lite** quantizado em ONNX (det+rec) — 4–8MB, 10–30ms, alta acurácia em overlay de UI. Em ROIs de posição fixa, dá para usar só o **recognizer** (sem detector) e ficar ainda mais rápido.
  - **Modelo da roleta:** **CNN de classificação pequena** (<5MB) treinada nos N modelos conhecidos — é *classificação*, não geração de texto; mais barato e robusto que um VLM.
- **Camada VLM opcional: Transformers.js v3** com **Moondream2/SmolVLM** (q4) — só para o tier "pergunta aberta", sob flag. Reusa o mesmo ORT-Web por baixo.
- **Premium detectável: Chrome Built-in AI (Gemini Nano)** — ver §17.
- **Fallback de emergência: Tesseract.js** — se nada acima inicializar.

> Por que **não** começar pelo Transformers.js/Florence-2: para texto curto e classificação, um VLM de 86–172MB é desperdício (latência 100–500ms, repo inchado). O ORT-Web + PaddleOCR/CNN entrega o mesmo resultado em <30ms e <15MB. Transformers.js entra **só** quando precisamos da flexibilidade de VQA.

## 15. Contrato de "tradução" (schema alvo — o JSON que a foto vira)

```jsonc
{
  "dealer":      { "text": "Mia",        "conf": 0.93 },
  "table":       { "text": "Immersive",  "conf": 0.88 },
  "round_id":    { "text": "1x2y...",    "conf": 0.71 },
  "wheel_model": { "label": "evo_classic","conf": 0.95 }, // CNN
  "extras":      { /* campos ad-hoc futuros, ROI-driven */ },
  "engine":      "ort-webgpu",   // ort-wasm | ort-webgpu | transformers | gemini-nano | tesseract
  "roi_version": "evo@2026-06",
  "infer_ms":    24
}
```

Esse objeto é **fundido DOM-first** no payload `novo_resultado` já existente (campos `dealer/table/round_id` + novos opcionais `vision_*`). A Engine ignora o que não conhece → **retrocompatível, sem migração**.

## 16. Otimizações de integração (o "de forma mais otimizada")

Maior impacto primeiro:
1. **Event-driven, 1 frame por giro** — dispara só no `newHash != lastHash` (gatilho que já existe). Nada de vídeo 30fps.
2. **Crop de ROI antes de inferir** — recortar a faixa do dealer/status reduz a entrada em 5–10× ⇒ latência cai 5–10×. ROIs versionadas por provider (mesmo conceito dos selectors do `evolution.json`).
3. **Warm-up no boot** — instanciar runtime + carregar pesos uma vez (no offscreen/worker) para matar o cold-start no 1º giro.
4. **Cache do modelo em OPFS / Cache API** (lazy-download no 1º run) — **fora do git** (preserva clone ágil), zero-setup manual.
5. **Capability-detect uma vez** e fixar o tier por sessão (evita reprobing).
6. **Fusão DOM-first + confidence** — visão só preenche quando o DOM falha ou valida quando ambos existem; nunca sobrepõe o DOM sem alta confiança e divergência persistente (evita "alucinar" dealer e poluir a atribuição por dealer já existente no projeto).

## 17. Deep-dive: Chrome Built-in AI (Gemini Nano) — vale a pena?

**Sim, como tier premium opcional; não como baseline.**
- ✅ **Prós:** **zero bundle** (modelo embarcado no Chrome), **multimodal** (`LanguageModel.create({ expectedInputs:[{type:'image'}] })` → `session.prompt({image, prompt:"Extraia o texto/identifique a roleta"})`), 100% on-device, e cobre nativamente o "capturar qualquer coisa que a gente definir".
- ❌ **Contras (bloqueantes p/ baseline):** exige **Chrome 137/138+** com **flags/origin trial**, **desktop-only**, **≥16GB RAM**, **>4GB VRAM** ou CPU forte, **~22GB de disco livre** (modelo 1.5–4GB baixado por **user-gesture**), e contexto ~6K tokens. Isso **quebra** o requisito "clonar e rodar em qualquer máquina da universidade".
- 🔧 **Como usar bem:** `await LanguageModel.availability()` → se `'available'`, ativa T3; senão, **nem tenta** e segue no T0/T1. Nunca tornar a feature dependente dele.

## 18. Tabela comparativa final (jun/2026)

| Motor/Modelo | Tamanho | Latência | Acurácia overlay | Roda em qualquer máquina | Veredito p/ este projeto |
|--------------|---------|----------|------------------|---------------------------|--------------------------|
| **ORT-Web (WASM) + PaddleOCR-lite** | <15MB | 10–30ms | Alta | ✅ | **★ Baseline (T0)** |
| **ORT-Web (WebGPU) + PaddleOCR/CNN** | <15MB | 5–15ms | Alta | ✅ (cai p/ WASM) | **★ Aceleração (T1)** |
| **Transformers.js v3 + Moondream2/SmolVLM** | 8–15MB | 200–500ms | Alta + VQA | ✅ | Opcional VQA (T2) |
| **Transformers.js + Florence-2** | 86–172MB | 100–500ms | Top + VQA | ⚠️ (pesado) | Evitar; só PoC de pesquisa |
| **Gemini Nano (Prompt API)** | 0MB (Chrome) | 100s ms–s | Alta + raciocínio | ❌ (16GB/22GB/flags) | Premium detectável (T3) |
| **Tesseract.js** | 2–5MB | 100–800ms | Média | ✅ | Fallback de emergência |

## 19. Fluxo do motor (pseudo-código da escada)

```js
// offscreen.js / worker — roda 1× por giro, com ROI já recortada
async function translateFrame(roiBitmap, fields) {
  const tier = await pickTier();           // detecta 1× e cacheia
  switch (tier) {
    case 'gemini-nano':  return geminiNano(roiBitmap, fields);      // T3
    case 'ort-webgpu':   return ortInfer(roiBitmap, 'webgpu');      // T1
    case 'transformers': return vlmInfer(roiBitmap, fields);        // T2 (flag)
    case 'ort-wasm':     return ortInfer(roiBitmap, 'wasm');        // T0
    default:             return tesseract(roiBitmap);               // fallback
  }
}
async function pickTier() {
  if (FLAGS.vlm) return 'transformers';
  if (await geminiAvailable()) return 'gemini-nano';
  if (navigator.gpu) return 'ort-webgpu';
  if (ortWasmReady) return 'ort-wasm';
  return 'tesseract';
}
```

## 20. Veredito do motor

- **Motor recomendado = ONNX Runtime Web** (WASM piso + WebGPU aceleração), com **PaddleOCR-lite + CNN** como tradutores — enxuto, universal, <30ms, **sem alterar a Engine Python**. ✅
- **Transformers.js v3** entra **só** para o tier VQA opcional (reusa o mesmo ORT-Web). **Gemini Nano** é tier premium **detectável**, jamais baseline. **Florence-2 está fora** do caminho de produção. ❌
- **Otimização real** vem de: event-driven + crop de ROI + warm-up + cache OPFS + fusão DOM-first — não de escolher o modelo "mais inteligente".

> **Próximo passo concreto (engine):** após o probe de DRM (§9.1), montar o T0 num offscreen mínimo — ORT-Web/WASM + um PaddleOCR-lite ONNX cacheado em OPFS — e medir acurácia do dealer vs DOM em ~30 giros. Se T0 empata/supera o DOM, está provado o motor; WebGPU/VLM/Gemini viram otimizações incrementais.

---
---

# 🧩 Parte 3 — Serviço isolado (microserviço + conector) acoplado à Escuta atual, com Chrome minimizado

> **Pedido:** auditar os últimos commits da Escuta (agora **pré-configurada, sem upload de JSON**), checar o que `passos_escuta_junho.md` ainda descreve na versão antiga, conferir os **padrões adotados** em `Manutenabilidade_iso.md`, e projetar o serviço de visão como **microserviço próprio + conector** que **funcione com o Chrome minimizado**, acoplado à extensão Escuta Beat.

## 21. Auditoria git — o que mudou (upload manual → zero-upload / auto-detect)

**Commit-pivô:** `23c3490 feat(escuta): auto-start + zero-upload na extensao (v3.3)` (entregue e deployado; backend Python v4.4.1 intacto).

| Antes (v3.2.0) | Agora (v3.3.x) | Onde |
|---|---|---|
| Upload **manual** de 1 JSON (`<input type=file>`) | **Manifests empacotados** servidos via `web_accessible_resources` + `chrome.runtime.getURL` (`loadBundledManifest`) | `extension/providers/{evolution,index}.json`, `background.js` |
| Provider escolhido à mão | **Auto-detecção por fingerprint ponderado** (URL/host dos frames) | `extension/provider_router.js` (`detectFromFrames`/`matchHostToProvider`/`PROVIDER_DETECTION`) |
| "Iniciar" manual | **Auto-start** via `webNavigation.onCompleted`/`onHistoryStateUpdated` → `maybeAutoStart` (+ boot-scan) | `background.js` |
| Sem catálogo | **Registry extensível**: novo provider = 1 entrada + 1 `providers/<id>.json` | `providers/index.json` |
| — | Supressão pós-STOP (TTL 24h + revalidação de host) | `background.js::suppressTab` |

**⚠️ Trechos DESATUALIZADOS em `passos_escuta_junho.md` (confirmado):**
- **§2 "Radiografia da arquitetura atual"** (L42-69) ainda rotula `CLIENT (Chrome Extension v3.2.0)` e `popup.loadExtractorFile() ← upload MANUAL de 1 JSON` como o **estado atual**.
- **§4.9.2 "De onde para onde"** (L544) ainda desenha `HOJE ► [upload manual do JSON]`.
- A realidade entregue está em **§12** ("Auto-Start & Zero-Upload — ENTREGUE, commit `23c3490`"). → **Recomendação:** marcar §2 e §4.9.2 como "estado pré-`23c3490`" e apontar para §12 (não reescrevi esses arquivos; só sinalizo o drift documental).

## 22. Padrões adotados (`Manutenabilidade_iso.md` ADENDO 14/06) que o novo serviço **herda**

O serviço de visão **deve replicar** os mesmos padrões que o ciclo zero-upload consagrou — não inventar outros:

1. **Config-driven + registry extensível** — comportamento vem de JSON versionado, não de código (precedente duplo: `provider_router.js::PROVIDER_DETECTION` no cliente e `server/extractor_service.py::_load_providers`/`detection.urlPatterns` no servidor).
2. **Fingerprint ponderado / determinístico** antes de ML (operável, debugável, sem treino).
3. **Self-heal por telemetria hit/miss** → promoção de fallback (NB-07); drift reportado como **hash/contagem, nunca conteúdo** (NB-10, privacidade).
4. **Distribuição OTA assinada** — **Ajv** (JSON Schema 2020-12) + **Ed25519** (tweetnacl) (NB-05).
5. **Consentimento** — automação só **lê**; apostar/operar exige clique (NB-02).
6. **Backend/Engine intacto** — todo o ciclo foi client-side; o Python (v4.4.1) não mudou. **O serviço de visão também não pode exigir mudança na Engine.**
7. **Detecção centralizada** (antes espalhada em `deal_capture.js`) — o serviço de visão deve ter **um** ponto de verdade de ROIs por provider.

> Scorecard ISO pós-ciclo: Usabilidade 8.6 · Manutenibilidade 8.7 · Confiabilidade 8.8 · geral 8.5/10. O novo serviço precisa **manter** esse nível: testes, idempotência, sem ampliar permissões/superfície.

## 23. Auditoria do requisito-chave: **funcionar com o Chrome minimizado** (a verdade dura)

Pesquisa técnica (jun/2026) — resultado que **redefine** o desenho:

| Método de captura | Janela **oculta/atrás** | Janela **MINIMIZADA** | Chrome? |
|---|:--:|:--:|:--:|
| `mss` / BitBlt (tela) | ✅ (mostra o que está na tela) | ❌ preto | ❌ |
| `pywin32` `PrintWindow` (PW_RENDERFULLCONTENT) | ⚠️ parcial | ❌ preto | ❌ |
| **Windows Graphics Capture (WGC)** / `windows-capture` | ✅ | ❌ **preto** (DWM não pinta minimizada) | ❌ |
| `chrome.tabs.captureVisibleTab` | ❌ (só aba ativa/visível) | ❌ | — |
| **`chrome.tabCapture` (modo tab) + flags anti-occlusion** | ✅ | ✅ **SIM** (pipeline interno do Chromium) | ✅ |
| **Chrome headless via CDP (Puppeteer/Playwright)** | ✅ | ✅ (não existe "minimizar") | ✅ |

**Conclusões duras:**
- **Nenhuma API de SO captura uma janela Chrome MINIMIZADA** — limite do DWM/compositor (a janela deixa de ser pintada). Um microserviço externo capturando por WGC/PrintWindow **falha** no minimizado.
- **A captura PRECISA nascer dentro do Chromium**: `chrome.tabCapture` (em offscreen document) **continua entregando frames mesmo minimizado**, desde que o Chrome seja iniciado com **flags anti-occlusion** e a captura comece **antes** de minimizar.
- Alternativa 100% à prova de minimizado: **Chrome headless controlado pelo microserviço** (CDP) — mas aí a sessão do cassino vive no browser do serviço, não no Chrome do operador.

## 24. Arquitetura recomendada — **split de responsabilidades**

A captura fica onde **tem** que ficar (dentro do Chrome, p/ sobreviver ao minimizado); a IA sai para um microserviço local isolado.

```
 MÁQUINA DO OPERADOR (localhost)                                    SERVIDOR REMOTO
┌──────────────── Chrome (flags anti-occlusion) ───────────────┐
│  Escuta Beat (extensão atual)                                │
│   • detecta giro via DOM  ──(gatilho: newHash!=lastHash)──┐  │
│   • OFFSCREEN: chrome.tabCapture (sobrevive minimizado)   │  │
│        └─ crop de ROI (faixa dealer/mesa/status)          │  │
└───────────────────────────────┬──────────────────────────┘  │
                 CONECTOR (localhost WS  ws://127.0.0.1:8799    │
                 ou Native Messaging — frames NUNCA saem do PC) │
                                 ▼                              │
┌──────────── services/vision (microserviço LOCAL próprio) ────┐│
│  ONNX Runtime NATIVE (DirectML/CUDA/CPU)                     ││
│   • PaddleOCR-lite  → dealer/mesa/round (texto)             ││
│   • CNN pequena     → modelo da roleta (classe)            ││
│   • [VLM opcional]  → "qualquer coisa que definirmos"      ││
│  ROIs config-driven (rois/<provider>.json + index.json)    ││
└───────────────────────────────┬─────────────────────────────┘│
                                 ▼ JSON {dealer,wheel_model,conf,source:'vision'}
                    volta à extensão → FUSÃO DOM-first          │
                                 │                              ▼
                                 └──► WS novo_resultado ─► Engine Python (INTACTA)
                                      (wss://roleta.xma-ia.com/ws)  cw/ccw.spin_features
```

**Por que assim (3 requisitos atendidos):**
- **Isolado/acoplável** → microserviço com escopo próprio (`services/vision/`), deps/testes/Dockerfile próprios; a extensão só ganha um **conector** fino.
- **Funciona minimizado** → a captura é `tabCapture` interna (+flags); o microserviço nunca tenta capturar a janela do SO.
- **Acoplado à Escuta atual** → a extensão continua sendo o **relógio** (detecta o giro) e a **câmera** (offscreen); o microserviço é só o **tradutor** pixel→JSON.
- **Resolve o risco da Parte 2** (WebGPU em offscreen "não-garantido"): a IA agora roda **nativa** (ONNX Runtime + DirectML), mais rápida e sem depender de WebGPU no browser. O ORT-Web in-browser (Parte 2) vira **fallback** quando o microserviço não está instalado.
- **Topologia:** o microserviço é **companion LOCAL** (na máquina do operador, ao lado do Chrome) — **não** vai para o servidor Debian. Frames ficam em `localhost` (privacidade NB-10); a Engine remota só recebe o JSON, como hoje.

## 25. Tecnologia escolhida × descartada

| Camada | Escolha | Descartado | Por quê |
|---|---|---|---|
| **Captura** | `chrome.tabCapture` em **offscreen** + flags anti-occlusion | WGC/PrintWindow externo; `captureVisibleTab` | Únicos que sobrevivem ao **minimizado** = pipeline interno do Chromium |
| **Conector** | **localhost WebSocket** (`ws://127.0.0.1`) — reusa o padrão WS já existente | Native Messaging (alternativa hardened) | Zero-setup (sem registrar host no registro do Windows); reusa código WS. NM fica como opção "sem porta aberta" |
| **Motor de IA** | **ONNX Runtime nativo** (DirectML p/ qualquer GPU Windows; CPU fallback) + PaddleOCR-lite/CNN | Florence-2/VLM como baseline; WebGPU em offscreen | Nativo é mais rápido, GPU universal via DirectML, modelos fora do git, sem risco offscreen |
| **Runtime do serviço** | **Python** (websockets/FastAPI) — alinha com a Engine e o `extractor_service.py` | Node/Electron, Go | Reuso de stack/skills do projeto; `onnxruntime` + `paddleocr`/`opencv` maduros |
| **À prova de minimizado (plano B)** | Chrome **headless via CDP** (Playwright) no próprio serviço | — | Caso as flags anti-occlusion não bastem em algum ambiente |
| **Config de ROIs** | JSON versionado + registry + Ajv + Ed25519 (**= padrão §4.9**) | ROIs hardcoded | Herda o padrão zero-upload/self-heal já adotado |

## 26. Arquitetura de dados & git (escopo próprio)

**Layout no monorepo** (espelha o precedente `server/extractor_service.py`, mas como processo local separado):

```
services/vision/                      ← escopo próprio do microserviço
├── app/
│   ├── server.py                     # WS localhost (conector ⇄ serviço)
│   ├── engine.py                     # ONNX Runtime (DirectML/CPU) + pipelines
│   ├── pipelines/ ocr.py  classify.py  vqa.py
│   └── rois.py                       # carrega/valida ROIs (Ajv-like + Ed25519)
├── rois/
│   ├── index.json                    # registry (= providers/index.json)
│   └── evolution.json                # ROIs por provider (faixa dealer/mesa/status)
├── models/                           # .onnx — GIT LFS ou lazy-download (NUNCA blob no git)
├── schema/roi.schema.json            # JSON Schema 2020-12
├── tests/  Dockerfile  pyproject.toml  README.md
extension/
└── vision_connector.js              # lado offscreen: tabCapture→crop→WS localhost
```

**Arquitetura de dados (contrato — Engine intacta):**
- O serviço devolve `{ dealer:{text,conf}, table:{...}, wheel_model:{label,conf}, engine, infer_ms, roi_version }` (schema da §15).
- A extensão **funde DOM-first** e injeta `vision_*` (opcionais) no payload `novo_resultado` já existente → **retrocompatível, sem migração**.
- Reaproveita o esquema atual de dados: `cw/ccw.spin_features(provider,table,dealer,round_id)` e `shared.dealers UNIQUE(name,provider,table)` (radiografia §2 do `passos`). **A Engine permanece o único escritor do DB** (respeita o modelo singleton/ownership).
- **ROIs seguem o padrão zero-upload**: empacotadas, **Ajv**-validadas, **Ed25519**-assináveis, com **self-heal** (telemetria hit/miss de ROI → promove ROI fallback), igual aos seletores do §4.9 — só que para regiões de imagem.
- **Modelos fora do git** (LFS/lazy-download cacheado), conforme Parte 1.

## 27. Setup mínimo para o minimizado — flags de lançamento do Chrome

Para `tabCapture` continuar entregando frames minimizado, o Chrome do operador precisa subir com:

```
chrome.exe --disable-features=CalculateNativeWinOcclusion
           --disable-backgrounding-occluded-windows
           --disable-renderer-backgrounding
           --disable-background-timer-throttling
```

Entregar como **atalho/launcher** (o microserviço pode criar/oferecer o atalho no primeiro run) — é o **único** passo de setup, e é o que torna o "minimizado" viável. Iniciar a captura **antes** de minimizar.

## 28. Riscos & gates (específicos do serviço)

| Risco | Severidade | Mitigação |
|---|---|---|
| **DRM/EME** → vídeo preto (persiste da Parte 1) | 🚨 | Probe §9.1 **antes**; dealer/mesa são overlay HTML (capturáveis), modelo-da-roleta depende do vídeo |
| Operador abre Chrome **sem** as flags | Alta | Launcher/atalho dedicado; detectar e avisar; fallback degradado |
| `offscreen`+`tabCapture` ausentes no manifest | Média | Adicionar permissões (Fase 2); iniciar captura na aba ativa |
| Porta localhost exposta | Média | Bind em `127.0.0.1`, token por sessão, origem checada; ou **Native Messaging** (sem porta) |
| Captura iniciada **após** minimizar | Média | Garantir start no auto-start, antes de qualquer minimização |
| Setup do microserviço quebra "zero-setup" | Média | Distribuir como 1 binário/`pipx`/Docker; ROIs e modelos lazy; documentar |

## 29. Plano faseado + veredito

- **F0 (gate):** probe DRM (§9.1) + provar `tabCapture` minimizado com as flags (capturar 1 frame legível do dealer com o Chrome minimizado).
- **F1 (MVP):** offscreen `tabCapture`→crop→**localhost WS**→microserviço Python (ONNX Runtime CPU + PaddleOCR-lite) → `vision_dealer` fundido DOM-first. Medir vs DOM em ~30 giros.
- **F2:** CNN do **modelo da roleta** + DirectML (GPU) + ROIs config-driven com registry/Ajv.
- **F3:** self-heal de ROIs (hit/miss) + OTA Ed25519 + (opcional) Native Messaging + VLM sob flag.

**Veredito:**
- ✅ **Viável como microserviço + conector acoplado à Escuta** — desde que a **captura fique na extensão** (offscreen `tabCapture` + flags) e o **microserviço local** faça só a IA. Externalizar a captura para WGC/SO **não funciona minimizado**.
- ✅ **Herda os padrões adotados** (registry/config-driven, self-heal, Ajv/Ed25519, consentimento, **Engine intacta**) — consistência com o ciclo zero-upload de 14/06.
- 🔧 **Pré-condições:** flags anti-occlusion no Chrome (launcher), permissões `offscreen`+`tabCapture`, e o **gate DRM**.

> **Próximo passo único:** F0 — abrir a mesa, **minimizar o Chrome** iniciado com as 4 flags, e confirmar que o offscreen `tabCapture` ainda entrega um frame com o **nome do dealer legível** (e checar se a área do vídeo não vem preta por DRM). Esse teste de 1 dia valida (ou derruba) toda a Parte 3.

---
---

# 🗄️ Parte 4 — Arquitetura de dados: foto → dados → decisão

> **Perguntas:** a ferramenta está alinhada com "fotos viram dados"? Como é a absorção em banco? Será um banco específico? Como ficou a infra de arquitetura de dados? Como os dados ficam disponíveis para os bancos/estratégias tomadores de decisão?
> **Resposta fundamentada no código real (verificado 19/06).**

## 35. A arquitetura de dados REAL (verificada no código)

```
[1] PRODUTOR (extensão)  novo_resultado {numero, direcao, dealer, table, provider, round_id}
        │                 ← AQUI a visão ENRIQUECE: + wheel_model + vision_* + confidence + source
        ▼
[2] ENGINE (escritor ÚNICO)  server/message_handler.handle_new_result → GameState singleton
        ▼
[3] SOURCE OF TRUTH (local)  SQLite  data/decisions.db
        │   save_decision() → decisions(dealer, dealer_table, provider, round_id, sda_*, result_region, pnl_units)
        │   auto-migra via ALTER TABLE ADD COLUMN idempotente (sqlite_repo.py:334-344)
        ▼
[4] OUTBOX / CDC (desacoplado, opcional)  maybe_publish_spin_result → outbox → cdc_worker
        │   dual_write_pg default OFF (SQLite basta em prod; PG é analítico)
        ▼
[5] FEATURE STORE (Postgres, analítico)
        │   cw/ccw.spin_features (0006) + dealer/table/provider/round_id (0007)
        │   shared.dealers UNIQUE(name,provider,table) (0007)
        │   shared.decision_dna + view dna_summary (0008): estimated/realized lift + confidence_n
        ▼
[6] CONSUMIDORES (tomadores de decisão)
        dealer_offset (offset modal por dealer) · dealer_stats (hit_rate) ·
        bet_advisor (lê spin_features) · region_bandit (dormente) · /api/dna_summary
```

| Camada | Papel | Evidência |
|---|---|---|
| Produtor | extensão emite `novo_resultado` com metadados | `background.js:1586-1599` |
| Engine | escritor único, agnóstico | `server/message_handler.py` (GameState singleton) |
| Source of truth | **SQLite** `decisions` (dealer/table/provider/round_id) | `sqlite_repo.py:334-344, 377-432` |
| Outbox/CDC | publica spin_result p/ PG (opt-in) | `message_handler.py:551-553`, `database/outbox_integration.py` |
| Feature store | **Postgres** `cw/ccw.spin_features`, `shared.dealers`, `decision_dna` | migrations `0006/0007/0008` |
| Consumidores | estratégias leem features por dealer/table | `strategies/dealer_offset.py`, `sqlite_repo.dealer_stats` |

## 36. Está alinhada com "foto → dados"? **SIM — a visão é ENRIQUECEDORA do produtor**

A visão **não cria um pipeline/banco novo**: por design (Partes 1-3) ela entra na **camada [1] (produtor)**. A foto vira `{dealer, wheel_model, …}` **fundido DOM-first** no **mesmo** `novo_resultado`, com `vision_*` + `confidence` + `source`. A Engine continua **escritor único**. Os campos `dealer/table/round` **já têm coluna e consumidores hoje** (fluem via DOM, sem foto) — a visão apenas os preenche de forma mais robusta **e adiciona `wheel_model`**.

## 37. Como é a absorção em banco (hoje e com a visão)

- **Hoje:** `dealer/table/provider/round_id` são absorvidos por `save_decision` → **SQLite `decisions` (SoT)** → outbox/CDC → **PG `spin_features` + `shared.dealers`**. A visão usa **exatamente essa absorção** — zero rework de parser/DB para os campos existentes.
- **`wheel_model` é NOVO:** precisa de **coluna** (migração **aditiva**, igual ao SP-13 que adicionou `dealer`): `ALTER TABLE decisions ADD COLUMN wheel_model TEXT` no SQLite + migration PG em `spin_features`/`shared.tables`. Antes disso, pode trafegar no `meta JSONB` como ponte.

## 38. Será um banco específico? **NÃO — reuso + separação de responsabilidades**

| Tipo de dado | Onde mora | Por quê |
|---|---|---|
| Campos **estruturados de decisão** (dealer, wheel_model, confidence) | stores **existentes** (SQLite SoT + PG feature store) | um banco separado quebraria o modelo **escritor-único/replay** e a rastreabilidade |
| **Frames/imagens brutos** + telemetria ML pesada | **LOCAIS** na máquina do operador (arquivos/OPFS), **nunca** no DB central | privacidade **NB-10** (frame não sai do PC) + mantém o DB enxuto |
| **Catálogo do modelo da roleta** | `shared.tables`/`shared.manifests` (**Sprint 3**) | `wheel_model` por `canonical_id` → replay e analytics por mesa/modelo |

Ou seja: **não** um banco novo para a decisão; **sim** uma fronteira clara — pixels ficam no cliente, **só o dado estruturado destilado** entra no DB.

## 39. Como os dados ficam disponíveis para os tomadores de decisão

Os dados viram **disponíveis** porque são persistidos como **features keyed por `dealer`/`table`/(futuro)`wheel_model`** — exatamente o que as estratégias já consultam: `dealer_offset` (offset modal por dealer), `dealer_stats` (ranking por hit_rate), `bet_advisor` (lê `spin_features`), `dna_summary`.

Para **`wheel_model` virar decisão-disponível**:
1. **Persistir** como coluna em `decisions` + `spin_features` (migração aditiva).
2. **Etiquetar `confidence` + `source`** — a estratégia **decide se confia** (gate por confiança, como o `score≥4` já faz no stake).
3. **Flag default OFF** (mesmo contrato dos demais ciclos).
4. **Consumidor**: um `wheel_offset` análogo ao `dealer_offset` (offset preferido por modelo de roleta, n≥30).

O padrão **`decision_dna`** (estimated vs realized lift + `confidence_n`, migration 0008) é o **template para medir se a feature de visão dá lift de verdade ANTES de confiar** — fecha o loop "dado disponível → decisão informada → mensurada".

## 40. Status honesto + próximo passo

- ✅ **Caminho de dados: EXISTE e está PROVADO** — `dealer` flui hoje via DOM (sem foto) e já alimenta `dealer_offset`.
- ⚠️ **Vision engine: DESIGN** (Partes 1-3), **não implementado**. O `selector_health.js` (§13) é **resiliência de seletor**, não visão.
- 🔧 **Gap:** `wheel_model`/`vision_confidence` **sem coluna** → migração aditiva (SQLite ALTER + PG) + fusão `vision_*` no `message_handler`, atrás de flag.
- **Próximo passo concreto:** (1) **probe DRM** (Parte 3, F0); (2) **migração aditiva** `wheel_model`/`vision_confidence` (mesmo padrão SP-13); (3) **consumidor `wheel_offset`** análogo ao `dealer_offset`, gated por `confidence`.

> **Resumo de 1 linha:** a infra de dados **já está alinhada e pronta para receber a visão como enriquecedora do produtor**, reusando SQLite(SoT)+PG(feature store) — sem banco novo; falta só a **migração aditiva de `wheel_model`/`confidence`** e o **consumidor por modelo**, pois o motor de visão em si ainda é design (Partes 1-3).

---
---

# ✅ Parte 5 — MVP de visão IMPLEMENTADO e DEPLOYADO (foto→dados funcionando)

> Status: **VIVO EM PRODUÇÃO** (commit `dce10af`). OCR provado no container de produção:
> extraiu `'Dealer Carlos'` de uma imagem real em ~1.8s. `vision_ocr.is_available()=True`.

## 36. O que foi entregue (pipeline real, não design)

```
[Extensão] novo número (DOM) → captureVisibleTab (1 frame jpeg) ──WS foto_frame──▶
[Servidor] handle_foto_frame → vision_ocr.extract (RapidOCR / PaddleOCR-ONNX)
           → {dealer, wheel_model, confidence, texts} ──WS foto_resultado──▶
[Extensão] loga "📸 Foto→dados: dealer=… roleta=… (conf %)"
```

| Camada | Implementação | Arquivo |
|---|---|---|
| Captura | `captureAndSendFrame`: `chrome.tabs.captureVisibleTab` (jpeg q60), 1/giro, flag `fotoCapturePolicy` (default on), defensivo | `extension/background.js` |
| Transporte | msg `foto_frame {trace_id, image}`; resposta `foto_resultado` | `extension/background.js` |
| **Motor OCR** | `RapidOCR` (PaddleOCR-ONNX, CPU, self-contained) → decode base64 + ROI + extrai dealer/wheel/confidence; singleton lazy; degradação graciosa; flag `SDA_VISION_OCR` | `server/vision_ocr.py` |
| Handler | `handle_foto_frame`: OCR em `asyncio.to_thread` (não bloqueia loop) → responde | `server/message_handler.py` |
| Deps | `rapidocr-onnxruntime` + `numpy<2`; Dockerfile: libs de runtime do opencv | `requirements.txt`, `Dockerfile` |
| Testes | 6 (gera imagem PIL → OCR extrai 'Maria'/'Lightning' + ROI + flags) | `tests/test_vision_ocr.py` |

## 37. ⚠️ Gotcha crítico resolvido — NumPy 2.x × CPU QEMU antigo

O servidor de produção é um **`QEMU Virtual CPU 2.5+`** sem `x86-64-v2`. O **NumPy 2.x exige v2** → `RuntimeError` no import, derrubando opencv+onnxruntime (OCR caía em `is_available()=False`, mas o server **não quebrou** graças à degradação graciosa). **Fix: `numpy>=1.26,<2`** (baseline SSE2). Validado em `python:3.12-slim` antes do deploy. **Lição durável:** qualquer dep nativa pesada neste servidor precisa de wheels baseline (sem v2).

## 38. Evidências de produção

- ✅ `vision_ocr.is_available() = True` no container `roleta-cloud`.
- ✅ **Teste ponta-a-ponta em produção (WebSocket real)**: enviado `foto_frame` com imagem de teste → resposta `foto_resultado` `ok=True, dealer='Mariana', provider='evolution', wheel='Lightning', conf=0.99, ms=2735`.
- ✅ **Persistência confirmada no DB de produção**: linha em `decisions` com `dealer=Mariana, provider=evolution, wheel_model=Lightning, vision_source=vision, vision_confidence=0.9879`.
- ✅ **Os 3 campos (dealer + provider + modelo da roleta) vêm da FOTO** (sem DOM): provider por marca direta (evolution/pragmatic/playtech…) **ou** inferido pelo nome da mesa (lightning/immersive→evolution, mega→pragmatic).
- ✅ `ALEMBIC ok (0009 head)`, container healthy, `/health=ok`.
- ✅ Suíte local **607 passed**.

## 39. Como usar (operador)

1. **Servidor**: já no ar (OCR habilitado por default; `SDA_VISION_OCR=0` desliga).
2. **Extensão**: recarregar **"Escuta Beat" v3.4.0** em `chrome://extensions` (client-side não vai por docker).
3. Abrir a mesa e escutar normalmente. A cada giro, a Escuta tira 1 foto e o servidor faz OCR; o resultado aparece nos **logs da Escuta** (`📸 Foto→dados: dealer=… roleta=…`).
4. Desligar a captura: `chrome.storage.local` → `fotoCapturePolicy='off'`.

## 40. Limites honestos (MVP) e evolução

- **DRM**: se a área do vídeo for protegida (Widevine), vem preta — o **dealer/mesa** (overlay HTML) tende a aparecer; o **modelo físico da roleta** depende do vídeo (probe DRM da Parte 3 ainda vale).
- **captureVisibleTab**: só captura a aba **ativa/visível** (não cobre minimizado — esse é o caminho `tabCapture`+offscreen das Partes 1-3, evolução futura).
- **Latência**: ~1.8s/foto no CPU QEMU (sem AVX); ok para 1 giro/min. A arquitetura ideal client-side (ONNX/WebGPU no offscreen, Partes 1-3) elimina o transporte de imagem — evolução.
- **Parsing**: heurística leve (regex dealer + keywords de modelo); afinar com ROIs por provider (`SDA_VISION_WHEEL_KEYWORDS`).
- **Persistência**: os campos `vision_*` já existem (Parte 4); o passo seguinte é o cliente **dobrar** o resultado do OCR no `novo_resultado` para gravar no DB e criar um consumidor `wheel_offset`.
