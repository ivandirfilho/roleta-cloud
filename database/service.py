# Roleta Cloud - Database Service

import logging
from typing import Dict, Optional, Any
from database import get_repository
from database.models import GaleWindow, WindowPlay, Decision, Session
from state.game import GameState

logger = logging.getLogger(__name__)

class DatabaseService:
    """
    Serviço para encapsular lógica de negócios relacionada ao banco de dados.
    Gerencia janelas de martingale e sessões.
    """

    def __init__(self):
        self.active_window_ids: Dict[str, Optional[int]] = {"cw": None, "ccw": None}
        # Inicializa janelas ativas
        self._init_active_window_ids()

    @property
    def repository(self):
        return get_repository()

    def _init_active_window_ids(self):
        """
        Restaura active_window_ids do banco de dados após restart do servidor.
        Chamado na inicialização para evitar janelas órfãs.
        """
        try:
            repo = self.repository
            for dir_key in ["cw", "ccw"]:
                window = repo.get_active_window(dir_key)
                if window:
                    self.active_window_ids[dir_key] = window.id
                    logger.info(f"[GALE_WINDOW] Restaurada janela ativa ID={window.id} dir={dir_key}")
        except Exception as e:
            logger.warning(f"Erro ao restaurar janelas ativas: {e}")

    def track_gale_window(
        self,
        game_state: GameState,
        direction: str,
        hit: bool,
        martingale_info: dict,
        pending: dict,
        force: int,
        numero: int,
        advice_confidence: str = "",
        advice_reason: str = "",
        sda_score: int = 0
    ) -> None:
        """
        Gerencia o tracking de janelas de Martingale no banco de dados.
        Chamado após cada atualização do martingale.
        """
        repo = self.repository

        # Normalizar direção
        dir_key = "cw" if direction in ("cw", "horario") else "ccw"

        # Obter ou criar janela ativa
        window_id = self.active_window_ids.get(dir_key)

        # Se é a primeira jogada da janela (window_count == 1), criar nova janela
        if martingale_info.get("window_count", 0) == 1:
            # Se tinha janela ativa anterior, fechar primeiro (caso edge)
            if window_id is not None:
                logger.warning(f"Fechando janela órfã {window_id} para {dir_key}")
                repo.close_gale_window(window_id, "orphan", 1)

            # Obter taxas atuais para ML features
            stats = game_state.get_performance_stats()
            sda_rate = stats.get(f"sda17_{dir_key}", {}).get("rate", 0)
            bet_rate = stats.get(f"bet_{dir_key}", {}).get("rate", 0)
            calibration = game_state.calibration_cw if dir_key == "cw" else game_state.calibration_ccw

            # Criar nova janela
            new_window = GaleWindow(
                direction=dir_key,
                gale_level=martingale_info.get("level_before", 1),
                sda17_rate_at_start=sda_rate,
                bet_rate_at_start=bet_rate,
                calibration_offset=calibration.offset if calibration else 0
            )
            window_id = repo.create_gale_window(new_window)
            self.active_window_ids[dir_key] = window_id
            logger.info(f"[GALE_WINDOW] Nova janela criada ID={window_id} dir={dir_key} level={new_window.gale_level}")

        # Adicionar play à janela ativa
        if window_id is not None:
            play = WindowPlay(
                window_id=window_id,
                play_number=martingale_info.get("window_count", 0),
                spin_number=numero,
                spin_direction=direction,
                spin_force=force,
                center_predicted=pending.get("center", 0),
                hit=hit,
                actual_number=numero,
                sda_score=sda_score,
                tr_confidence=advice_confidence,
                tr_reason=advice_reason
            )
            repo.add_window_play(play)
            logger.debug(f"[GALE_WINDOW] Play adicionado: window={window_id} play={play.play_number} hit={hit}")

        # Se teve transição de janela (5 plays completos), fechar
        transition = martingale_info.get("transition", "")
        if transition:
            if window_id is not None:
                # Determinar resultado
                if "SUCESSO" in transition:
                    result = "success"
                elif "SUBINDO" in transition:
                    result = "escalated"
                else:  # STOP
                    result = "stop"

                next_level = martingale_info.get("level_after", 1)
                repo.close_gale_window(window_id, result, next_level)
                logger.info(f"[GALE_WINDOW] Janela fechada ID={window_id} result={result} next_level={next_level}")

            # Limpar referência para nova janela
            self.active_window_ids[dir_key] = None

    def get_window_history(self) -> Dict[str, Any]:
        """Retorna histórico de janelas para ambas as direções."""
        repo = self.repository
        try:
            return {
                "cw": repo.get_window_history("cw", limit=5),
                "ccw": repo.get_window_history("ccw", limit=5)
            }
        except Exception as e:
            logger.warning(f"Erro ao obter window_history: {e}")
            return {"cw": [], "ccw": []}

    def create_session(self, session_id: str):
        """Cria uma nova sessão."""
        try:
            self.repository.create_session(Session(id=session_id))
        except Exception as e:
            logger.warning(f"Erro ao criar sessão no DB: {e}")

    def save_decision(self, decision: Decision) -> int:
        """Salva uma decisão."""
        return self.repository.save_decision(decision)

    def update_result(self, decision_id: int, hit: bool, actual_number: int):
        """Atualiza resultado de uma decisão."""
        self.repository.update_result(decision_id, hit, actual_number)

# Singleton
db_service = DatabaseService()
