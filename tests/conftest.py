"""Roleta Cloud - Configuração de Testes"""
import os
import sys
from pathlib import Path

# Garantir que o diretório raiz do projeto está no PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

# B5 CUT-POLICY v1 (12/06): default OFF na suite — os testes legados validam
# a mecânica subjacente (escalação G3, fallback N=19 etc.). Os testes da
# policy (test_b1_b2_b5_12_06.py) setam PROFIT_CUT_V1 explicitamente.
os.environ.setdefault("PROFIT_CUT_V1", "0")
os.environ.setdefault("PROFIT_STOP_LOSS_UNITS", "0")
