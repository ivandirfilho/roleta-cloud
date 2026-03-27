"""Test script to validate database schema creation and integrity."""
import sqlite3
import tempfile
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_schema_creation():
    """Testa criação automática do schema via SQLiteDecisionRepository."""
    from database.sqlite_repo import SQLiteDecisionRepository
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_path = f.name
    
    try:
        repo = SQLiteDecisionRepository(db_path=temp_path)
        conn = sqlite3.connect(temp_path)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        
        assert 'sessions' in tables, f"'sessions' não encontrada. Tabelas: {tables}"
        assert 'decisions' in tables, f"'decisions' não encontrada. Tabelas: {tables}"
        assert 'gale_windows' in tables, f"'gale_windows' não encontrada. Tabelas: {tables}"
        assert 'window_plays' in tables, f"'window_plays' não encontrada. Tabelas: {tables}"
        
        # Verificar coluna sda_centers existe
        cols = [r[1] for r in conn.execute("PRAGMA table_info(decisions)").fetchall()]
        assert 'sda_centers' in cols, f"'sda_centers' não encontrada. Colunas: {cols}"
        
        conn.close()
        # Fechar conexão interna do repo para liberar o arquivo
        del repo
        print("✅ test_schema_creation PASSED")
    finally:
        try:
            os.unlink(temp_path)
        except PermissionError:
            pass  # Windows file lock — arquivo será limpo pelo OS


if __name__ == "__main__":
    test_schema_creation()
    print("Todos os testes de DB passaram.")
