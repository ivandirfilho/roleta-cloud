"""Tests for bug fixes from resolucao_bugs_28_03.md"""
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import deque
from state.timeline import Timeline
from state.game import GameState, MartingaleState
from state.bet_advisor import TripleRateAdvisor
from strategies.sda17 import SDA17Strategy
from core.roulette import roulette

WHEEL = roulette.WHEEL_SEQUENCE


def test_sda17_coverage_always_ge_18():
    """BUG-28-04: Triple Focus deve gerar >= 18 números em qualquer cenário."""
    strategy = SDA17Strategy()
    
    # Edge case: forças extremas que causam overlap máximo
    edge_cases = [
        [1, 1, 1, 1, 1, 1, 1],      # Todas forças = 1 (centros colapsam)
        [36, 36, 36, 36, 36, 36, 36], # Todas forças = 36 (quase volta completa)
        [1, 37, 1, 37, 1, 37, 1],     # Alternância extrema
        [18, 18, 18, 18, 18],          # Metade da roda
        [5, 10, 15, 20, 25, 30, 35],  # Espalhadas
    ]
    
    for forces in edge_cases:
        tl = Timeline("cw")
        for f in forces:
            tl.add(f)
        result = strategy.analyze(tl, 0, WHEEL, calibration=0)
        if result.should_bet:
            assert len(result.numbers) >= 18, (
                f"Coverage {len(result.numbers)} < 18 com forces={forces}"
            )
    print("✅ test_sda17_coverage_always_ge_18 PASSED")


def test_c4_rate_uses_bet_performance():
    """BUG-28-03: get_bet_c4_rate() deve usar performance_bet, não sda17."""
    gs = GameState()
    gs.last_direction = "horario"
    
    # Cenário: sda17 tem 2/4 hits, bet tem 4/4 hits
    gs.performance_sda17_ccw = deque([True, False, True, False], maxlen=12)
    gs.performance_bet_ccw = deque([True, True, True, True], maxlen=12)
    
    # get_bet_advice usa sda17 (para Kill Switch)
    advice = gs.get_bet_advice(sda_score=3)
    assert advice.c4_rate == 0.5, f"Advisor c4 should be 0.5, got {advice.c4_rate}"
    
    # get_bet_c4_rate usa performance_bet (para SmartGale)
    bet_c4 = gs.get_bet_c4_rate()
    assert bet_c4 == 1.0, f"Bet c4 should be 1.0, got {bet_c4}"
    
    print("✅ test_c4_rate_uses_bet_performance PASSED")


def test_always_bet_when_timeline_has_data():
    """BUG-28-01: Engine deve apostar quando timeline > 0 (mesmo SDA insuficiente)."""
    from core.engine import GameEngine
    
    gs = GameState()
    strategy = SDA17Strategy()
    engine = GameEngine(gs, strategy)
    
    # Spin 1: define last_number, last_direction="horario"
    engine.process_spin(17, "horario")
    # Spin 2: same direction → adds force to timeline_cw
    engine.process_spin(25, "horario")
    # Spin 3: opposite direction → target_timeline = cw (que tem 1 força)
    # SDA will have insufficient forces (1 < min_forces=3) → should_bet=False
    # But target_timeline.size=1 > 0 → fallback G1
    decision3 = engine.process_spin(10, "anti-horario")
    
    assert decision3.acao == "APOSTAR", (
        f"Esperado APOSTAR com timeline > 0, obteve {decision3.acao}: {decision3.action_reason}"
    )
    assert decision3.gale_level == 1, f"Fallback deve ser G1, obteve G{decision3.gale_level}"
    
    print("✅ test_always_bet_when_timeline_has_data PASSED")


def test_pular_only_with_empty_timeline():
    """BUG-28-01: PULAR só deve ocorrer com timeline completamente vazia."""
    from core.engine import GameEngine
    
    gs = GameState()
    strategy = SDA17Strategy()
    engine = GameEngine(gs, strategy)
    
    # Primeiro spin: timeline está vazia, sem last_direction
    decision = engine.process_spin(17, "horario")
    # Neste caso target_timeline é ccw (oposta), que está vazia → PULAR é aceitável
    # Mas last_direction ainda não existia (primeiro spin), então target_timeline.size = 0
    assert decision.acao == "PULAR", f"Primeiro spin deve PULAR (timeline vazia), obteve {decision.acao}"
    
    print("✅ test_pular_only_with_empty_timeline PASSED")


def test_timeline_add_invalid_force():
    """BUG-28-11: Timeline.add() deve clampar force para [1, 37]."""
    tl = Timeline("cw")
    
    tl.add(0)   # Abaixo do mínimo → clamped para 1
    assert list(tl.forces)[0] == 1, f"Force 0 deveria virar 1, obteve {list(tl.forces)[0]}"
    
    tl.add(50)  # Acima do máximo → clamped para 37
    assert list(tl.forces)[0] == 37, f"Force 50 deveria virar 37, obteve {list(tl.forces)[0]}"
    
    tl.add(18)  # Normal → sem alteração
    assert list(tl.forces)[0] == 18
    
    print("✅ test_timeline_add_invalid_force PASSED")


def test_state_load_corrupted_json():
    """BUG-28-06: Load de state.json corrompido deve logar e criar backup."""
    from pathlib import Path
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        f.write("{invalid json content!!!")
        temp_path = f.name
    
    try:
        gs = GameState.load(Path(temp_path))
        # Deve retornar estado limpo (não crashar)
        assert gs.last_number == 0
        assert gs.timeline_cw.size == 0
        
        # Deve ter criado backup
        backup_path = temp_path + '.corrupted'
        assert os.path.exists(backup_path), "Backup do state corrompido não foi criado"
        
        # Cleanup backup
        os.unlink(backup_path)
        print("✅ test_state_load_corrupted_json PASSED")
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def test_foreign_key_constraint():
    """BUG-28-05: FK deve estar ativa, rejeitando referências inválidas."""
    from database.sqlite_repo import SQLiteDecisionRepository
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_path = f.name
    
    try:
        repo = SQLiteDecisionRepository(db_path=temp_path)
        conn = repo._get_connection()
        
        # Verificar que FK está ON
        fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk_status == 1, f"foreign_keys deveria ser 1, obteve {fk_status}"
        
        conn.close()
        del repo
        print("✅ test_foreign_key_constraint PASSED")
    finally:
        try:
            os.unlink(temp_path)
        except PermissionError:
            pass


def test_martingale_all_levels_valid():
    """SmartGaleV4 deve retornar apenas níveis 1, 2 ou 3."""
    mg = MartingaleState()
    
    for score in range(1, 7):
        for c4 in [0.0, 0.25, 0.5, 0.75, 1.0]:
            for consec in range(5):
                mg.consecutive_hits = consec
                mg.level = max(1, min(3, consec))
                result = mg.get_gale(score=score, c4_rate=c4)
                assert result in (1, 2, 3), f"Gale inválido: {result} (score={score}, c4={c4}, consec={consec})"
    
    print("✅ test_martingale_all_levels_valid PASSED")


def test_drift_detection_correct_order():
    """BUG-28-12: Drift deve usar os 3 mais recentes (idx 0, 1, 2)."""
    strategy = SDA17Strategy()
    
    # Tendência crescente nos 3 mais recentes: 10, 8, 6 (idx 0, 1, 2)
    forces = [10, 8, 6, 4, 2, 1, 1]
    _, info = strategy._predict_robust(forces)
    
    # drift_adj deve ser positivo (tendência de aumento)
    assert info["drift"] > 0, f"Drift deveria ser > 0 com tendência crescente, obteve {info['drift']}"
    
    # Tendência decrescente: 2, 5, 10
    forces2 = [2, 5, 10, 15, 20, 25, 30]
    _, info2 = strategy._predict_robust(forces2)
    assert info2["drift"] < 0, f"Drift deveria ser < 0 com tendência decrescente, obteve {info2['drift']}"
    
    print("✅ test_drift_detection_correct_order PASSED")


if __name__ == "__main__":
    test_sda17_coverage_always_ge_18()
    test_c4_rate_uses_bet_performance()
    test_always_bet_when_timeline_has_data()
    test_pular_only_with_empty_timeline()
    test_timeline_add_invalid_force()
    test_state_load_corrupted_json()
    test_foreign_key_constraint()
    test_martingale_all_levels_valid()
    test_drift_detection_correct_order()
    print("\n🎉 Todos os testes de bug fixes passaram!")
