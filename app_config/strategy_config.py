"""
QW-5: Carregador de configuração TOML da estratégia.

Permite tunar constantes sem redeploy. Reload é on-demand (`maybe_reload()`)
checando mtime — chamado de dentro de SDA17Strategy.analyze() no início de
cada spin (custo: 1 stat call ~ <0.1ms).

Compatibilidade:
- Python 3.11+: usa `tomllib` nativo (stdlib)
- Python 3.10-: requer `tomli` (em requirements.txt)
- Arquivo ausente ou TOML inválido: usa defaults embutidos (operação degradada
  mas segura — sistema NUNCA quebra por falta de config)

Thread-safety: leitura via snapshot imutável; reload sob lock.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore

logger = logging.getLogger(__name__)


# Defaults embutidos (cópia conservadora do strategy.toml — usados se arquivo ausente)
_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "sda17": {
        "bayesian_default": 10,
        "bayesian_warmup": 2,
        "offset_min": 7,
        "offset_max": 13,
        "sigmoid_k": 6,
        "sigmoid_scale": 2.0,
        "hit_tighten": 0.08,
        "miss_cross_rate": 0.3,
        "max_history": 24,
    },
    "sda17.minimizer": {
        "enabled": True,
        "window": 30,
        "warmup_n": 10,
        "threshold": 0.487,
        "stake_fraction": 0.10,
    },
    "sda17.stake_weight": {
        "enabled": True,
        "cap_upper": 1.5,
        "cap_lower": 0.3,
        "divisor": 0.472,
    },
    "sda17.mg_cap": {
        "enabled": True,
        "track_resets": True,
    },
    "sda17.hot_substitution": {
        "enabled": True,
        "cooldown_spins": 3,
    },
    "sda17.warmup_adaptive": {
        "enabled": True,
        "warmup_winning": 2,
        "warmup_losing": 5,
    },
    "sda17.drift_freeze": {
        "enabled": True,
        "window": 50,
        "threshold": 0.15,
        "freeze_spins": 5,
        "soft_reset_weight": 0.5,
    },
}


class StrategyConfig:
    """
    Loader thread-safe de config TOML com reload on-demand.

    Uso:
        cfg = StrategyConfig()                                  # carrega no construtor
        cfg.maybe_reload()                                      # opcional, no início do analyze()
        threshold = cfg.get("sda17.minimizer", "threshold")     # leitura snapshot
    """

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            path = Path(__file__).resolve().parent.parent / "config" / "strategy.toml"
        self.path = Path(path)
        self._mtime: float = 0.0
        self._lock = threading.RLock()
        self._snapshot: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in _DEFAULTS.items()}
        self.reload()

    # ------------------------------------------------------------------ #
    def reload(self) -> bool:
        """
        (Re)lê o arquivo TOML. Em caso de erro, mantém snapshot anterior e loga.
        Retorna True se reload foi bem-sucedido.
        """
        with self._lock:
            if not self.path.exists():
                logger.warning(
                    "[STRATEGY-CFG] arquivo não encontrado em %s — usando defaults embutidos",
                    self.path,
                )
                return False
            try:
                with open(self.path, "rb") as f:
                    raw = tomllib.load(f)
            except Exception as e:
                logger.error(
                    "[STRATEGY-CFG] TOML inválido (%s) — mantendo snapshot anterior",
                    e,
                )
                return False

            # Flatten dotted sections: {"sda17": {"minimizer": {...}}} → "sda17.minimizer"
            new_snapshot: Dict[str, Dict[str, Any]] = {}
            for top, body in raw.items():
                if not isinstance(body, dict):
                    continue
                # Coleta valores escalares no topo
                scalars = {k: v for k, v in body.items() if not isinstance(v, dict)}
                if scalars:
                    new_snapshot[top] = scalars
                # Recurse 1 nível (suficiente para nosso schema)
                for sub, sub_body in body.items():
                    if isinstance(sub_body, dict):
                        new_snapshot[f"{top}.{sub}"] = sub_body

            # Merge sobre defaults (mantém chaves ausentes)
            merged: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in _DEFAULTS.items()}
            for section, body in new_snapshot.items():
                if section not in merged:
                    merged[section] = {}
                merged[section].update(body)

            self._snapshot = merged
            try:
                self._mtime = self.path.stat().st_mtime
            except OSError:
                self._mtime = 0.0
            logger.info("[STRATEGY-CFG] reload OK (%d seções)", len(merged))
            return True

    # ------------------------------------------------------------------ #
    def maybe_reload(self) -> bool:
        """Recarrega APENAS se mtime mudou. Chamada barata (1 stat)."""
        try:
            m = self.path.stat().st_mtime
        except OSError:
            return False
        if m > self._mtime:
            return self.reload()
        return False

    # ------------------------------------------------------------------ #
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Leitura snapshot. Ex.: get('sda17.minimizer', 'enabled')."""
        with self._lock:
            sec = self._snapshot.get(section, {})
            if key in sec:
                return sec[key]
            # Fallback ao default embutido (não ao parâmetro `default` ainda)
            embed = _DEFAULTS.get(section, {})
            if key in embed:
                return embed[key]
            return default

    def section(self, section: str) -> Dict[str, Any]:
        """Retorna cópia da seção inteira (snapshot)."""
        with self._lock:
            sec = dict(self._snapshot.get(section, {}))
            for k, v in _DEFAULTS.get(section, {}).items():
                sec.setdefault(k, v)
            return sec


# Singleton global — instanciar 1x no boot
_global_cfg: Optional[StrategyConfig] = None


def get_strategy_config() -> StrategyConfig:
    global _global_cfg
    if _global_cfg is None:
        _global_cfg = StrategyConfig()
    return _global_cfg
