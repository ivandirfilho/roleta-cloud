"""Pacote de políticas de staking (flat/kelly) — spec flat_kelly_junho.md §6.

Default de produção continua ``gale`` (ver ``app_config.settings.staking_mode``);
estes modos só são acionados sob ``SDA_STAKING_MODE in {flat, kelly}``.
"""

from .policy import compute_staking, flat_stake, kelly_stake  # noqa: F401
