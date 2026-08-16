# Auditoria UX sênior do front — Glass Box · Popup · Overlay Escuta Beat (SPR-U1)

> **Data:** 2026-08-16 · **Escopo:** `frontend/` (dashboard Glass Box), `extension/popup.*`,
> `extension/content.js` + `extension/overlay.css` (overlay expandido, minimizado e seção de
> controle), com leituras dirigidas em `extension/background.js` para validar jornadas.
> **Método:** walkthrough dirigido por código (100% dos elementos interativos), matriz de
> estados, sonda read-only no servidor público (incidente `/ws` 502 REAL durante a auditoria)
> e heurísticas de Nielsen/Fitts/contraste. **Zero mudança de código** — todo bug vai para a
> tabela de achados.

---

## 1. Sumário executivo

1. **O sistema mente sobre a conexão durante o jogo.** Com o servidor fora (502 verificado
   hoje: nginx de pé, `/ws` 502), o overlay minimizado — a superfície primária de jogo —
   mostra os últimos centros/gale congelados **sem nenhum sinal de erro**; o expandido pode
   ficar em "Conectando..." para sempre; o popup exibe "✅ CONECTADO" (que significa "há uma
   aba aberta", não servidor); e `startListening` responde sucesso e liga o badge verde
   mesmo sem servidor, descartando silenciosamente cada leitura. O operador joga com
   sugestão velha acreditando que o sistema opera (achados OV-01, PP-01, BG-01 — P0/P1).
2. **Desktop é cidadão de segunda classe no overlay:** drag só funciona por touch — o
   operador (desktop) não consegue mover o painel que cobre a mesa (OV-02, P1).
3. **A grade de resultados do painel de controle esconde os 2 números mais recentes**
   (`slice(-10)` sobre array newest-first) e diverge do popup (MN-01, P1).
4. **O dashboard não tem backoff** (5s fixo, variável de tentativas morta) — tempestade de
   reconexão e log 100% poluído em ~80s de queda; a extensão já resolveu isso no SPR-V2 e o
   padrão está pronto para ser espelhado (GB-01/GB-03).
5. Suspeitas do Diretor: **todas confirmadas** exceto duas — zonas mortas de clique
   (verificado OK) e reconexão da extensão (verificado OK, backoff+jitter+teto). O formato
   único do minimizado segurou (3 writers usam o mesmo helper), mas há divergência de
   *dados* em edge-cases (MN-02/MN-03).
6. Decisão do SPR-X5 (racetrack abaixo dos centros no minimizado): **confirmada**, com 4
   refinamentos v2 não-bloqueantes (§6).

---

## 2. Inventário 100% dos elementos interativos (checklist)

### 2.1 Glass Box (`frontend/index.html` + `app.js` + `style.css`)

| ✔ | Elemento | Tipo | O que faz | Estados | Feedback | Falhas observadas |
|---|---|---|---|---|---|---|
| ✔ | Pill status `#status-indicator` | passivo | ONLINE/OFFLINE do WS | `online`/`offline` | cor de fundo/texto | glifo ⚫ idêntico nos 2 estados (GB-02) |
| ✔ | `#latency` header | passivo | latência do último trace | número/`--ms` | texto | congela após desconexão (GB-04) |
| ✔ | Fluxo Escuta→Servidor→SDA→Overlay (4 nós + 3 setas) | passivo animado | animação da cadeia por spin | `active`/`success`/reset | borda azul pulsante → verde | `.flow-status` sempre `--` — elemento morto (GB-08) |
| ✔ | Card Último Spin | passivo | número/direção/força/latência | valor ou `--` | texto | sem sinal de stale (GB-04) |
| ✔ | Card Resultado (ação, veredito, par, centro, score, região) | passivo | decisão da estratégia | `apostar`/`pular` (borda) | verde/laranja + veredito red/green | score com denominador `/6` hardcoded (GB-11) |
| ✔ | Card 3 Regiões (`#f17-body`, cobertura, bias) | passivo | centros force17/V5 + badge 17/21 | populado/aguardando | cores por label, badge dourado | innerHTML sem escape (GB-06) |
| ✔ | Timeline CW/CCW (2 barras) | passivo | forças acumuladas | largura 0–100% | animação width | — |
| ✔ | Métricas (Spins/APOSTAR/PULAR/Taxa) | passivo | contadores da sessão do dashboard | números | — | risco de contagem dupla trace×sugestao (GB-05) |
| ✔ | Estratégia + Martingale CW/CCW | passivo | nome/desc/trend + gale/aposta por direção | `G1..G3` | classe `level-N` | valores congelam offline (GB-04) |
| ✔ | Performance SDA17 (2×12 quadrados) | passivo | hits/misses base | `hit`/`miss`/`empty` | verde/vermelho | — |
| ✔ | Performance Apostas (2×12 quadrados) | passivo | hits/misses de aposta real | idem | idem | — |
| ✔ | Histórico de Janelas | passivo | janelas martingale por direção | `active`/`success`/`stop`/`escalated` | borda esquerda + dots | tooltip via `title` com payload (GB-06) |
| ✔ | Trace (`#trace-steps`) | passivo | passos do pipeline | populado/aguardando | monospace | innerHTML com `step.name`/`step.data` (GB-06) |
| ✔ | **Filtros de log ×4** (`Todos/Spin/Resultado/Erro`) | **botão** | filtra `state.logs` | `active` | fundo azul | contador mostra total, não o filtrado (GB-09) |
| ✔ | Logs container | passivo | últimos 50 eventos | por tipo | cor por tipo | spam de reconexão domina em ~80s (GB-03) |
| ✔ | Footer (URL WS + last update) | passivo | endereço + timestamp | — | — | URL duplicada no HTML e no JS (GB-10) |

*Únicos elementos interativos do dashboard: os 4 botões de filtro. Todo o resto é display.*

### 2.2 Popup (`extension/popup.html` + `popup.js`)

| ✔ | Elemento | Tipo | O que faz | Estados | Feedback | Falhas observadas |
|---|---|---|---|---|---|---|
| ✔ | LED `#indicator` + status/URL | passivo | status **da aba ativa** (não do servidor!) | `connected`/`listening`/`error` | verde/azul pulsante/vermelho | "✅ CONECTADO" ambíguo — não é o servidor (PP-01) |
| ✔ | Toggle **Auto-start** | checkbox | política auto/off no background | checked/uncheck | log | — |
| ✔ | Status auto-detecção | passivo | provider detectado + confiança | detectando/ok/nenhum | texto | funciona offline (detecção é local) — reforça PP-01 |
| ✔ | **Dropdown mesa** | select | pede config da mesa ao servidor | vazio/carregando/erro | opções | rebuild via broadcast perde seleção atual (PP-06) |
| ✔ | **📸 Capturar** | botão | captura DOM → servidor | normal/⏳/disabled | ícone | preso em ⏳ para sempre se servidor não responder (PP-03) |
| ✔ | **📂 Carregar arquivo** | botão | manifest manual (fallback) | normal/⏳/disabled | texto | cancel do picker pode deixar ⏳ (PP-07) |
| ✔ | **▶️ INICIAR ESCUTA** | botão | comando startListening | enabled/disabled | log | continua visível E habilitado durante escuta (PP-02) |
| ✔ | **⏹️ PARAR ESCUTA** | botão | comando stopListening | show/hide | log | — |
| ✔ | **📋 EXPORTAR LOGS** | botão | baixa JSON de logs | — | log | posicionado ACIMA do painel de operação (PP-04) |
| ✔ | **⬅️ HORÁRIO / ➡️ ANTI-HORÁRIO** | 2 botões | âncora manual de direção | ativo azul/laranja | pintura imediata | ícones/cores divergem das outras superfícies (PP-05) |
| ✔ | Semáforo (PODE APOSTAR/FECHADO/AGUARDANDO) | passivo | status do jogo lido da mesa | open/closed/waiting | verde/vermelho/amarelo | — |
| ✔ | Saldo / Na mesa / Ficha ativa | passivo | financeiro lido da mesa | valores/default | BRL formatado | congela sem sinal de stale ao parar |
| ✔ | Grade 12 resultados | passivo | últimos números + seta de direção | cores roleta + `new` | animação | newest-first correto (diverge do painel de controle — MN-01) |
| ✔ | Info (mesa ativa/último/total) | passivo | metadados da escuta | — | — | — |
| ✔ | Painel DIR20 (descartes/streak/re-baselines/flips/motivo/frame/versão) | passivo | telemetria da perda (SPR-V2) | streak>0 pinta laranja | cor | boa prática — candidato a espelhar no overlay |
| ✔ | Log (30 entradas) | passivo | eventos do popup | por tipo | cor | — |

### 2.3 Overlay expandido (`extension/content.js` + `overlay.css`)

| ✔ | Elemento | Tipo | O que faz | Estados | Feedback | Falhas observadas |
|---|---|---|---|---|---|---|
| ✔ | Pill `.eb-status` (header) | passivo | ação atual | `apostar`/`pular`/`aguardando` + `g1/g2/g3` | cor + texto | classes g1/g2/g3 sobrepõem a cor da ação (OV-03) |
| ✔ | Role `#eb-role` ⚡/👑/👁️ | passivo (title no hover) | master/slave/desconhecido | 3 estados | emoji+cor+tooltip | tooltip inacessível no touch |
| ✔ | **🔄 Nova Sessão** | botão | reset de dealer no servidor | hover gira | `confirm()` + status | destrutivo a 6px do minimizar, 24px (OV-08); `confirm()` bloqueia página (OV-09) |
| ✔ | **🎯 Forçar MASTER** | botão (só slave) | toma o papel master | show/hide | `confirm()` | idem OV-09 |
| ✔ | **− Minimizar** | botão | alterna minimizado | rotate 180° | persiste em storage | pós-reset, 1º clique parece não funcionar (OV-05) |
| ✔ | Último (`#eb-ultimo`) | passivo | último número | valor/`--` | — | — |
| ✔ | Região (`#eb-regiao`) | passivo | 3 centros + rótulos + 17/21 números + badge | apostar/pular/aguardando | verde GO / laranja / — | AGUARDANDO herda a caixa VERDE-GO (OV-04); innerHTML payload (OV-06) |
| ✔ | Veredito (`#eb-veredito`) | passivo | 🟢/🔴 + sentido + nº | green/red/vazio | cor | — |
| ✔ | Gale (`#eb-gale-display`) | passivo | `GN hits/count` | g1/g2/g3 | verde/dourado/azul | — |
| ✔ | Aposta (R$ `#eb-aposta`) | passivo | valor sugerido | número | — | — |
| ✔ | Barra de confiança | passivo | 0–100% | width | animação | — |
| ✔ | Timer (`#eb-timer`) | passivo | conexão/sync/última atualização | textos diversos | cor | "Conectando..." eterno sem servidor; sobrescrito por "🟡 Aguardando aposta" (OV-01) |
| ✔ | **🎛️ Controles** | botão | expande seção de controle | texto alterna | — | — |
| ✔ | **Drag do painel** | gesto | move o overlay | — | posição | só touch, sem mouse; sem clamp inferior (OV-02) |

### 2.4 Seção de controle (dentro do overlay) + minimizado

| ✔ | Elemento | Tipo | O que faz | Estados | Feedback | Falhas observadas |
|---|---|---|---|---|---|---|
| ✔ | LED `#eb-ctrl-indicator` + texto + URL | passivo | **status real do WS do servidor** | vermelho/amarelo(`connected`)/verde-pulsante(`listening`) | cor | única superfície com o status verdadeiro do servidor — mas escondida atrás do 🎛️ |
| ✔ | **Select mesa** + **📸** | select+botão | config/captura | disabled durante ⏳ | ícone | restaura seleção corretamente (contraste com PP-06) |
| ✔ | **▶️ INICIAR / ⏹️ PARAR** | botões | start/stop escuta | disabled por `isListening` | opacidade | fluxo com captura automática e timeout de 3s — razoável |
| ✔ | Grade últimos resultados | passivo | 10 números coloridos | — | cores roleta | **mostra os 10 mais antigos, esconde os 2 mais recentes** (MN-01) |
| ✔ | Timestamp última leitura | passivo | hora | — | — | usa `new Date()` quando falta `lastUpdate` — inventa frescor |
| ✔ | **Pill minimizado** `[C2] [C3] [C1]` + badge 17/21 + gale | passivo | resumo de jogo | cor por gale | formato único (helper) | congelado sem sinal de erro quando servidor cai (OV-01); heartbeat só atualiza com `bet_placed` (MN-03) |
| ✔ | − (vira ∠180°) no minimizado | botão | expande | — | — | — |
| ✔ | Drag no minimizado | gesto | move | — | — | idem OV-02 |
| ✔ | Reaparecimento (`showOverlay`/`hideOverlay` via background) | mensagem | mostra/esconde | `isVisible` | display | sem atalho para o operador reexibir se sumir |

**Zonas mortas de clique (suspeita do Diretor): VERIFICADO OK.** `pointer-events: none` no
contêiner raiz (`overlay.css:13`) + `auto` apenas no `.eb-panel` (`overlay.css:28`); o
contêiner não tem dimensão própria além do painel, então cliques fora do painel atravessam
para a página (trocar aba da mesa funciona). Sem zona morta encontrada por código.

---

## 3. Matriz de estados

Dimensões: **ação** {AGUARDANDO, APOSTAR, PULAR} × **vista** {expandido, minimizado} ×
**conexão** {conectado, desconectado, reconectando} × **cache** {com/sem sugestão}.
Células marcadas ⚠️ = a informação **mente** ou está ausente.

### 3.1 Conectado (state_sync fluindo a ~1s)

| Ação × Cache | Expandido | Minimizado |
|---|---|---|
| APOSTAR (com sugestão) | pill verde "🎯 APOSTAR", região verde com 3 centros+rótulos+badge+números, beep, timer "🟢 Sincronizado"/"🟡 Aguardando aposta" | `[C2][C3][C1]` + badge + gale, cor por gale ✔ |
| PULAR (com sugestão) | pill "⏸️ PULAR" ⚠️ *pintada da cor do gale, não laranja* (OV-03), região laranja "Sem entrada" | pill continua mostrando centros do último APOSTAR + gale ⚠️ *sem indicação de PULAR no minimizado* — operador precisa confiar que não deve clicar |
| AGUARDANDO (sem sugestão) | pill "⏳ AGUARDANDO" ⚠️ *verde por herdar `g1`* (OV-03), região "Aguardando..." ⚠️ *em caixa VERDE-GO* (OV-04) | pill "⏳ AGUARDANDO" (sem centros) ✔ |
| AGUARDANDO (com cache de reload) | atualiza na 1ª sugestão | ⚠️ até a 1ª sugestão/state_sync com `bet_placed`, mostra "⏳ AGUARDANDO" mesmo havendo predição pendente (mitigado pelo cold-start via `data.regioes`, content.js:917-921; resíduo MN-03/MN-06) |

### 3.2 Desconectado (servidor caiu DEPOIS de conectado)

| Ação × Cache | Expandido | Minimizado |
|---|---|---|
| Qualquer (com sugestão em cache) | timer "🔴 Desconectado" (se `state.tabId` existe), **resto do painel congelado**: centros, gale, aposta, confiança seguem exibidos ⚠️ *sugestão velha parece atual* | ⚠️⚠️ **NADA muda** — `eb-timer` tem `display:none` no minimizado (overlay.css:280-284); pill mostra centros/gale congelados, indistinguível de "conectado sem giro novo" (OV-01, **P0**) |
| Sem sugestão | timer "🔴 Desconectado", região "Aguardando dados..." | pill "⏳ AGUARDANDO" ⚠️ idêntico ao estado conectado-sem-sugestão |

### 3.3 Reconectando / nunca conectou (caso REAL de hoje: `/ws` 502)

| Superfície | O que o usuário vê | Mentira/lacuna |
|---|---|---|
| Overlay (escuta nunca iniciada) | "⏳ AGUARDANDO" + "Conectando..." **para sempre** | ⚠️ `notifyConnectionStatus` exige `state.tabId` (background.js:1128-1137) — sem escuta iniciada o overlay nunca fica sabendo do erro |
| Overlay (escuta iniciada com servidor fora) | broadcast `stateSync {isListening:true}` escreve "🟡 Aguardando aposta" **por cima** de qualquer "🔴 Desconectado" (background.js:1528 → content.js:934-939) | ⚠️ o texto de *sync* aparece sem haver servidor |
| Extensão entre tentativas de reconexão | igual a desconectado | ⚠️ não existe representação de "reconectando" (tentativa N, próxima em Xs) em NENHUMA superfície — a telemetria existe (`wsReconnectAttempts` em `chrome.storage.session`) e não é exibida |
| Popup | LED verde "✅ CONECTADO" (é a ABA!) + "Sem mesas (servidor offline?)" + auto-detecção funcionando | ⚠️ dois sinais contraditórios lado a lado (PP-01) |
| Dashboard | pill "⚫ OFFLINE" vermelho ✔ + log com 3 entradas/5s de erro | ⚠️ em ~80s as 50 linhas do log são só spam de reconexão (GB-03); sem backoff (GB-01) |

### 3.4 Jornada "servidor fora" de ponta a ponta (verificada com sonda real durante a auditoria)

Sonda 16/08: `GET /health → 404` (nginx 1.22.1 respondendo; backend fora do ar),
`GET /ws → 502`. Ou seja: TLS/nginx OK, upstream morto — exatamente o cenário desta jornada.

1. **Operador abre a mesa** → content script cria o overlay: "⏳ AGUARDANDO" + região
   "Aguardando dados..." + timer "Conectando..." (content.js:150-183). Auto-start detecta o
   provider e dispara `startListening`.
2. **Background liga tudo sem checar o servidor**: `isListening=true`, alarms, badge verde
   `●`, resposta `{success:true}` (background.js:1503-1531). `connectWebSocket()` recebe 502
   no handshake → `onclose` → backoff exponencial (correto, background.js:989-1012). Cada
   leitura da mesa vira `sendToWebSocket(...)` que retorna `false` e **descarta o giro
   silenciosamente** (background.js:1014-1019).
3. **O que cada superfície diz**: popup "✅ CONECTADO" + "👂 ESCUTANDO..." + grade de números
   atualizando (leitura local funciona!); overlay minimizado com pill normal; dashboard
   OFFLINE. **Só** o LED da seção de controle (atrás do 🎛️) e o dashboard dizem a verdade.
4. **Operador tenta capturar mesa** → 📸 vira ⏳; `capturarMesaRemota` responde
   `{success:true}` mesmo com WS caído (background.js:1222-1228); popup loga "✅ Captura
   enviada para o servidor!"; `mesaConfigurada` nunca chega; **📸 fica ⏳ para sempre**
   (popup.js:149-155 é o único caminho que restaura) (PP-03).
5. **Servidor volta** → extensão reconecta com backoff+jitter ✔ (sem tempestade);
   dashboard reconecta na próxima janela de 5s (todos os clientes juntos — GB-01).
6. **Conclusão**: a perda é invisível no caminho feliz do operador. Propostas concretas na
   tabela (OV-01, PP-01, PP-03, BG-01) e no sprint candidato §7.1.

---

## 4. Tabela de achados

Severidade: **P0** = induz decisão errada com dinheiro em jogo · **P1** = função principal
quebrada/informação mente · **P2** = robustez/UX relevante · **P3** = polimento/dívida.

| ID | Sev | Superfície | Evidência (arquivo:linha) | Sintoma | Proposta |
|---|---|---|---|---|---|
| OV-01 | **P0** | Overlay (min+exp) | content.js:182, 934-939; background.js:1128-1137, 1528; overlay.css:280-284 | Servidor fora = pill minimizado congelado sem NENHUM sinal; expandido "Conectando..." eterno ou "🟡 Aguardando aposta" mentiroso; sugestão velha parece atual | Estado de erro explícito nas 2 vistas: watchdog de state_sync (>Ns sem heartbeat ⇒ borda cinza/vermelha + "⚠ sem servidor" no pill, centros esmaecidos); `connectionStatus` broadcast a todas as abas sem depender de `tabId` |
| BG-01 | **P1** | Sistêmico (ext.) | background.js:1503-1531, 1014-1019, 1222-1228 | `startListening`/`capturarMesa` respondem sucesso sem servidor; leituras descartadas em silêncio; badge verde mente | Resposta distinta `{success:true, serverConnected:false}` propagada às UIs; badge amarelo quando escutando-sem-servidor; contador de descartes DIR20 já existe — expor giros perdidos por WS-down no popup/overlay |
| PP-01 | **P1** | Popup | popup.js:392-394, 577; popup.html:500-506 | "✅ CONECTADO" = aba ativa, não servidor; nenhum status do WS no popup; contradiz o dropdown "(servidor offline?)" | Renomear para "Aba OK" ou dividir em 2 linhas: Aba ✔ / Servidor ✔|✖ (o dado já vem em `getState().isConnected`) |
| OV-02 | **P1** | Overlay (drag) | content.js:510-538 (touchstart/move/end; clamps só em :531-532) | Sem drag por mouse no desktop (operador é desktop); overlay fixo sobre a mesa; touch pode empurrar o painel para fora da borda inferior/esquerda da viewport sem volta | Migrar para Pointer Events (`pointerdown/move/up` cobre mouse+touch) + clamp nas 4 bordas + área de arraste = header (evita conflito com selects da seção de controle) |
| MN-01 | **P1** | Overlay (controle) | content.js:432 (`slice(-10)`); background.js:2173 (`unshift` ⇒ newest-first) | Grade do painel de controle mostra os 10 mais ANTIGOS — os 2 resultados mais recentes nunca aparecem; diverge do popup (que mostra newest-first correto, popup.js:697-736) | `slice(0, 10)` |
| GB-01 | **P1** | Glass Box | app.js:4, 8, 86, 97, 105 | Reconexão fixa 5s sem backoff/jitter; `reconnectAttempts` declarado e zerado mas nunca usado (código morto); todos os dashboards martelam juntos quando o servidor volta | Espelhar o padrão da extensão (background.js:989-1012): expoente+jitter+teto 60s+timer único; exibir "tentativa N — próxima em Xs" no pill |
| GB-02 | P2 | Glass Box | app.js:277; index.html:17 | "⚫ ONLINE" e "⚫ OFFLINE" usam o MESMO glifo preto; a distinção é só cor de fundo (falha para daltônicos/relance; o círculo preto contradiz "online") | `🟢 ONLINE` / `🔴 OFFLINE` (ou `●` com `aria-label` + cor), manter fundo |
| GB-03 | P2 | Glass Box | app.js:80, 88, 95, 100-105, 513-518 (MAX_LOGS 50) | Queda longa: 3 entradas de log por ciclo de 5s ⇒ em ~80s o log inteiro é spam de reconexão, enterrando eventos reais | Colapsar tentativas numa única linha mutável ("Reconectando… tentativa N"); logar só transições de estado |
| GB-04 | P2 | Glass Box | app.js:254, 504-510 (resetFlow limpa só o fluxo) | Após desconexão, Último Spin/Resultado/Regiões/Métricas/Martingale/latência permanecem com valores velhos sem marcação | Classe `stale` (opacity+"dados de HH:MM:SS") aplicada no `onclose` a todos os cards |
| GB-05 | P2 | Glass Box | app.js:208-218, 257-265 | Métricas podem contar o mesmo spin 2× quando chegam `trace` E `sugestao` (guarda depende de `result.trace_id` existir; `handleTrace` não tem guarda inversa) | Dedupe por `trace_id` num `Set` único compartilhado pelos dois handlers |
| GB-06 | P2 | Glass Box | app.js:315-321, 439, 526-529 (com :119), 194-205 | `innerHTML`/`title` com campos string do payload WS sem escape (`step.name`, `step.data`, `data.message` do ack, `r.label`, tooltip) — XSS surface honesta: payload é nosso, mas via WS público | Helper `esc()` (ou `textContent` nos folhas); coagir numéricos com `Number()` |
| GB-07 | P2 | Glass Box | style.css:208-210, 463-465 vs 713-728 | Em ≤768px o grid vira 1 coluna mas `.result-card`/`.strategy-card` mantêm `grid-column: 2` ⇒ coluna fantasma, layout quebrado no celular | Resetar `grid-column: 1` no media query (como já feito p/ logs/trace/timeline) |
| PP-02 | P2 | Popup | popup.js:424-448 (não esconde), 450-452 (re-habilita) | Durante escuta, ▶️ INICIAR fica visível E habilitado ao lado de ⏹️ PARAR — clique re-dispara startListening | No estado `isListening`: `btnStart.style.display='none'` (o overlay já faz o equivalente, content.js:414-421) |
| PP-03 | P2 | Popup | popup.js:604-624, 149-155; background.js:1222-1228 | 📸 preso em ⏳ para sempre quando o servidor não responde `mesaConfigurada` (caso 502 real); log diz "✅ Captura enviada" mesmo com WS caído | Timeout de 10s restaurando o botão + `capturarMesaRemota` deve reportar `sendToWebSocket()===false` como erro |
| PP-04 | P2 | Popup | popup.html:551-553 (export) vs 576-602 (painel), 556-573 (direção) | Hierarquia invertida: botão de debug (EXPORTAR LOGS) acima do semáforo de operação; controle crítico de direção no meio do scroll | Reordenar por frequência de uso: conexão → semáforo/financeiro → direção → mesa/escuta → resultados → debug no rodapé |
| OV-03 | P2 | Overlay exp. | overlay.css:67-77 vs 80-90; content.js:622-625 | `.g1/.g2/.g3` (mesma especificidade, declaradas DEPOIS) vencem a cor da ação: "⏳ AGUARDANDO" renderiza VERDE (g1) e "⏸️ PULAR" pode ficar dourado — verde=GO quando não há sugestão | Aplicar classe g* no status APENAS quando minimizado (é o único lugar onde ela é semântica); ou escopar `.minimized .eb-status.g1` |
| OV-04 | P2 | Overlay exp. | overlay.css:185-195; content.js:584-587 | Estado AGUARDANDO usa a mesma caixa gradiente VERDE-GO da região de aposta com o texto "Aguardando..." — a cor grita "aposte" | Variante `.eb-region.aguardando` cinza/neutra |
| OV-05 | P2 | Overlay | content.js:777-779 vs 469-476 | `handleSessionReset` zera `overlayState.isMinimized` sem remover a classe `.minimized` nem chamar `saveUIState()` ⇒ visual e estado divergem; próximo clique no − "não faz nada" (re-adiciona classe já presente) | Reset deve reusar `toggleMinimize`/aplicar classe + persistir |
| OV-06 | P2 | Overlay | content.js:60-64 (usos :482,608,927), 85-104 (:572), 108-117 (:592) | `innerHTML` no DOM da página do cassino com strings do payload (`label`, `gale_display`, `slot`, `numeros`) sem escape — superfície XSS caso servidor/master comprometido | Igual GB-06: `esc()` + `Number()` nos numéricos; ou construir via `createElement`/`textContent` |
| MN-02 | P2 | Overlay min. | content.js:925-926 | Precedência invertida no badge 17/21 do heartbeat: cache (`lastSugestao`) vence o dado FRESCO do state_sync — badge velho persiste após o servidor trocar o modo | Inverter: `data.force17?.v5_mode || v5ModeFromSugestao(lastSugestao)` |
| MN-03 | P2 | Overlay min. | content.js:890-892, 911 | Heartbeat só atualiza o pill quando `bet_placed=true` — em sequências de PULAR o minimizado fica congelado entre sugestões; pós-reload fica "⏳ AGUARDANDO" até a 1ª aposta | Atualizar centros/badge no heartbeat independente de `bet_placed` (manter o gate SÓ para gale/aposta, que é a razão original do gate) |
| MN-04 | P2 | Overlay CSS | overlay.css:275-290 E 359-391 | Regras `.minimized` duplicadas em dois blocos distantes — mexer num e esquecer o outro é armadilha ativa (o brief do X5 já precisa citar "duas media queries!") | Unificar num bloco único ANTES/DURANTE o X5 |
| PP-05 | P3 | Popup×Dash | popup.html:561-567; popup.js:722, 343-349; index.html:90-97 | Vocabulário de direção inconsistente: popup ⬅️ HORÁRIO/➡️ ANTI (azul/laranja); dashboard 🔄 CW/🔃 CCW (azul/verde); grade usa ⬅️/➡️ | Padronizar par ícone+cor único nas 3 superfícies (decisão de design; sugerido ↻/↺ + azul/laranja) |
| PP-06 | P3 | Popup | popup.js:302-311 vs content.js:448-461 | `updateMesas` broadcast reconstrói o dropdown sem restaurar a seleção (o overlay restaura) | Copiar o padrão do overlay (`const current = select.value; ...; select.value = current`) |
| PP-07 | P3 | Popup | popup.js:237-247 | Cancelar o file picker pode deixar "⏳ Carregando..." (nem todo Chrome dispara `onchange` no cancel) | Ouvir o evento `cancel` do input (Chrome ≥113) além do onchange |
| OV-07 | P3 | Overlay | content.js:656-658 | Beep em TODO update APOSTAR (re-broadcasts repetem) e sem toggle de som para o operador | Beep só na transição de `trace_id`/sugestão nova + toggle 🔈 persistido |
| OV-08 | P3 | Overlay | overlay.css:114-151; content.js:696 | 🔄 Nova Sessão (destrutivo) 24px a 6px do − minimizar — alvo pequeno (Fitts) com vizinho perigoso; mitigado pelo confirm() | Separar com espaçador; alvo ≥32px como já feito no media touch |
| OV-09 | P3 | Overlay | content.js:696, 738 | `confirm()` nativo congela o JS da página do cassino durante o jogo ao vivo | Mini-diálogo interno no overlay (2 botões) sem bloquear a página |
| OV-10 | P3 | Overlay | content.js:763 | Typo "Aguardando novo dados..." | "Aguardando novos dados..." |
| MN-05 | P3 | Overlay CSS | overlay.css:393-676 | ~280 linhas (40% do arquivo) de CSS morto do control panel v4.0 removido (`#eb-ctrl-toggle`, `.ebcp-*`) | Remover em sprint de limpeza |
| MN-06 | P3 | Overlay min. | content.js:917-921 | Fallback final do cold-start ainda usa `pending_prediction.centers` na ordem V4 `[C1,C2,C3]` (≠ c2,c3,c1 do formato único) — divergência de ordem possível se `data.regioes` faltar | Reordenar no fallback ou descartar o fallback V4 quando servidor ≥V5 |
| GB-08 | P3 | Glass Box | index.html:28,34,40,46; app.js:507 | `.flow-status` nunca é populado — sempre `--` (elemento morto que sugere informação que nunca chega) | Preencher (ex.: ms por etapa do trace) ou remover |
| GB-09 | P3 | Glass Box | app.js:530 | Contador `(N)` do card Logs mostra o total, não o nº de entradas do filtro ativo | `filtered.length` quando filtro ≠ all |
| GB-10 | P3 | Glass Box | index.html:272; app.js:3 | URL do WS hardcoded em 2 lugares (rodapé HTML + JS) — podem divergir | Rodapé lê `WS_URL` no boot |
| GB-11 | P3 | Glass Box | app.js:293 | Score sempre "`/6`" hardcoded — se a escala mudar (V5), o denominador mente | Enviar/usar `score_max` do payload com fallback 6 |

### Suspeitas do Diretor — veredito

| Suspeita (brief §3) | Veredito |
|---|---|
| `app.js:277` ⚫ ONLINE | **Confirmada** → GB-02 |
| `setupDrag` só touch | **Confirmada + agravada** (sem clamp inferior) → OV-02 |
| Zonas mortas de clique (`pointer-events`) | **Não confirmada** — verificado OK (§2.4) |
| 3 writers do minimizado divergindo | **Formato: resolvido** (helper único em :482/:608/:927); **dados: diverge** em edge-cases → MN-02, MN-03, MN-06 |
| Reconexão sem backoff | **Dashboard: confirmada** (GB-01); **extensão: não confirmada** — backoff exponencial+jitter+teto verificado OK (background.js:989-1012) |
| `innerHTML` com payload | **Confirmada** nas duas superfícies → GB-06, OV-06 (severidade honesta: P2) |
| WAITING/"Conectando..." permanente com servidor fora | **Confirmada + agravada** (tabId-gate, overwrite do stateSync, minimizado cego) → OV-01, BG-01 |
| Duplicação popup × seção de controle | **Confirmada com divergências reais**: significado de "CONECTADO" (PP-01), grade de resultados (MN-01), restauração de seleção de mesa (PP-06), visibilidade do INICIAR (PP-02) |

---

## 5. Heurísticas — leitura transversal

- **Visibilidade de status (Nielsen #1):** o pior gap do produto — estado do servidor
  invisível exatamente nas superfícies de jogo (OV-01/PP-01/BG-01).
- **Correspondência com o mundo real (#2):** cor verde usada para "aguardando" (OV-03/OV-04)
  e ⚫ para "online" (GB-02) violam o código de cores que o próprio produto estabeleceu.
- **Consistência (#4):** direção com 3 vocabulários (PP-05); duas grades de resultados com
  ordens diferentes (MN-01); "CONECTADO" com 2 significados (PP-01).
- **Prevenção de erro (#5):** INICIAR clicável durante escuta (PP-02); Nova Sessão colada no
  minimizar (OV-08).
- **Fitts / jogo ao vivo:** alvos de 24px no header do overlay; drag indisponível no desktop
  significa que o operador não consegue afastar o painel do racetrack da Evolution (OV-02).
- **Latência percebida:** toggles do overlay respondem <100ms ✔; 📸 sem timeout viola a
  expectativa (PP-03).

---

## 6. Validação da decisão do SPR-X5 (racetrack abaixo dos centros no minimizado)

**Veredito: CONFIRMADA.** A posição (linha 2 do pill, abaixo do formato único
`[C2][C3][C1]`+badge+gale) é o menor delta visual que resolve o "onde clico?" em <1s:
mantém a linha 1 intocada (formato único preservado — pré-requisito correto), aproveita o
mapeamento espacial 1:1 com o widget de vizinhos da Evolution, e `pointer-events:none` evita
capturar cliques destinados à mesa. Largura ~200–240px é viável (SVG escala por viewBox).

**Refinamentos v2 propostos (não bloqueiam o X5):**
1. **O racetrack deve obedecer ao futuro estado de erro (OV-01):** quando o watchdog de
   state_sync disparar, apagar/esmaecer o glow — um racetrack aceso com servidor morto é a
   versão gráfica da sugestão congelada (pior que o pill de texto, porque brilha).
2. **Legibilidade a 220px:** com 17–21 slots acesos, números legíveis em TODOS os acesos
   (~7px/slot) tende a virar ruído — v2: rótulo numérico apenas nos 3 CENTROS
   (`.active-center`), demais acesos só glow. O brief já aponta essa direção ("legibilidade
   dos ACESOS > completude"); recomendo formalizar "número visível = só centros" como
   default no minimizado.
3. **Unificar os dois blocos `.minimized` do CSS (MN-04) no próprio PR do X5** — o X5 vai
   mexer exatamente aí; deixar a duplicação viva dobra o risco da lição de 05/08.
4. **Interação com drag (OV-02):** o pill fica ~2× mais alto; com clamp só em top/left, fica
   mais fácil "perder" o overlay pela borda inferior em telas baixas — se o v2 do drag não
   sair antes, ao menos clampar `top` a `window.innerHeight - alturaDoPill` no X5.

---

## 7. Sprints candidatos (agrupamento com locks — o Diretor decide)

### 7.1 SPR-UX-CONN · "o front não mente sobre conexão" — **P0/P1**
- **Escopo:** OV-01 (estado de erro nas 2 vistas + watchdog de state_sync), BG-01 (start/
  captura reportam servidor; badge amarelo; descartes WS-down visíveis), PP-01 (linha de
  status do servidor no popup), PP-03 (timeout do 📸), MN-03 (heartbeat atualiza pill sem
  bet_placed).
- **Locks:** `extensão-JS` (content.js, background.js, popup.*) — serializa com SPR-X5.
- **Nota:** é a materialização da jornada 502 de hoje; candidato a P0 do bloco.

### 7.2 SPR-UX-DESKTOP · "overlay operável no desktop" — P1
- **Escopo:** OV-02 (Pointer Events + clamp 4 bordas), MN-01 (`slice(0,10)`), OV-08 (alvos/
  espaçamento header), OV-07 (beep por transição + toggle som), OV-05 (reset × minimizado).
- **Locks:** `extensão-JS` (content.js, overlay.css) — serializa com X5 (mesmos arquivos).

### 7.3 SPR-UX-DASH · "dashboard honesto e robusto" — P1/P2
- **Escopo:** GB-01 (backoff espelhado da extensão), GB-03 (log colapsado), GB-04 (stale
  dimming), GB-02 (🟢/🔴), GB-05 (dedupe métricas), GB-06 (escape innerHTML), GB-07 (grid
  mobile).
- **Locks:** `frontend/` apenas — **paraleliza** com 7.1/7.2 sem conflito.

### 7.4 SPR-UX-POLISH · "consistência e dívida" — P2/P3
- **Escopo:** OV-03/OV-04 (semântica de cor), PP-02/PP-04/PP-05/PP-06/PP-07, OV-06 (escape
  overlay), OV-09/OV-10, MN-02/MN-04*/MN-05/MN-06, GB-08..GB-11. (*MN-04 sai daqui se for
  absorvido pelo X5, como recomendado em §6.3.)
- **Locks:** `extensão-JS` + `frontend/` — rodar por último, rebase barato (só cosmético).

---

## 8. Definition of Done do brief — checklist

- [x] 100% dos elementos interativos das 4 superfícies inventariados (§2, tabelas com ✔).
- [x] ≥1 achado com evidência arquivo:linha por superfície (Glass Box: GB-01..11 · Popup:
      PP-01..07 · Overlay expandido: OV-01..10 · Overlay minimizado/controle: MN-01..06).
- [x] Matriz de estados completa (§3.1–3.3) com células onde a informação mente marcadas ⚠️.
- [x] Jornada "servidor fora" ponta a ponta com sonda real e propostas (§3.4, §7.1).
- [x] Validação do SPR-X5 com refinamentos v2 (§6).
- [x] Zero mudança de código (docs-only).
