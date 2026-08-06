"""SPR-V1 / DIR22 — métrica de ALTERNÂNCIA + matriz de gap (B2/min_overlap).

A fase é um TOGGLE: giros consecutivos alternam de sentido. Dois giros seguidos com o
MESMO sentido, fora de gap/reset, denunciam fase corrompida — é o sintoma que o
operador vê como "está apostando no lado errado". Puramente observável (`
alternancia_violada_total`), atrás de `SDA_PHASE_ALT_METRIC` (default OFF).

Cobre também a matriz de recuperação de gap por `k` com `min_overlap`, incluindo a
fronteira: com janela 12 e `min_overlap=3`, gaps até k=9 são recuperáveis; acima
disso a evidência acaba e `phase_uncertain` é a resposta CORRETA.
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app_config.settings import phase_alt_metric_enabled, phase_min_overlap
from state.game import GameState
from state.phase import HORARIO, ANTI, phase_advance, phase_advance_ex, reconcile_shift


def test_flags_default_off(monkeypatch):
    monkeypatch.delenv("SDA_PHASE_ALT_METRIC", raising=False)
    monkeypatch.delenv("SDA_PHASE_MIN_OVERLAP", raising=False)
    assert phase_alt_metric_enabled() is False
    assert phase_min_overlap() == 0
    monkeypatch.setenv("SDA_PHASE_ALT_METRIC", "1")
    monkeypatch.setenv("SDA_PHASE_MIN_OVERLAP", "3")
    assert phase_alt_metric_enabled() is True
    assert phase_min_overlap() == 3


# ------------------------------------------------------- matriz de gap por k

JANELA = 12
PREV = [4, 19, 15, 32, 0, 26, 3, 35, 12, 28, 7, 29, 18, 22, 9, 31]
NOVOS = [40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51]


def _janela(k: int):
    """`allNumbers` (12) com `k` números novos na frente e o resto vindo de PREV."""
    return (NOVOS[:k] + PREV)[:JANELA]


@pytest.mark.parametrize("k", list(range(0, 12)))
def test_matriz_gap_baseline_min_overlap_zero(k):
    """min_overlap=0 (legado): aceita QUALQUER k com 1 número coincidente."""
    gap, inter, uncertain = phase_advance(PREV, _janela(k))
    if k == 0:
        assert (gap, uncertain) == (0, False)
    else:
        assert uncertain is False
        assert gap == k - 1
        assert inter == list(reversed(NOVOS[1:k]))


@pytest.mark.parametrize("k", list(range(0, 12)))
def test_matriz_gap_com_min_overlap_3(k):
    """FRONTEIRA: `m = min(len(prev), 12 - k) >= 3` ⟺ `k <= 9`.

    Até k=9 o gap é recuperado; de k=10 em diante sobram <3 números coincidentes e o
    servidor prefere `phase_uncertain` (pedir resync) a inventar giros — o
    comportamento CORRETO, não uma regressão.
    """
    gap, inter, uncertain, ambiguo = phase_advance_ex(PREV, _janela(k), 3)
    if k <= 9:
        assert uncertain is False, f"k={k} deveria ser recuperavel"
        assert ambiguo is False
        assert gap == max(0, k - 1)
    else:
        assert uncertain is True, f"k={k} nao deveria ser aceito com evidencia < 3"
        assert ambiguo is True
        assert gap == 0


def test_k_maximo_recuperavel_e_9():
    """Documenta o número que vai para o Log/ADENDO."""
    recuperaveis = [
        k for k in range(0, 12)
        if phase_advance_ex(PREV, _janela(k), 3)[2] is False
    ]
    assert max(recuperaveis) == 9


def test_ambiguidade_em_sequencia_periodica():
    """`prev=[1,2,1,2]` casa em k=0 E k=2 — o "primeiro match" seria um chute. Com
    evidência mínima exigida, o servidor recusa em vez de escolher."""
    prev = [1, 2, 1, 2]
    new = [1, 2, 1, 2, 1, 2]
    k, matched = reconcile_shift(prev, new)
    assert (k, matched) == (0, True)          # legado: primeiro match, sem questionar
    _, _, uncertain, ambiguo = phase_advance_ex(prev, new, 3)
    assert (uncertain, ambiguo) == (True, True)


def test_min_overlap_nao_afeta_casos_de_borda_vazios():
    """`new` vazio (nada a reconciliar) e `prev` vazio (primeiro giro) NÃO podem ser
    barrados por falta de evidência — não há histórico contra o que comparar."""
    assert phase_advance_ex([1, 2, 3], [], 3) == (0, [], False, False)
    assert phase_advance_ex([], [5, 6], 3) == (0, [], False, False)


# --------------------------------- min_overlap: exigência limitada pela evidência
# REGRESSÃO (code-review B2): `m` nunca passa de `min(len(prev), len(new))`. Exigir
# `min_overlap=3` quando só existem 1-2 números de histórico tornava a condição
# INSATISFAZÍVEL e transformava um alinhamento perfeito e ÚNICO em `phase_uncertain`
# — que aciona a DIR17 e re-ancora a fase na direção do CLIENTE, exatamente o vetor
# que o `min_overlap` existe para fechar. Acontecia nos 2 primeiros giros depois de
# TODO `nova_sessao` (o `_phase_results` acabou de ser zerado) e com janelas curtas.

@pytest.mark.parametrize("prev,new,k_esperado", [
    ([17], [32, 17], 1),                       # 1º giro após reset: só 1 de evidência
    ([32, 17], [5, 32, 17], 1),                # 2º giro: 2 de evidência
    ([17], [17], 0),                           # sem giro novo, evidência 1
    ([32, 17], [9, 5, 32, 17], 2),             # gap de 1 com histórico curto
])
def test_min_overlap_nao_exige_mais_evidencia_do_que_pode_existir(prev, new, k_esperado):
    gap, _inter, uncertain, ambiguo = phase_advance_ex(prev, new, 3)
    assert (uncertain, ambiguo) == (False, False), (prev, new)
    assert gap == max(0, k_esperado - 1)
    # e o veredito é o MESMO do caminho legado, que também acertava estes casos.
    assert reconcile_shift(prev, new, 20, 3) == (k_esperado, True)


def test_min_overlap_ainda_barra_quando_a_evidencia_existia_e_nao_bastou():
    """O teto NÃO desliga a regra: com prev/new longos o bastante, exigir 3 continua
    valendo — só o que era impossível de satisfazer deixou de ser exigido."""
    prev = [5, 32, 17]
    new = [21, 1, 2, 3, 4, 6, 7, 8, 9, 5]      # casa só em k=9, com m=1 de 3 possíveis
    _gap, _inter, uncertain, ambiguo = phase_advance_ex(prev, new, 3)
    assert (uncertain, ambiguo) == (True, True)


def test_teto_do_min_overlap_nao_afrouxa_a_fronteira_k9():
    """Com histórico cheio (16) e janela 12 o teto é inerte: eff = min(3,16,12) = 3."""
    for k in range(0, 12):
        assert phase_advance_ex(PREV, _janela(k), 3)[2] is (k > 9)


def test_reconcile_shift_min_overlap_zero_e_byte_identico():
    """INV ADITIVO: com min_overlap=0 o caminho é exatamente o legado."""
    for k in range(0, 12):
        new = _janela(k)
        assert reconcile_shift(PREV, new) == reconcile_shift(PREV, new, 20, 0)


# ------------------------------------------------------------- handler (E2E)

class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


@pytest.fixture()
def handler(tmp_path, monkeypatch):
    import database
    from app_config.settings import settings
    from strategies.sda17 import SDA17Strategy
    from server import message_handler as mh_mod
    from server.message_handler import MessageHandler

    database.init_database(str(tmp_path / "d.db"))
    monkeypatch.setattr(settings, "state_file", tmp_path / "state.json")
    monkeypatch.setattr(mh_mod.db_service, "save_decision", lambda d: 1)
    monkeypatch.setattr(
        mh_mod.connection_manager, "broadcast",
        MagicMock(side_effect=lambda *a, **k: asyncio.sleep(0)),
    )
    monkeypatch.setattr(mh_mod.connection_manager, "get_role", lambda cid: "master")
    monkeypatch.setenv("SDA_PHASE_RECONCILE", "1")
    return MessageHandler(
        game_state=GameState(), strategy=SDA17Strategy(),
        state_lock=asyncio.Lock(), configs_path=str(tmp_path / "cfg"),
    )


def _spin(handler, ws, i, numero, direcao, all_numbers):
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "novo_resultado", "numero": numero, "direcao": direcao,
        "timestamp": 1_700_000_000_000 + i * 45_000, "trace_id": f"t-{i:03d}",
        "allNumbers": all_numbers,
    }), "c1"))


def test_alternancia_ok_nao_incrementa(handler, monkeypatch):
    from state import phase_metrics
    monkeypatch.setenv("SDA_PHASE_ALT_METRIC", "1")
    phase_metrics.reset()
    ws = _FakeWS()
    spins = [17, 32, 5, 21]
    for i, n in enumerate(spins):
        _spin(handler, ws, i, n, HORARIO if i % 2 == 0 else ANTI,
              list(reversed(spins[: i + 1])))
    assert phase_metrics.snapshot()["alternancia_violada_total"] == 0
    phase_metrics.reset()


def test_alternancia_violada_incrementa(handler, monkeypatch):
    """Dois giros seguidos no mesmo sentido, sem gap: fase corrompida."""
    from state import phase_metrics
    monkeypatch.setenv("SDA_PHASE_ALT_METRIC", "1")
    phase_metrics.reset()
    ws = _FakeWS()
    spins = [17, 32, 5]
    for i, n in enumerate(spins):
        _spin(handler, ws, i, n, HORARIO, list(reversed(spins[: i + 1])))
    assert phase_metrics.snapshot()["alternancia_violada_total"] >= 1
    phase_metrics.reset()


def test_flag_off_nao_mede(handler, monkeypatch):
    from state import phase_metrics
    monkeypatch.setenv("SDA_PHASE_ALT_METRIC", "0")
    phase_metrics.reset()
    ws = _FakeWS()
    spins = [17, 32, 5]
    for i, n in enumerate(spins):
        _spin(handler, ws, i, n, HORARIO, list(reversed(spins[: i + 1])))
    assert phase_metrics.snapshot()["alternancia_violada_total"] == 0
    phase_metrics.reset()


def test_gap_recuperado_nao_gera_falso_positivo(handler, monkeypatch):
    """Um gap de k giros consome k trocas de fase: comparar com o sentido
    IMEDIATAMENTE anterior acusaria violação onde não há."""
    from state import phase_metrics
    monkeypatch.setenv("SDA_PHASE_ALT_METRIC", "1")
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", "1")
    phase_metrics.reset()
    ws = _FakeWS()
    spins = [17, 32, 5, 21, 0, 26, 3]
    escondido = 3
    for i, n in enumerate(spins):
        if i == escondido:
            continue
        # gap de 1 giro ⇒ o sentido "pula" um toggle e volta a coincidir.
        _spin(handler, ws, i, n, HORARIO if i % 2 == 0 else ANTI,
              list(reversed(spins[: i + 1])))
    snap = phase_metrics.snapshot()
    assert snap["gap_recuperado_total"] >= 1
    assert snap["alternancia_violada_total"] == 0, snap
    phase_metrics.reset()


def test_phase_uncertain_nao_gera_falso_positivo(handler, monkeypatch):
    """Sem alinhamento não há expectativa de alternância a violar."""
    from state import phase_metrics
    monkeypatch.setenv("SDA_PHASE_ALT_METRIC", "1")
    phase_metrics.reset()
    ws = _FakeWS()
    _spin(handler, ws, 0, 17, HORARIO, [17])
    _spin(handler, ws, 1, 32, HORARIO, [32, 99, 98, 97])   # mesa nova: sem overlap
    snap = phase_metrics.snapshot()
    assert snap["phase_uncertain_total"] >= 1
    assert snap["alternancia_violada_total"] == 0, snap
    phase_metrics.reset()


def test_metrica_ambigua_incrementa_no_handler(handler, monkeypatch):
    """A métrica só é honesta se HOUVE alinhamento e a evidência é que não bastou.

    Os 3 primeiros giros constroem `_phase_results = [5, 32, 17]` (evidência 3, o
    máximo exigível). O 4º traz uma janela que casa APENAS em k=9, com m=1 — havia
    alinhamento, a evidência era 1/3: ambíguo, `phase_uncertain` e nenhum giro
    inventado. (Antes do teto de evidência, os giros 2 e 3 já falhavam aqui — ver
    `test_min_overlap_nao_exige_mais_evidencia_do_que_pode_existir`.)
    """
    from state import phase_metrics
    monkeypatch.setenv("SDA_PHASE_MIN_OVERLAP", "3")
    phase_metrics.reset()
    ws = _FakeWS()
    base = [17, 32, 5]
    for i, n in enumerate(base):
        _spin(handler, ws, i, n, HORARIO if i % 2 == 0 else ANTI,
              list(reversed(base[: i + 1])))
    assert phase_metrics.snapshot()["phase_ambiguo_total"] == 0, "buildup limpo"
    _spin(handler, ws, 3, 21, HORARIO, [21, 1, 2, 3, 4, 6, 7, 8, 9, 5])
    snap = phase_metrics.snapshot()
    assert snap["phase_ambiguo_total"] == 1, snap
    assert snap["phase_uncertain_total"] >= 1, snap
    phase_metrics.reset()
