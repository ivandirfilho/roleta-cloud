# Roleta Cloud - Repository Interface
# Interface abstrata para facilitar migração futura de banco de dados

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime

from .models import Decision, Session


class DecisionRepository(ABC):
    """
    Interface abstrata para repositório de decisões.
    
    Implementações:
    - SQLiteDecisionRepository (atual)
    - SurrealDecisionRepository (futuro)
    - IcebergDecisionRepository (futuro, cold storage)
    """
    
    # =========================================================================
    # CRUD de Decisões
    # =========================================================================
    
    @abstractmethod
    def save_decision(self, decision: Decision) -> int:
        """
        Salva uma nova decisão.
        
        Args:
            decision: Objeto Decision a ser salvo
            
        Returns:
            ID da decisão criada
        """
        pass
    
    @abstractmethod
    def update_result(self, decision_id: int, hit: bool, actual_number: int) -> None:
        """
        Atualiza o resultado de uma decisão.
        Chamado quando o próximo spin revela se acertamos.
        
        Args:
            decision_id: ID da decisão
            hit: True se acertou, False se errou
            actual_number: Número que realmente saiu
        """
        pass
    
    @abstractmethod
    def get_decision(self, decision_id: int) -> Optional[Decision]:
        """
        Busca uma decisão por ID.
        
        Args:
            decision_id: ID da decisão
            
        Returns:
            Decision ou None se não encontrada
        """
        pass
    
    @abstractmethod
    def get_decisions(
        self,
        session_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        final_action: Optional[str] = None,
        limit: int = 100
    ) -> List[Decision]:
        """
        Busca decisões com filtros.
        
        Args:
            session_id: Filtrar por sessão
            start_time: A partir de (datetime)
            end_time: Até (datetime)
            final_action: "APOSTAR" ou "PULAR"
            limit: Máximo de resultados
            
        Returns:
            Lista de decisões
        """
        pass
    
    @abstractmethod
    def get_last_decision_id(self, session_id: str) -> Optional[int]:
        """
        Retorna o ID da última decisão da sessão.
        Usado para atualizar resultado no próximo spin.
        
        Args:
            session_id: ID da sessão
            
        Returns:
            ID da última decisão ou None
        """
        pass
    
    # =========================================================================
    # CRUD de Sessões
    # =========================================================================
    
    @abstractmethod
    def create_session(self, session: Session) -> str:
        """
        Cria uma nova sessão.
        
        Args:
            session: Objeto Session
            
        Returns:
            ID da sessão
        """
        pass
    
    @abstractmethod
    def update_session(self, session: Session) -> None:
        """
        Atualiza estatísticas da sessão.
        
        Args:
            session: Objeto Session atualizado
        """
        pass
    
    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Busca sessão por ID.
        
        Args:
            session_id: ID da sessão
            
        Returns:
            Session ou None
        """
        pass
    
    @abstractmethod
    def end_session(self, session_id: str) -> None:
        """
        Marca sessão como finalizada.
        
        Args:
            session_id: ID da sessão
        """
        pass
    
    # =========================================================================
    # Analytics
    # =========================================================================
    
    @abstractmethod
    def get_stats(
        self,
        session_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Retorna estatísticas agregadas.
        
        Args:
            session_id: Filtrar por sessão (opcional)
            start_time: A partir de (opcional)
            end_time: Até (opcional)
            
        Returns:
            Dicionário com estatísticas
        """
        pass
    
    @abstractmethod
    def get_gale_stats(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna estatísticas por nível de gale.
        
        Args:
            session_id: Filtrar por sessão (opcional)
            
        Returns:
            Estatísticas por nível de gale
        """
        pass
    
    @abstractmethod
    def get_triple_rate_analysis(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Analisa eficácia do Triple Rate Advisor.
        
        Args:
            session_id: Filtrar por sessão (opcional)
            
        Returns:
            Análise do Triple Rate
        """
        pass
