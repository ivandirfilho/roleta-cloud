from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).parent.parent

class ServerSettings(BaseSettings):
    host: str = Field(default="0.0.0.0", validation_alias="WS_HOST")
    port: int = Field(default=8765, validation_alias="WS_PORT")
    ssl_enabled: bool = Field(default=False, validation_alias="SSL_ENABLED")
    ssl_cert: str = Field(default="/etc/letsencrypt/live/roleta.seudominio.com/fullchain.pem", validation_alias="SSL_CERT")
    ssl_key: str = Field(default="/etc/letsencrypt/live/roleta.seudominio.com/privkey.pem", validation_alias="SSL_KEY")

class AuthSettings(BaseSettings):
    enabled: bool = Field(default=False, validation_alias="AUTH_ENABLED")
    keycloak_url: str = Field(default="http://localhost:8080", validation_alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="roleta", validation_alias="KEYCLOAK_REALM")
    keycloak_client_id: str = Field(default="roleta-cloud", validation_alias="KEYCLOAK_CLIENT_ID")

class GameSettings(BaseSettings):
    max_timeline_size: int = 45
    sda_forces_analyzed: int = 4

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    base_dir: Path = BASE_DIR
    state_file: Path = BASE_DIR / "state.json"
    log_file: Path = BASE_DIR / "roleta.log"

    server: ServerSettings = Field(default_factory=ServerSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    game: GameSettings = Field(default_factory=GameSettings)

    # S-STRAT-13.1: opt-in para auto-promote do shadow grid (default OFF).
    shadow_auto_promote_enabled: bool = Field(default=False, validation_alias="SHADOW_AUTO_PROMOTE_ENABLED")

settings = Settings()


def profit_cut_v1_enabled() -> bool:
    """B5 CUT-POLICY v1 (12/06) — única política consistente no walk-forward
    (treino −1.33→−0.19, teste −0.78→−0.19 por aposta): score>=4, gale<=2,
    nunca N=19 (fallback vira N=21). Default ON; desligar com PROFIT_CUT_V1=0.

    Lido por chamada (não cacheado) para permitir toggle em testes.
    """
    import os
    return os.environ.get("PROFIT_CUT_V1", "1").strip().lower() not in ("0", "false", "off")


def profit_stop_loss_units() -> float:
    """B5 — stop-loss automático por sessão (unidades). 0 desliga. Default 30."""
    import os
    try:
        return float(os.environ.get("PROFIT_STOP_LOSS_UNITS", "30"))
    except ValueError:
        return 30.0


def region_shift_v1_enabled() -> bool:
    """SV-01 (12/06) — Modelo Universal M5: atuador de shift por região.

    Vencedor do replay causal (2762 decisões, analise_12_junho.md §6):
    shift_C1 = clamp(round(−EMA_região·0.5), ±4) + satélites relativos ±2.
    Default ON; desligar com REGION_SHIFT_V1=0.
    """
    import os
    return os.environ.get("REGION_SHIFT_V1", "1").strip().lower() not in ("0", "false", "off")


def sigmoid_satellites_enabled() -> bool:
    """SV-02 (12/06) — sigmoid dos satélites APOSENTADO em produção.

    Replay causal: offsets presos no prior e M4 (sigmoid em C1) destrutivo;
    o M5 assume a adaptação. Default OFF; religar com SDA_SIGMOID_SATELLITES=1
    (rollback trivial — estado continua persistido).
    """
    import os
    return os.environ.get("SDA_SIGMOID_SATELLITES", "0").strip().lower() in ("1", "true", "on")
