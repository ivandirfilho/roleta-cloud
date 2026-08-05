"""DIR9 (sentido-fase): bloco `sentido` no canal por-giro `sugestao`.

Antes do fix: o bloco `sentido{last_seq,next_direction,locked,source,resync_advised,stats}`
viajava apenas no `state_sync` (broadcast 1s) e no `trace`. A resposta `sugestao`
(canal por-giro) NÃO carregava o bloco — cliente etiquetava com fase 1 tick atrasada.

Depois: handler une `self._engine_overlay_fields()` (privado, com _cs_meta/_bg_meta) +
`self.game_state.engine_overlay_fields()` (público, com sentido). Aditivo, sem flag.
"""

from state.game import GameState
from state.phase import HORARIO, ANTI


def test_engine_overlay_fields_inclui_sentido():
    """Bloco sentido publicado pela fonte unica (game_state.engine_overlay_fields)."""
    gs = GameState()
    gs.spin_seq = 7
    gs.seed_parity = HORARIO
    gs.seed_n = 0
    gs.direction_source = "operator_seed"
    gs.direction_locked = False
    out = gs.engine_overlay_fields()
    assert "sentido" in out
    sentido = out["sentido"]
    assert sentido["last_seq"] == 7
    assert sentido["source"] == "operator_seed"
    assert sentido["locked"] is False
    assert "stats" in sentido
    # SPR-V1 (05/08): 4 chaves novas (buffer/ambiguidade/plausibilidade/alternancia).
    assert set(sentido["stats"].keys()) == {
        "gap_recuperado_total", "phase_uncertain_total", "direction_divergence_total",
        "phase_buffer_missing_total", "phase_ambiguo_total",
        "spin_implausivel_total", "alternancia_violada_total",
    }


def test_overlay_uniao_complementar():
    """
    DIR9 garante que as DUAS fontes sao COMPLEMENTARES (nao redundantes):
    - _engine_overlay_fields (handler): c_selection, force17, block_gale, bet_gate, ultimo_acerto
    - engine_overlay_fields (gamestate): sentido (+ outros aditivos)

    O teste simula o merge feito no handler em :1268-1278.
    """
    gs = GameState()
    gs.spin_seq = 3
    gs.seed_parity = ANTI

    # GameState side (DIR5+):
    gs_out = gs.engine_overlay_fields()
    # Handler side (simulado vazio aqui — _cs_meta/_bg_meta default None):
    handler_out = {}  # sem motor ativo neste fixture

    merged = {}
    merged.update(handler_out)
    merged.update(gs_out)

    # Sentido vem do GameState (unico responsavel pela fase):
    assert merged["sentido"]["last_seq"] == 3
    # Nao tem c_selection nem block_gale porque o motor nao foi rodado:
    assert "c_selection" not in merged
