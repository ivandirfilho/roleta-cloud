"""
Roleta Cloud - Teste do Core
=============================

Testa todos os cálculos do núcleo da roleta.
"""

import sys
sys.path.insert(0, '..')

from core import roulette, Direction, get_neighbors, calculate_target


def test_wheel_sequence():
    """Testa se a sequência da roda está correta"""
    print("📋 Testando sequência da roda...")
    
    # Primeiro e último
    assert roulette.WHEEL_SEQUENCE[0] == 0, "Primeiro número deve ser 0"
    assert roulette.WHEEL_SEQUENCE[-1] == 26, "Último número deve ser 26"
    assert len(roulette.WHEEL_SEQUENCE) == 37, "Deve ter 37 números"
    
    # Todos os números de 0-36 devem estar presentes
    assert set(roulette.WHEEL_SEQUENCE) == set(range(37)), "Deve conter todos números 0-36"
    
    print("   ✅ Sequência OK")


def test_positions():
    """Testa posições dos números"""
    print("📋 Testando posições...")
    
    # Zero está na posição 0
    assert roulette.get_position(0) == 0
    
    # 32 está na posição 1 (segundo número)
    assert roulette.get_position(32) == 1
    
    # Teste reverso
    assert roulette.get_number_at_position(0) == 0
    assert roulette.get_number_at_position(1) == 32
    
    print("   ✅ Posições OK")


def test_distance():
    """Testa cálculo de distância"""
    print("📋 Testando distância...")
    
    # Distância do 0 ao 32 (sentido horário) = 1
    dist = roulette.calculate_distance(0, 32, Direction.CLOCKWISE)
    assert dist == 1, f"Esperado 1, obtido {dist}"
    
    # Distância do 0 ao 26 (sentido horário) = 36 (quase volta completa)
    dist = roulette.calculate_distance(0, 26, Direction.CLOCKWISE)
    assert dist == 36, f"Esperado 36, obtido {dist}"
    
    # Distância do 0 ao 26 (anti-horário) = 1
    dist = roulette.calculate_distance(0, 26, Direction.COUNTERCLOCKWISE)
    assert dist == 1, f"Esperado 1, obtido {dist}"
    
    print("   ✅ Distância OK")


def test_neighbors():
    """Testa vizinhos"""
    print("📋 Testando vizinhos...")
    
    # Vizinhos do 0 com raio 2
    neighbors = roulette.get_neighbors(0, 2)
    assert len(neighbors) == 5, f"Esperado 5 vizinhos, obtido {len(neighbors)}"
    assert 0 in neighbors, "Centro deve estar nos vizinhos"
    assert 32 in neighbors, "32 (direita do 0) deve estar"
    assert 26 in neighbors, "26 (esquerda do 0) deve estar"
    
    print(f"   Vizinhos do 0 (raio 2): {neighbors}")
    print("   ✅ Vizinhos OK")


def test_target():
    """Testa cálculo de alvo"""
    print("📋 Testando cálculo de alvo...")
    
    # Do 0, andando 1 casa no sentido horário = 32
    target = roulette.calculate_target(0, 1, Direction.CLOCKWISE)
    assert target == 32, f"Esperado 32, obtido {target}"
    
    # Do 0, andando 2 casas no sentido horário = 15
    target = roulette.calculate_target(0, 2, Direction.CLOCKWISE)
    assert target == 15, f"Esperado 15, obtido {target}"
    
    # Do 0, andando 1 casa no sentido anti-horário = 26
    target = roulette.calculate_target(0, 1, Direction.COUNTERCLOCKWISE)
    assert target == 26, f"Esperado 26, obtido {target}"
    
    print("   ✅ Alvo OK")


def test_force_distance():
    """Testa distância circular de força"""
    print("📋 Testando distância de força...")
    
    # Distância entre força 1 e força 5 = 4
    dist = roulette.calculate_force_distance(1, 5)
    assert dist == 4, f"Esperado 4, obtido {dist}"
    
    # Distância entre força 1 e força 37 = 1 (circular)
    dist = roulette.calculate_force_distance(1, 37)
    assert dist == 1, f"Esperado 1 (37 e 1 são vizinhos), obtido {dist}"
    
    print("   ✅ Distância de força OK")


def test_visual_region():
    """Testa representação visual"""
    print("📋 Testando região visual...")
    
    visual = roulette.get_visual_region(17, 2)
    print(f"   Região visual do 17 (raio 2): {visual}")
    
    print("   ✅ Visual OK")


def run_all_tests():
    """Executa todos os testes"""
    print("\n" + "=" * 60)
    print("   🎰 ROLETA CLOUD - TESTE DO CORE")
    print("=" * 60 + "\n")
    
    test_wheel_sequence()
    test_positions()
    test_distance()
    test_neighbors()
    test_target()
    test_force_distance()
    test_visual_region()
    
    print("\n" + "=" * 60)
    print("   ✅ TODOS OS TESTES PASSARAM!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_all_tests()
