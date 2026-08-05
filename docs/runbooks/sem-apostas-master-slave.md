# Runbook — "Servidor ligado, mas sem apostas/regiões" (eleição de MASTER)

> Modo de falha nº1 do fluxo de dados. Sintoma típico: o **Glass Box mostra
> ONLINE**, o container está `healthy`, **mas nenhuma região de aposta aparece**
> e nenhum resultado chega. Quase sempre a causa é **não há WS MASTER eleito** —
> e não o servidor "caído". Documentado após o incidente de 13/06/2026
> (~16h sem spins).

---

## 0. TL;DR — recuperar em 30 segundos

1. **Na escuta (página da roleta):** se o indicador do overlay estiver
   `👁️ VIEWER`, clique no botão **🎯 (Forçar MASTER)** e confirme.
   Isso usa o caminho `force_master`, que **não** é afetado pelo bug.
2. **Se não tiver acesso à escuta:** `docker restart roleta-cloud` no servidor.
   No boot, o primeiro REGISTER vira MASTER automaticamente.
3. **Confirmar recuperação:**
   ```bash
   docker logs roleta-cloud --since 2m | grep "👑"      # deve aparecer "Novo MASTER assumiu"
   docker logs roleta-cloud --since 2m | grep VERIFICANDO # deve aparecer ao próximo giro real
   ```

---

## 1. A organização do fluxo de dados (quem faz o quê)

```
[Escuta / extensão Chrome]                                  [Glass Box / Overlay]
 extension/deal_capture.js                                  frontend/app.js (dashboard)
 extension/background.js                                    extension/content.js (overlay)
        │                                                            ▲
        │ novo_resultado  (ENVIADO SÓ SE role == MASTER)             │ trace / sugestao / state_sync
        ▼                                                            │ (regiões aparecem aqui)
   wss://roleta.xma-ia.com/ws ──► server/connection_manager.py ──► server/message_handler.py
                                   (atribui role master/slave)        │ gate de role + dedup
                                                                      ▼
                                                            strategies/sda17.py (decisão)
                                                                      │ broadcast p/ todas conexões
                                                                      ▼
                                                       dashboard + overlay (mostra a região)
```

| Componente | Arquivo | Papel |
|---|---|---|
| Captura do giro | `extension/deal_capture.js`, `extension/background.js` | Lê o número/sentido na DOM da Evolution e envia `novo_resultado` |
| Transporte | `wss://roleta.xma-ia.com/ws` → `127.0.0.1:8765` | WebSocket único; proxy reverso → container |
| Eleição de role | `server/connection_manager.py` | Decide quem é **MASTER** (envia dados) e quem é **SLAVE** (só recebe) |
| Gate + roteamento | `server/message_handler.py` | Rejeita dados de SLAVE; despacha por tipo de mensagem |
| Estratégia | `strategies/sda17.py` (`SDA17Strategy`) | Calcula centro/região/score → decisão |
| Visualização | `frontend/app.js`, `extension/content.js` | Glass Box e overlay; renderizam `trace`/`state_sync` |

---

## 2. A invariante que, quebrada, causa o incidente

**Só o WS MASTER pode alimentar o sistema com giros.**

- Servidor (`server/message_handler.py:94-103`): mensagens de dados
  (`novo_resultado`, `historico_inicial`, `correcao_historico`) vindas de quem
  **não** é `master` são **descartadas** com erro `NOT_MASTER`.
- Escuta (`extension/background.js:313-315`): quando o role local **não** é
  `master`, a extensão **nem envia** o giro.

Consequência: **sem MASTER eleito → silêncio total de spins**, e — porque a
escuta nem tenta enviar — **sem nenhum warning de rejeição no log do servidor**.
O servidor parece perfeitamente saudável.

---

## 3. Por que o "ONLINE" do Glass Box engana

O status `⚫ ONLINE` é setado **apenas no `ws.onopen`** (`frontend/app.js:83-89`,
`252-255`). Ou seja, significa só que **o handshake WebSocket abriu** — **não**
que há fluxo de dados. As regiões de aposta só aparecem quando chega uma
mensagem `type: 'trace'` (`frontend/app.js:107-118, 264-272`). Logo:

> **ONLINE + sem regiões = conexão ok, mas nenhuma decisão sendo emitida.**
> Não confunda "conectado" com "funcionando".

---

## 4. Causa-raiz do incidente 13/06 (o que causou o erro)

Cadeia causal completa:

1. **Container reiniciou 03:15 UTC** (deploy v4.4.0). Escuta `dev-8c01a7ea`
   conectou e virou MASTER. Spins fluíram normalmente até **04:06**
   (`decision_id=5956`).
2. **04:29:47 — o MASTER desconectou** (aba/escuta fechada). `disconnect()`
   iniciou o **grace period de 10s** e gravou `last_master_device_id =
   dev-8c01a7ea` (`server/connection_manager.py:139-160`).
3. Como **nenhuma outra conexão existia** naquele momento, o
   `handle_grace_period` (`:162-194`) expirou sem promover ninguém. Ficou
   `master_id = None`.
4. **Horas depois**, a escuta voltou e enviou REGISTER. O caminho de promoção
   `update_device_id` (`:222-285`, versão anterior) tinha **dois ramos**, e
   **ambos falhavam**:
   - `is_master_reconnecting` exige `(agora - disconnect) < 10s` → **falso**
     (passaram horas);
   - o fallback `elif not self.last_master_device_id:` → **falso**, porque
     `last_master_device_id` já estava preenchido (`dev-8c01a7ea`).
5. **Resultado: deadlock.** A escuta ficava **SLAVE para sempre**; cada giro era
   descartado (regra da §2). Por isso `roleta_seconds_since_last_spin`
   (`server/health_server.py:122`) cresceu sem parar e o alerta
   `RoletaNoSpinsRecent` disparou por ~16h, até o restart manual às 20:16.

**Assinatura nos logs:** a última linha `👑 ... assumiu/restaurado` é de
**04:29** (na verdade a última *positiva* foi às 03:15); depois disso, **nenhuma
linha `👑`** — prova de que o sistema ficou sem MASTER.

### Correção aplicada
`server/connection_manager.py › update_device_id` agora promove a MASTER sempre
que **não há master** e (é o master reconectando no grace **OU** o grace já
expirou **OU** nunca houve master); mantém SLAVE **apenas** para um device
*diferente* **dentro** do grace (preservando a janela de reconexão do master
original). Coberto por `tests/test_connection_manager_master.py` (5 testes).
Commit local `1446166` — **precisa de `git push` para ser deployado** (a
produção ainda roda o código antigo).

---

## 5. Diagnóstico (comandos)

```bash
# 1) O container está de pé e healthy? (quase sempre SIM — não é esse o problema)
docker ps --filter name=roleta-cloud --format '{{.Names}} {{.Status}}'

# 2) Há quanto tempo sem spin? (contador crescente = ingestão parada)
docker logs roleta-cloud --since 30m 2>&1 | grep RoletaNoSpinsRecent | tail -3

# 3) Ciclo de vida do MASTER — a evidência decisiva.
#    Se a ÚLTIMA linha 👑 for antiga e não houver "assumiu/restaurado" recente,
#    o sistema está SEM MASTER.
docker logs roleta-cloud --timestamps 2>&1 | grep "👑" | tail -10

# 4) A escuta está conectando mas sem virar master?
#    "REGISTER ... device_id=..." seguido de NENHUM "👑 Novo MASTER" = deadlock.
docker logs roleta-cloud --since 15m 2>&1 | grep -E "REGISTER|👑|SLAVE" | tail -20

# 5) Há giros sendo processados? (vazio = nada chegando/aceito)
docker logs roleta-cloud --since 5m 2>&1 | grep -E "VERIFICANDO|decision_created" | tail
```

---

## 6. Recuperação imediata

| Situação | Ação |
|---|---|
| Tenho acesso à escuta | Clicar **🎯 Forçar MASTER** no overlay (`extension/content.js:632`) |
| Só tenho o servidor | `docker restart roleta-cloud` (reelege MASTER no boot) |
| Recorrência frequente | **Deployar o fix** (§4) — `git push` do commit `1446166` |

> O restart resolve **na hora**, mas **mascara** o bug se o código antigo ainda
> estiver em produção. A correção definitiva é o deploy do fix.

---

## 7. Prevenção — para não ocorrer de novo

1. **Deployar o fix do deadlock (prioridade 1).** `git push` do commit `1446166`
   → o pull-deploy (`roleta-deploy.timer`, ~2min) aplica. Elimina a causa-raiz.
   Confirmar no servidor que o `connection_manager.py` em produção contém o ramo
   "MASTER assumido após grace period expirado".

2. **Alerta que aponta a CAUSA, não o sintoma — ✅ IMPLEMENTADO.** Antes só
   existia `RoletaNoSpinsRecent` (sintoma, `warning`), que disparou por ~16h sem
   ação efetiva. Agora há **`RoletaNoMaster`** (`obs/alerts.yml`):
   `expr: (roleta_ws_connections > 0) and (roleta_master_present == 0)`,
   `for: 1m`, `severity: critical`. As métricas `roleta_master_present` (0/1) e
   `roleta_ws_connections` são expostas por um provider do ConnectionManager
   registrado no boot (`server/websocket.py` → `server/health_server.py`).
   Reduz a detecção de **~16h para ~1min** e diz o que fazer (Forçar MASTER /
   restart). *Requer deploy (`git push`) para entrar em produção.*

3. **Elevar severidade/rota do `RoletaNoSpinsRecent`** de `warning` para algo que
   efetivamente notifique o dono em horário de operação (o alerta funcionou; o
   roteamento, não).

4. **Auto-recuperação (defesa em profundidade).** Já existe `handle_grace_period`
   que promove o SLAVE mais recente ao fim do grace. Com o fix da §4, a
   reconexão tardia também recupera sozinha. Opcional: se `master_id is None`
   por > N segundos **e** há conexões, promover a mais recente proativamente.

5. **Clientes passivos nunca viram MASTER — ✅ IMPLEMENTADO (04/08/2026).**
   Incidente pós go-live V5: o grace period promoveu um **dashboard Glass Box**
   (conexão sem REGISTER, `device_id="unknown"`) a MASTER; a escuta re-registrou
   e ficou SLAVE eterna → spins nunca enviados (gate local da escuta), Glass
   Box/overlay congelados **sem nenhum erro no log**. Fix em
   `server/connection_manager.py`: (a) `handle_grace_period` só promove conexões
   **registradas**; (b) REGISTER **destrona** master passivo (`unknown`) e
   assume — master registrado segue protegido. Regressão:
   `tests/test_connection_manager_master.py` (9 testes). Assinatura do incidente
   num probe passivo: `state_sync` 1Hz fluindo + **zero `trace`** com mesa ativa.

### Checklist de operação
- [ ] Glass Box sem regiões? → rodar o diagnóstico da §5 (passo 3, linhas `👑`).
- [ ] Sem MASTER recente? → Forçar MASTER (escuta) **ou** restart do container.
- [ ] Confirmar giro processado (`VERIFICANDO` / `decision_created`).
- [ ] Garantir que o fix do deadlock (commit `1446166`) está deployado.

---

## Referências de código

- `frontend/app.js:83-89, 252-255` — ONLINE = só handshake.
- `server/message_handler.py:94-103` — gate `NOT_MASTER`.
- `server/connection_manager.py:139-194` — disconnect + grace period.
- `server/connection_manager.py:222-285` — `update_device_id` (ponto do bug/fix).
- `extension/background.js:313-315` — escuta não envia se não for master.
- `extension/content.js:632, 749-775` — botão 🎯 Forçar MASTER (visível quando SLAVE).
- `obs/alerts.yml:28-33` — `RoletaNoSpinsRecent`; `server/health_server.py:122` — métrica do sintoma.
- `tests/test_connection_manager_master.py` — regressão dos 5 cenários de eleição.
