"""Contrato `phase_authority`: PRODUTOR (servidor SPR-V1) x CONSUMIDOR (extensão SPR-V2).

O bloco nasceu no SPR-V1 (`GameState.engine_overlay_fields`) como pré-requisito do
SPR-V2, e os dois sprints foram escritos em repositórios de código diferentes (Python
e JS) sem nenhum teste que os amarrasse. Este módulo é essa amarra: cada asserção
existe porque `extension/background.js::handleStateSyncPhase` depende dela.

O que o V2 realmente lê do bloco (background.js §304-365) — e só isto:

  ``enabled``    gate de capability, comparado com ``pa.enabled === true``. A comparação
                 é ESTRITA: um ``1`` inteiro (ou uma string ``"true"``) desarmaria a
                 reconciliação em SILÊNCIO, sem erro em lugar nenhum.
  ``direction``  passa por ``normalizePhaseDir``, que aceita ``cw``/``ccw``. Qualquer
                 outro vocabulário vira ``null`` e o passo de desfazer-flip vira no-op.
  ``spin_seq``   heurística de ACK (``Number.isFinite(Number(...))``). Precisa existir
                 MESMO SEM ÂNCORA — é assim que o V2 detecta giro rejeitado.

``seed_parity``/``seed_n`` são publicados mas hoje NÃO são consumidos; ficam cobertos
apenas quanto a serem JSON puro, para não travar evolução futura do V2.

Os testes cobrem os três eixos onde uma incompatibilidade real poderia se esconder:
(1) o bloco chega ao canal que o V2 escuta; (2) o tipo/vocabulário sobrevive ao JSON;
(3) `phase_authority.direction` e `sentido.next_direction` NÃO divergem — se
divergissem, o V2 desfaria o flip para uma direção no passo 1 e reconciliaria para a
outra no passo 2, oscilando a cada heartbeat.
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from state.game import GameState
from state.phase import ANTI, HORARIO, project_phase

# Vocabulário aceito por `normalizePhaseDir` (extension/background.js §284-288).
# `null` é explicitamente tratado pelo consumidor (não reverte o flip).
V2_DIRECTIONS_ACEITAS = {"cw", "ccw", "horario", "anti-horario", "anti_horario"}

# Campos que o V2 lê hoje. Se algum sumir do produtor, o consumidor degrada em silêncio.
V2_CAMPOS_CONSUMIDOS = ("enabled", "direction", "spin_seq")


def _ancorada(spin_seq=6, parity=HORARIO, n=0):
    gs = GameState()
    gs.spin_seq = spin_seq
    gs._apply_seed(parity, "operator_seed", n=n)
    return gs


def _pa(gs):
    return gs.engine_overlay_fields()["phase_authority"]


# --------------------------------------------------------------------- wiring real
# O V2 escuta `state_sync` e entrega `data.data` ao handler de fase
# (background.js §875: `await handleStateSyncPhase(data.data)`).

def test_state_sync_do_heartbeat_entrega_phase_authority(monkeypatch):
    """Canal ponta-a-ponta: o bloco chega em `state_sync.data`, onde o V2 o procura.

    Sem esta asserção, remover o `update(engine_overlay_fields())` de
    `server/websocket.py` desarmaria TODO o SPR-V2 sem quebrar um único teste:
    `pa` viria `undefined`, `paEnabled` viraria `false` e a reconciliação
    simplesmente pararia de acontecer — silenciosamente.
    """
    import server.websocket as ws_mod

    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "1")
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", "1")

    capturado = []
    pronto = asyncio.Event()

    class _StubCM:
        active_connections_set = {"cliente-fake"}

        async def broadcast(self, message, exclude_disconnected=True):
            capturado.append(message)
            pronto.set()

    monkeypatch.setattr(ws_mod, "connection_manager", _StubCM())
    monkeypatch.setattr(ws_mod.db_service, "get_window_history", lambda: [])
    monkeypatch.setattr(ws_mod.game_state, "spin_seq", 6)
    ws_mod.game_state._apply_seed(HORARIO, "operator_seed", n=0)

    async def _uma_volta():
        tarefa = asyncio.create_task(ws_mod.broadcast_heartbeat())
        try:
            await asyncio.wait_for(pronto.wait(), timeout=10)
        finally:
            tarefa.cancel()
            try:
                await tarefa
            except asyncio.CancelledError:
                pass

    asyncio.run(_uma_volta())

    assert capturado, "heartbeat não publicou nada"
    msg = json.loads(capturado[0])
    assert msg["type"] == "state_sync"
    pa = msg["data"]["phase_authority"]          # <- exatamente o que o V2 acessa
    assert pa["enabled"] is True
    assert pa["direction"] == "cw"
    assert pa["spin_seq"] == 6


# ---------------------------------------------------------------------- schema/tipos

def test_campos_consumidos_pelo_v2_existem_sempre():
    """Presentes com e sem âncora — o ACK do V2 depende disso no estado frio."""
    for gs in (_ancorada(), GameState()):
        pa = _pa(gs)
        for campo in V2_CAMPOS_CONSUMIDOS:
            assert campo in pa, f"{campo} ausente: consumidor degrada em silêncio"


def test_enabled_e_booleano_estrito_no_json(monkeypatch):
    """`pa.enabled === true` no V2: `1` ou `"true"` desarmariam a reconciliação."""
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "1")
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", "1")
    bruto = json.dumps(_pa(_ancorada()))
    assert '"enabled": true' in bruto, bruto
    assert json.loads(bruto)["enabled"] is True


@pytest.mark.parametrize("sae,pbs,esperado", [
    ("0", "0", False),
    ("1", "0", False),   # rollout passo 1 isolado: capability ainda NÃO anunciada
    ("0", "1", False),   # idem, ordem inversa
    ("1", "1", True),
])
def test_enabled_e_o_and_das_duas_flags(monkeypatch, sae, pbs, esperado):
    """Capability = autoridade E buffer-sync.

    Importa para o ROLLOUT: ligar só `SDA_PHASE_BUFFER_SYNC` não acende o V2. E
    importa para o ROLLBACK: desligar qualquer uma das duas desarma o consumidor
    sozinho, sem precisar tocar na extensão instalada.
    """
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", sae)
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", pbs)
    assert _pa(_ancorada())["enabled"] is esperado


@pytest.mark.parametrize("parity,seq,esperado", [
    (HORARIO, 6, "cw"),
    (HORARIO, 7, "ccw"),
    (ANTI, 6, "ccw"),
    (ANTI, 7, "cw"),
])
def test_direction_usa_o_vocabulario_que_o_v2_normaliza(parity, seq, esperado):
    d = _pa(_ancorada(spin_seq=seq, parity=parity))["direction"]
    assert d == esperado
    assert d in V2_DIRECTIONS_ACEITAS


def test_sem_ancora_direction_null_mas_spin_seq_vivo():
    """Assimetria deliberada: sem âncora não há fase a espelhar, mas o ACK continua.

    `normalizePhaseDir(null)` devolve `null` e o V2 pula o desfazer-flip; já a
    heurística de ACK precisa de `spin_seq` para saber se o giro foi contado. Publicar
    `null` aqui também seria um furo — o V2 marcaria todo giro como rejeitado.
    """
    pa = _pa(GameState())
    assert pa["direction"] is None
    assert isinstance(pa["spin_seq"], int)
    assert not isinstance(pa["spin_seq"], bool)


def test_bloco_inteiro_e_json_puro_sem_ancora_e_com_ancora():
    for gs in (_ancorada(), GameState()):
        pa = _pa(gs)
        assert json.loads(json.dumps(pa)) == pa


# ------------------------------------------------------- coerência entre os 2 blocos

class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


@pytest.fixture()
def make_handler(tmp_path, monkeypatch):
    import database
    from app_config.settings import settings
    from server import message_handler as mh_mod
    from server.message_handler import MessageHandler
    from strategies.sda17 import SDA17Strategy

    database.init_database(str(tmp_path / "d.db"))
    monkeypatch.setattr(settings, "state_file", tmp_path / "state.json")
    monkeypatch.setattr(mh_mod.db_service, "save_decision", lambda d: 1)
    monkeypatch.setattr(
        mh_mod.connection_manager, "broadcast",
        MagicMock(side_effect=lambda *a, **k: asyncio.sleep(0)),
    )
    monkeypatch.setattr(mh_mod.connection_manager, "get_role", lambda cid: "master")

    return lambda: MessageHandler(
        game_state=GameState(), strategy=SDA17Strategy(),
        state_lock=asyncio.Lock(), configs_path=str(tmp_path / "cfg"),
    )


def test_direction_nao_diverge_de_sentido_next_direction(make_handler, monkeypatch):
    """Guarda anti-ping-pong: os DOIS blocos do mesmo payload têm de concordar.

    O V2 usa duas fontes no mesmo `state_sync`: `phase_authority.direction` (projeção
    determinística da âncora) para desfazer um flip local, e `sentido.next_direction`
    (`target_direction`, o toggle sobre `last_direction`) para reconciliar. São CÓDIGOS
    INDEPENDENTES — se divergirem, o cliente é puxado para um lado no passo 1 e para o
    outro no passo 2, oscilando a cada heartbeat.

    Elas coincidem por um motivo específico: com `SDA_SENTIDO_AUTORITATIVO=1` o servidor
    grava em `last_direction` a PROJEÇÃO do giro n, logo o toggle
    `opposite(proj(n)) == proj(n+1)` reencontra a projeção em `spin_seq`. Este teste
    trava esse invariante contra qualquer mudança futura em `target_direction`.
    """
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "1")
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", "1")
    monkeypatch.setenv("SDA_PHASE_RECONCILE", "1")

    h = make_handler()
    gs = h.game_state
    ws = _FakeWS()
    asyncio.run(h.process_message(ws, json.dumps({"type": "nova_sessao"}), "c1"))
    asyncio.run(h.process_message(ws, json.dumps({
        "type": "set_seed", "direction": HORARIO, "locked": True}), "c1"))

    equivalente = {"cw": "horario", "ccw": "anti-horario"}
    spins = [17, 32, 5, 21, 26, 3]
    vistos = []

    for i, n in enumerate(spins):
        asyncio.run(h.process_message(ws, json.dumps({
            "type": "novo_resultado", "numero": n, "direcao": ANTI,
            "timestamp": 1_700_000_000_000 + i * 45_000, "trace_id": f"ctr-{i:03d}",
            "allNumbers": list(reversed(spins[: i + 1])),
        }), "c1"))

        overlay = gs.engine_overlay_fields()
        pa, sentido = overlay["phase_authority"], overlay["sentido"]
        assert equivalente[pa["direction"]] == sentido["next_direction"], (
            f"giro {i}: ping-pong — pa={pa['direction']} next={sentido['next_direction']}"
        )
        # A projeção segue determinística a partir da âncora do operador.
        assert pa["direction"] == (
            "cw" if project_phase(HORARIO, gs.seed_n, pa["spin_seq"]) == HORARIO else "ccw"
        )
        vistos.append(pa["spin_seq"])

    # Heurística de ACK do V2: `spin_seq` é o mesmo contador de `sentido.last_seq`,
    # cresce a cada giro aceito e nunca retrocede.
    assert vistos == sorted(vistos) and len(set(vistos)) == len(vistos), vistos
    assert gs.engine_overlay_fields()["sentido"]["last_seq"] == vistos[-1]
