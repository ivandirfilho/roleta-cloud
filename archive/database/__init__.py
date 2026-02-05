# Roleta Cloud - Database Package
# Sistema de logging de decisões para análise posterior

from .models import Decision, Session, GaleWindow, WindowPlay
from .repository import DecisionRepository
from .sqlite_repo import SQLiteDecisionRepository

# Singleton para fácil acesso
_repository: DecisionRepository = None


def get_repository() -> DecisionRepository:
    """Retorna instância do repositório (singleton)."""
    global _repository
    if _repository is None:
        _repository = SQLiteDecisionRepository()
    return _repository


def init_database(db_path: str = None) -> None:
    """
    Inicializa o banco de dados.
    
    Args:
        db_path: Caminho para o arquivo SQLite (opcional)
    """
    global _repository
    _repository = SQLiteDecisionRepository(db_path)


__all__ = [
    "Decision",
    "Session",
    "GaleWindow",
    "WindowPlay",
    "DecisionRepository",
    "SQLiteDecisionRepository",
    "get_repository",
    "init_database"
]

