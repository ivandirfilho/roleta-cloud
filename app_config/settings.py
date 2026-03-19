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

settings = Settings()
