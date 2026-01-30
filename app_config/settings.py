from pathlib import Path
from typing import List, Set
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

    # Roulette Wheel Constants
    wheel_sequence: List[int] = [
        0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
        5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26
    ]
    red_numbers: Set[int] = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    black_numbers: Set[int] = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    base_dir: Path = BASE_DIR
    state_file: Path = BASE_DIR / "state.json"
    log_file: Path = BASE_DIR / "roleta.log"

    server: ServerSettings = Field(default_factory=ServerSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    game: GameSettings = Field(default_factory=GameSettings)

settings = Settings()
