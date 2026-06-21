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


def geometry_v2_enabled() -> bool:
    """REGRA 13/06 — Geometria V2 (fat-SAT + offsets-KDE por sentido).

    Backtest de DECISÃO (evolution_sim_2026 run_decision, 2762 decisões,
    vs P0-LIVE 7+5+5@10+M5): P2 = 3+7+7 (raios 1/3/3), satélites nos PICOS
    de densidade do erro de força do PRÓPRIO sentido (KDE causal das últimas
    jogadas) + M5 C1-shift mantido. cw vira EV-positiva (EVcov −0.08→+0.34) e
    ccw melhora (−1.42→−0.92, saldo +16/+19), passando walk-forward nos DOIS
    sentidos. Default ON; rollback trivial com SDA_GEOMETRY_V2=0 (estado
    region_err_hist continua persistido).
    """
    import os
    return os.environ.get("SDA_GEOMETRY_V2", "1").strip().lower() not in ("0", "false", "off")


def sat_asym_enabled() -> bool:
    """V3 (13/06) — raios de satélite ASSIMÉTRICOS adaptativos por sentido.

    Backtest causal: satélite GORDO (raio 4) no lado mais denso do erro do
    sentido + MAGRO (raio 2) no outro (N=17 mantido) acerta +0.4–0.6pp e
    melhora o EVcov out-of-sample nos 2 sentidos vs V2 simétrica. Refina a V2;
    default ON, rollback SDA_SAT_ASYM=0 (volta a 3/3 simétrico).
    """
    import os
    return os.environ.get("SDA_SAT_ASYM", "1").strip().lower() not in ("0", "false", "off")


def strategy_regions_v4_enabled() -> bool:
    """V4 (13/06) — Refatoração de regiões: 3 regiões DISJUNTAS de 7 = 21 distintos.

    C1 mantém o critério atual (força prevista + shift M5), raio 3. C2 = gravidade
    circular sobre as 4 últimas forças fora do alvo de C1. C3 = zona menos visitada
    (heatmap) dos 5 últimos resultados. Composição C1→C2→C3 sem sobreposição
    (centros a >=7 casas) garante 21 números. Mutuamente exclusiva com a geometria
    V2/V3 (quando V4 ON, ignora offsets-KDE/raios assimétricos/shift dos satélites;
    mantém o shift M5 de C1). Default OFF; ligar com SDA_REGIONS_V4=1. Spec/auditoria:
    refatoracao_estrategica_13_06.md.
    """
    import os
    return os.environ.get("SDA_REGIONS_V4", "0").strip().lower() in ("1", "true", "on")


def staking_mode() -> str:
    """Seletor de staking (spec flat_kelly_junho.md §RN-1).

    Enum de 3 valores via env SDA_STAKING_MODE: "gale" (default — comportamento
    atual byte-idêntico), "flat" (stake constante U·N por sentido) ou "kelly"
    (Kelly fracionário por sentido). Valor inválido cai em "gale" (fail-safe).

    Lido por chamada (não cacheado) para permitir toggle em testes/runtime.
    """
    import os
    v = os.environ.get("SDA_STAKING_MODE", "gale").strip().lower()
    return v if v in ("gale", "flat", "kelly", "block_gale") else "gale"


# ---------- SP-IMPL (16/06): motores C1/C2 variável + Block-Gale (default OFF) ----------

def bet_pair_mode() -> str:
    """Cobertura da aposta (implantação aposta 14#/17#).

    Enum via env SDA_BET_PAIR: "full" (default do código — 3 centros, byte-idêntico),
    "c2c3"/"c1c3" (par ESTÁTICO fixo {C2,C3} ou {C1,C3} = 14#, sem voto — PRODUÇÃO
    rodava "c2c3" desde 17/06), "var_c1c2_c3" (voto C1/C2 móvel pelas últimas 3 não-C3
    + C3 fixo — DESATIVADO por resultados desfavoráveis), "force17" (C1=ForceLast +
    geometria 17# = C2-7 ∪ C3-5 ∪ C1-5; 3 regiões, isolado por sentido — proposta
    validada analise_400 PARTES VII–XV). Valor inválido cai em "full".

    Lido por chamada (não cacheado) para permitir toggle em testes/runtime.
    """
    import os
    v = os.environ.get("SDA_BET_PAIR", "full").strip().lower()
    return v if v in ("full", "var_c1c2_c3", "c1c3", "c2c3", "force17") else "full"


def force17_exact_enabled() -> bool:
    """force17: completa a cobertura para EXATAMENTE 17 números. **Default OFF**
    (18/06, tarde — realinhado ao estudo).

    O estudo `analise_400_junho.md` (L940/L985) é explícito: a estratégia vencedora
    aposta a **união real ~15** (sobreposição PERMITIDA e BENÉFICA — reduz N, baixa o
    breakeven de 47,2% p/ 42,8%); **forçar a cobertura a 17 PIORA** (alarga a aposta,
    sobe o breakeven). Por isso o default fiel ao estudo é **OFF (união ~15)**.

    ON (`SDA_FORCE17_EXACT=1`) é **opt-in** p/ consistência visual de "sempre 17
    números": quando o overlap reduz a união abaixo de 17, adiciona os números
    não-cobertos mais próximos até 17 (estende as regiões; não move centros). Custo:
    breakeven +4,4 pontos (42,8%→47,2%). Lido por chamada (toggle runtime).
    """
    import os
    return os.environ.get("SDA_FORCE17_EXACT", "0").strip().lower() in ("1", "true", "on")


def gale_only_after_green() -> bool:
    """Block-gale: só coloca aposta (stake real) após um green. Default OFF.

    Stake-gate (não supressão — INV-3): quando ativo e a última foi red, a
    indicação continua mas o stake vai a 0 (papel). Toggle via GALE_ONLY_AFTER_GREEN.
    """
    import os
    return os.environ.get("GALE_ONLY_AFTER_GREEN", "0").strip().lower() in ("1", "true", "on")


def gale_cap(direction: str = "") -> int:
    """Teto do block-gale (1=flat, 2=G2, 3=G3, 4=G4). Default 1 (flat).

    Global via GALE_CAP; override por sentido via GALE_CAP_CW / GALE_CAP_CCW.
    Subir o teto é opt-in explícito do operador (risco de ruína — ver §9.6).
    """
    import os
    dk = "cw" if direction in ("cw", "horario") else ("ccw" if direction else "")
    raw = None
    if dk == "cw":
        raw = os.environ.get("GALE_CAP_CW")
    elif dk == "ccw":
        raw = os.environ.get("GALE_CAP_CCW")
    if raw is None:
        raw = os.environ.get("GALE_CAP", "1")
    try:
        return min(4, max(1, int(raw)))
    except (TypeError, ValueError):
        return 1


def c_selection_auto_promote_enabled() -> bool:
    """Promoção automática (human-in-the-loop) de regra do CSelectionEngine.

    Default OFF — o motor só sugere; humano aplica. Toggle via
    C_SELECTION_AUTO_PROMOTE. Mesmo padrão de shadow_auto_promote_enabled.
    """
    import os
    return os.environ.get("C_SELECTION_AUTO_PROMOTE", "0").strip().lower() in ("1", "true", "on")


def dealer_fill_forward_enabled() -> bool:
    """Vision (auditoria_pos_foto 21/06) — fill-forward do dealer por sessão.

    Quando o giro chega sem dealer (DOM não casou e a foto ainda não aterrissou),
    propaga o ÚLTIMO dealer real conhecido da MESMA sessão. Corta na troca (um
    dealer real novo substitui o anterior) e na troca de sessão. É METADATA — não
    altera nenhuma decisão de aposta. Default **OFF**; ligar com
    SDA_DEALER_FILL_FORWARD=1. Auditoria: auditoria_pos_foto_21_junho.md §7.2.
    """
    import os
    return os.environ.get("SDA_DEALER_FILL_FORWARD", "0").strip().lower() in ("1", "true", "on")


def dealer_force_profile_enabled() -> bool:
    """Vision (auditoria_pos_foto 21/06) — consumidor dormante de perfil de força
    por dealer×sentido (strategies/dealer_force_profile.py).

    Default **OFF** e ainda NÃO wired no caminho quente (como region_bandit): só
    lê features quando explicitamente chamado. Ligar com
    SDA_DEALER_FORCE_PROFILE=1 só após n≥30 por dealer (ramp-up). Auditoria §7.5.
    """
    import os
    return os.environ.get("SDA_DEALER_FORCE_PROFILE", "0").strip().lower() in ("1", "true", "on")


def vision_attach_max_age_s() -> float:
    """Vision (auditoria_pos_foto 21/06) — janela máxima (s) para a foto/OCR colar
    na decisão mais recente (update_last_vision).

    Hardening da associação racy: se >0, o OCR só sobrescreve a última decisão se
    ela foi criada há menos de N segundos (evita contaminar o giro seguinte quando
    o OCR atrasa). Default **0 = sem limite** (preserva o comportamento atual,
    byte-idêntico). Opt-in via SDA_VISION_ATTACH_MAX_AGE_S. Auditoria §7.4.
    """
    import os
    try:
        return max(0.0, float(os.environ.get("SDA_VISION_ATTACH_MAX_AGE_S", "0")))
    except (TypeError, ValueError):
        return 0.0
