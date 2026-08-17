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
    # MIG-0: compose points this at the persistent data volume. Keep the
    # repository-relative default for local runs outside Docker.
    state_file: Path = Field(
        default=BASE_DIR / "state.json",
        validation_alias="STATE_FILE",
    )
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
    validada analise_400 PARTES VII–XV), "v5_1721" (V5 04/08: 3 regiões
    assinatura-primeiro R1/R2/R3 por sentido + seletor 17↔21 pós-miss —
    estrategia_proposta_03_08.md). Valor inválido cai em "full".

    Lido por chamada (não cacheado) para permitir toggle em testes/runtime.
    """
    import os
    v = os.environ.get("SDA_BET_PAIR", "full").strip().lower()
    return v if v in ("full", "var_c1c2_c3", "c1c3", "c2c3", "force17", "v5_1721") else "full"


def v5_sig4_enabled() -> bool:
    """V5.1 "assinatura-4" (05/08 — spec exata do operador). **Default OFF**.

    Com `SDA_V5_SIG4=1`, o composer v5_1721 muda para a spec revisada:
      R1 = cluster gravidade-7 das últimas **4** forças do sentido-alvo (era 8);
      R2 = **projeção de tendência** — o MESMO centro R1 deslocado por
           clamp(round(slope Theil–Sen janela 4), ±8) casas de força
           (acelerando → adiante; freando → atrás; era "2º cluster do resíduo");
      R3 = região **menos visitada** da divisão FIXA da roda em 6 regiões
           (5×6 + 1×7, ordem física), placar contando TODOS os giros dos DOIS
           sentidos (era zona fria heatmap de 12 do mesmo sentido).
    Geometria/seletor 17↔21 intactos (mesmos centros, C17 ⊂ C21).
    OFF = composer v5_1721 byte-idêntico ao go-live 04/08.
    Rollback: SDA_V5_SIG4=0 no host + redeploy. Lido por chamada (não cacheado).
    """
    import os
    return os.environ.get("SDA_V5_SIG4", "0").strip().lower() in ("1", "true", "on")


def v5_flip_puro_enabled() -> bool:
    """Seletor 17/21 PURO pela última jogada do sentido-alvo. **Default OFF**.

    Regra do dono (05/08, tarde): "o sistema deve analisar a última derrota ou
    vitória do SENTIDO-ALVO para sugerir 17 ou 21 de forma isolada" — a última
    jogada resolvida do sentido da PRÓXIMA jogada decide: vitória → 17,
    derrota → 21. Sem overrides de cobertura.

    Com `SDA_V5_FLIP_PURO=1`:
      - o stop-loss de sessão (B5) deixa de travar o seletor em 17 (LOCK17);
        segue vetando o STAKE (mínimo 1u — INV-3: indicação sempre mantida);
      - o teto de jogadas-21 por sessão×sentido deixa de forçar 17.
    OFF = comportamento do go-live 04/08 (flip + LOCK17 por B5/teto).
    Motivo: em produção o B5 ficou ativo a sessão toda → modo 17 permanente
    mesmo após derrotas (probe 05/08), mascarando a regra do flip.
    Rollback: SDA_V5_FLIP_PURO=0 no host + restart. Lido por chamada.
    """
    import os
    return os.environ.get("SDA_V5_FLIP_PURO", "0").strip().lower() in ("1", "true", "on")


def v5_coverage_lock() -> str:
    """Optional V5 coverage lock: ``17``, ``21`` or empty (current behavior)."""
    import os
    value = os.environ.get("SDA_V5_COVERAGE_LOCK", "").strip()
    return value if value in ("17", "21") else ""


def sugestao_broadcast_enabled() -> bool:
    """Broadcast da mensagem `sugestao` a TODOS os clientes. **Default OFF**.

    Hoje a `sugestao` por-giro vai SÓ ao websocket do MASTER; viewers/Glass Box
    dependem do state_sync (1 s) — a vista EXPANDIDA de um viewer nunca recebe
    a sugestão por-giro (gap de UX percebido como "sugestão sumiu na rodada").
    Com `SDA_SUGESTAO_BROADCAST=1`, o servidor REPLICA a mesma `sugestao` aos
    demais clientes conectados (master continua recebendo a dele primeiro; a
    cópia broadcast o exclui — zero duplicação). Aditivo: clientes ignoram
    mensagens desconhecidas. Rollback: =0 + redeploy. Lido por chamada.
    """
    import os
    return os.environ.get("SDA_SUGESTAO_BROADCAST", "0").strip().lower() in ("1", "true", "on")


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
    """Vision-context fill-forward (resultados_bancos 22/06) — a foto/OCR é a fonte
    AUTORITATIVA de dealer/modelo/provider (o DOM da Evolution não os expõe). Quando
    o giro chega sem esses campos, propaga o ÚLTIMO valor real de cada um da MESMA
    sessão (do último OCR) para TODA jogada, deixando os dados 100% acoplados
    (auditáveis/estratégia). Corta na troca (valor real novo substitui) e na sessão.
    É METADATA — não altera nenhuma decisão de aposta.

    Default do código **OFF** (testes/envs neutros); **produção liga via compose
    (SDA_DEALER_FILL_FORWARD=1)**. Auditoria: resultados_bancos_junho.md §sprint.
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


def error_engine_enabled() -> bool:
    """Error Engine — classifica o PROCESSO do erro por resolução. **Default OFF**
    (ADENDO 05/08 noite-2).

    Com `SDA_ERROR_ENGINE=1`, cada resolução do v5_1721 classifica o resultado
    (strategies/error_engine.py: DATA_SUSPECT > HIT > GEOMETRY_MISS >
    SIGNATURE_SHIFT > FORCE_MISS > VARIANCE) e registra a classe no
    decision_dna (`error_class`) — telemetria pura de "por que erramos".
    NÃO altera aposta/stake/indicação (INV-3 intocado); é o insumo dos
    freezes de aprendizado do R2 dealer-aware (DATA_SUSPECT congela o bandit).
    OFF = resolução byte-idêntica. Rollback: SDA_ERROR_ENGINE=0 + restart.
    Lido por chamada (não cacheado).
    """
    import os
    return os.environ.get("SDA_ERROR_ENGINE", "0").strip().lower() in ("1", "true", "on")


def r2_dealer_shadow_enabled() -> bool:
    """R2 dealer-aware em SHADOW (mede, não aposta). **Default OFF**
    (ADENDO 05/08 noite-2).

    Com `SDA_R2_DEALER_SHADOW=1`, a decisão v5_1721 calcula os candidatos de
    R2 do bandit Thompson por dealer×sentido (strategies/dealer_signature.py:
    braços trend/residual/dealer/correct), escolhe um em paper e congela no
    pending (`r2ds`). A resolução mede o would-be hit do R2 shadow, alimenta
    o bandit/EWMA e registra `r2_source`/`r2_signed_err` no decision_dna.
    A APOSTA REAL NÃO MUDA — cobertura publicada segue o compose de produção.
    Pré-requisito de auditoria antes de ligar SDA_R2_DEALER (live).
    OFF = zero efeito. Rollback: =0 + restart. Lido por chamada.
    """
    import os
    return os.environ.get("SDA_R2_DEALER_SHADOW", "0").strip().lower() in ("1", "true", "on")


def r2_dealer_live_enabled() -> bool:
    """R2 dealer-aware LIVE — o braço vencedor do bandit VIRA o R2 apostado.
    **Default OFF** (ADENDO 05/08 noite-2).

    Com `SDA_R2_DEALER=1` (e fora do warmup), o centro R2 do compose v5_1721 é
    recomposto com a força do braço vencedor (compose_v5(r2_override_force=…)):
    mesmo clamp ±8 de R1, mesma disjunção, R3 recalculado com a ocupação nova —
    C17 ⊂ C21 e INV-3 preservados (indicação/stake intactos; SÓ o centro muda).
    Implica o comportamento de shadow (aprendizado contínuo). Só ligar após
    validar o funil `r2_source` em shadow (hit-rate por braço ≥ baseline).
    OFF = compose de produção byte-idêntico. Rollback: SDA_R2_DEALER=0 +
    restart (estado adaptativo v2.0 é retro-compatível). Lido por chamada.
    """
    import os
    return os.environ.get("SDA_R2_DEALER", "0").strip().lower() in ("1", "true", "on")


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


def dedup_phantom_enabled() -> bool:
    """Phantom dedup (auditoria resultados_bancos 22/06): rejeita re-envios do
    MESMO número+sentido em janela curta (extensão re-detecta o DOM estático e
    reenvia o resultado 1-7s depois; o ciclo real é ~42-48s). Esses giros fantasma
    o engine processaria como reais, corrompendo a cadeia de predição/aposta.

    Default **OFF** (toca o caminho de aposta — ligar só após validar). Ligar com
    SDA_DEDUP_PHANTOM=1. Discriminador = janela de TEMPO (não a força).
    """
    import os
    return os.environ.get("SDA_DEDUP_PHANTOM", "0").strip().lower() in ("1", "true", "on")


def dedup_phantom_window_ms() -> int:
    """Janela (ms) do phantom dedup: re-envio do mesmo número+sentido dentro dela é
    descartado. Default 20000 (20s) — bem abaixo do ciclo real (~42-48s) e bem
    acima dos re-envios observados (1-7s). Ajuste via SDA_DEDUP_PHANTOM_WINDOW_MS."""
    import os
    try:
        return max(0, int(os.environ.get("SDA_DEDUP_PHANTOM_WINDOW_MS", "20000")))
    except (TypeError, ValueError):
        return 20000


def historico_nao_direcional_enabled() -> bool:
    """DIR2 (sentido-fase): trata o histórico inicial/correção como contexto
    NÃO-DIRECIONAL. O histórico do DOM (12 últimos) não carrega o sentido real do
    giro — a extensão o FABRICA por alternância retroativa — e hoje alimenta
    timeline_cw/ccw via process_spin, envenenando o motor SDA17. Com a flag ON, o
    histórico popula só recent_results (zona fria C3), sem direção; a fase real
    entra com os giros ao vivo. Default OFF (byte-idêntico). Ligar com
    SDA_HISTORICO_NAO_DIRECIONAL=1."""
    import os
    return os.environ.get("SDA_HISTORICO_NAO_DIRECIONAL", "0").strip().lower() in ("1", "true", "on")


def sentido_autoritativo_enabled() -> bool:
    """DIR3-5 (sentido-fase): torna o SERVIDOR a autoridade da fase do giro
    (horário↔anti-horário). Com OFF, o servidor obedece o sentido do master e os
    campos de fase (spin_seq/seed/source) são apenas telemetria — a aposta não muda.
    Com ON (SDA_SENTIDO_AUTORITATIVO=1), a fase projetada/reconciliada pelo servidor
    passa a valer e é publicada no state_sync/sugestao. Default OFF (byte-idêntico)."""
    import os
    return os.environ.get("SDA_SENTIDO_AUTORITATIVO", "0").strip().lower() in ("1", "true", "on")


def phase_reconcile_enabled() -> bool:
    """DIR4 (sentido-fase): reconciliação de fase por SHIFT dos últimos resultados.
    O cliente já envia allNumbers (12 últimos) mas o servidor os ignorava. Com ON, o
    servidor compara allNumbers com recent_results para contar quantos giros REAIS
    entraram (k); k>1 = gap (cliente minimizado / 2 giros num tick) → avança a fase
    pelos giros perdidos, corrigindo a paridade. Default OFF (byte-idêntico). Ligar
    com SDA_PHASE_RECONCILE=1."""
    import os
    return os.environ.get("SDA_PHASE_RECONCILE", "0").strip().lower() in ("1", "true", "on")


def dedup_seq_enabled() -> bool:
    """DIR6 (sentido-fase): idempotência por trace_id. Cada giro carrega um trace_id
    único do cliente; reenvios (cliente caiu após enviar, re-render do DOM) chegam com
    o MESMO trace_id. Com ON, o servidor rejeita trace_ids já vistos (janela de 64) —
    mais robusto que o dedup por numero+sentido+ms. Default OFF. Ligar com
    SDA_DEDUP_SEQ=1."""
    import os
    return os.environ.get("SDA_DEDUP_SEQ", "0").strip().lower() in ("1", "true", "on")


def dna_realize_enabled() -> bool:
    """H1 (03/08): fecha o loop do decision_dna — dna_realize_lifts() roda
    automaticamente a cada N resultados (ver dna_realize_every), calculando
    realized_lift_pp POR SENTIDO (cw/ccw; NULL legado = grupo próprio) e
    espelhando cada bucket ao PG via outbox (evento dna_lift_bucket).
    Corrige F1 da auditoria 03/08 (função órfã → coluna 100% NULL).
    Default OFF (byte-idêntico). Ligar com SDA_DNA_REALIZE=1."""
    import os
    return os.environ.get("SDA_DNA_REALIZE", "0").strip().lower() in ("1", "true", "on")


def dna_realize_every() -> int:
    """H1 (03/08): cadência do dna_realize_lifts — roda a cada N resultados
    confirmados (default 20). Leitura por-chamada via SDA_DNA_REALIZE_EVERY."""
    import os
    try:
        return max(1, int(os.environ.get("SDA_DNA_REALIZE_EVERY", "20").strip()))
    except ValueError:
        return 20


def direction_vision_enabled() -> bool:
    """DIR7 (sentido-fase): fusão da fonte de VÍDEO na decisão de fase. Estrutura
    STAND-BY: o futuro serviço de vídeo publica direction_event (ou direction_source=
    'vision' no spin) e, se confiável, confirma/sobrepõe o toggle determinístico
    (prioridade operator>vision>toggle). Default OFF (vídeo inerte). SDA_DIRECTION_VISION=1."""
    import os
    return os.environ.get("SDA_DIRECTION_VISION", "0").strip().lower() in ("1", "true", "on")


def direction_vision_min_conf() -> float:
    """DIR7: confiança mínima (0..1) para um sinal de direção de vídeo ser aceito.
    Abaixo disto o sinal é descartado e o toggle determinístico prevalece. Default 0.7."""
    import os
    try:
        return max(0.0, min(1.0, float(os.environ.get("SDA_DIRECTION_VISION_MIN_CONF", "0.7"))))
    except (TypeError, ValueError):
        return 0.7


def reset_reancora_enabled() -> bool:
    """DIR16 (sentido-fase): fix critico do reset/reancoragem de fase apos troca de
    dealer/mesa. Em OFF (atual), reset_session zera spin_seq/seed_n/direction_source
    mas MANTEM seed_parity da mesa anterior -> o auto-seed da DIR5 nunca dispara e
    project_phase segue usando a paridade antiga. Em ON, reset_session zera tambem
    seed_parity (a menos que direction_locked=True), e handle_history_correction/
    handle_initial_history reanchoram fase ao reprocessar historico. Default OFF
    (byte-identico). SDA_RESET_REANCORA=1."""
    import os
    return os.environ.get("SDA_RESET_REANCORA", "0").strip().lower() in ("1", "true", "on")


def overlay_ultimos_n() -> int:
    """DIR10 (sentido-fase): tamanho do ring buffer overlay (lista 'ultimos[N]' no
    state_sync/sugestao para auditoria offline). 0 = desativa publicacao. Default 12.
    SDA_OVERLAY_ULTIMOS_N=N."""
    import os
    try:
        return max(0, min(64, int(os.environ.get("SDA_OVERLAY_ULTIMOS_N", "12"))))
    except (TypeError, ValueError):
        return 12


def sentido_autoritativo_shadow_enabled() -> bool:
    """DIR18 (sentido-fase): SHADOW MODE da autoridade DIR5. Quando ON com autoritativo
    OFF, roda project_phase + incrementa direction_divergence_total MAS nao substitui
    a direcao do hint do cliente. Permite A/B observavel: comparar 'o que aconteceria'
    sem mudar aposta. Em producao SHADOW=1 sempre (zero risco) — vira fonte de verdade
    para decidir se ligar autoritativo total. Default OFF (byte-identico).
    SDA_SENTIDO_AUTORITATIVO_SHADOW=1."""
    import os
    return os.environ.get("SDA_SENTIDO_AUTORITATIVO_SHADOW", "0").strip().lower() in ("1", "true", "on")


def lock_total_enabled() -> bool:
    """DIR13 (sentido-fase): FIX #Z — lock total da fase (DIR5+DIR17). Hoje
    direction_locked so e checado em message_handler.py:740 (impede fusao de video
    DIR7). NAO impede phase_advance (DIR4) nem auto-seed da DIR5 nem reanchoragem
    DIR17. Nome promete 'trava' mas semantica e 'so nao escuta video'.

    Com flag ON, direction_locked passa a ter semantica completa:
    - DIR5 auto-seed nao dispara (preserva seed_parity escolhido pelo operador)
    - DIR17 nao reanchora em uncertain (lock manda)
    - DIR7 segue sem fusao de video (comportamento atual)

    Default OFF (compatibilidade). SDA_LOCK_TOTAL=1."""
    import os
    return os.environ.get("SDA_LOCK_TOTAL", "0").strip().lower() in ("1", "true", "on")


def uncertain_reancora_enabled() -> bool:
    """DIR17 (sentido-fase): reancora a fase quando phase_advance retorna sem alinhamento
    (matched=False, troca de mesa silenciosa). Em OFF (atual), apenas seta resync_advised
    e segue projetando com seed antigo + spin_seq que ainda incrementa — direcao autoritativa
    errada persiste ate cliente ver resync_advised e mandar set_seed. Em ON, zera seed_parity
    (a menos que direction_locked) e marca seed_n=spin_seq atual — proximo giro alinhado faz
    auto-seed limpo. Default OFF (byte-identico). SDA_UNCERTAIN_REANCORA=1."""
    import os
    return os.environ.get("SDA_UNCERTAIN_REANCORA", "0").strip().lower() in ("1", "true", "on")


# ===================== SPR-V1 (05/08): blindagem da fase =====================
# Todas as flags abaixo nascem DEFAULT OFF (ISO obrig. #4) e sao lidas POR CHAMADA
# (nunca cacheadas em global/atributo) para permitir toggle sem restart em teste.


def phase_buffer_sync_enabled() -> bool:
    """SPR-V1 B1 (furo A): sincroniza o buffer de fase (_phase_results) com os giros
    recuperados no gap do DIR4. Hoje o handler sincroniza apenas recent_results (zona
    fria C3) e o buffer de fase fica PERMANENTEMENTE defasado apos qualquer gap — todo
    giro seguinte devolve phase_uncertain e a fase reancora na direcao do cliente.
    Com ON, o buffer volta a espelhar o allNumbers do cliente e o proximo shift alinha
    em k=1. Tambem passa a limpar _phase_results no correcao_historico (coerencia com
    recent_results, que ja e limpo). Default OFF (byte-identico).
    Ligar: SDA_PHASE_BUFFER_SYNC=1."""
    import os
    return os.environ.get("SDA_PHASE_BUFFER_SYNC", "0").strip().lower() in ("1", "true", "on")


def phase_min_overlap() -> int:
    """SPR-V1 B2: evidencia MINIMA (numeros coincidentes) para aceitar um alinhamento
    de shift. Hoje reconcile_shift aceita o primeiro k que casa, mesmo com overlap m=1
    — 1/37 de chance de coincidencia, o que inventa k giros e corrompe a paridade.
    Com valor > 0, um match com evidencia abaixo do minimo (ou com mais de um k
    plausivel) vira phase_uncertain explicito — o caminho SEGURO. 0 = OFF
    (comportamento atual byte-identico). Producao sugerida: 3 (com allNumbers=12
    recupera ate k=9). Ler via SDA_PHASE_MIN_OVERLAP."""
    import os
    try:
        return max(0, int(os.environ.get("SDA_PHASE_MIN_OVERLAP", "0").strip()))
    except (TypeError, ValueError):
        return 0


def min_spin_interval_ms() -> int:
    """SPR-V1 B3 (furo B / DIR21): intervalo MINIMO (ms) entre dois giros ACEITOS,
    medido no relogio MONOTONICO DO SERVIDOR (imune a NTP e ao relogio do cliente).
    Um giro que chega antes disso e fisicamente impossivel (o ciclo real e ~42-48s) —
    e o vetor do 'giro fantasma' que flipa a fase. 0 = OFF (byte-identico).
    Producao sugerida: 15000. Ler via SDA_MIN_SPIN_INTERVAL_MS."""
    import os
    try:
        return max(0, int(os.environ.get("SDA_MIN_SPIN_INTERVAL_MS", "0").strip()))
    except (TypeError, ValueError):
        return 0


def phase_alt_metric_enabled() -> bool:
    """SPR-V1 B5 (DIR22): telemetria de violacao de alternancia — a mesa alterna um
    sentido por giro, entao dois giros consecutivos com o MESMO sentido final (fora de
    gap recuperado e de reset) sao um sintoma de fase corrompida. So conta metrica +
    warning; NUNCA altera aceitacao do giro nem a aposta. Default OFF.
    Ligar: SDA_PHASE_ALT_METRIC=1."""
    import os
    return os.environ.get("SDA_PHASE_ALT_METRIC", "0").strip().lower() in ("1", "true", "on")


def phase_event_audit_enabled() -> bool:
    """SPR-V4 (Bloco 2): persiste a trilha `phase_events` (SQLite, append-only). Sem
    esta flag NADA e gravado — o contrato do evento continua sendo aplicado em memoria
    (identidade/alvo/TTL/one-shot), mas nao ha prova duravel. E requisito de EVIDENCIA
    do gate T4: counters Prometheus zeram a cada restart do container e logs tem
    retencao limitada. Default OFF. Ligar: SDA_PHASE_EVENT_AUDIT=1."""
    import os
    return os.environ.get("SDA_PHASE_EVENT_AUDIT", "0").strip().lower() in ("1", "true", "on")


def direction_vision_shadow_enabled() -> bool:
    """SPR-V4 (Bloco 3): SHADOW da visao. A cada `novo_resultado`, compara o evento
    fresco e BOUND com a direcao final POS-autoridade e classifica agree/disagree
    (ou stale/unbound/selfcontradict/missing). ZERO efeito em direcao, seed, timeline,
    decisao ou stake — e so leitura + contador + (se SDA_PHASE_EVENT_AUDIT) trilha.
    NAO confundir com SDA_DIRECTION_VISION (congelada em 0 pelo fail-close do SPR-V1:
    visao NAO tem autoridade sobre o giro). Default OFF.
    Ligar: SDA_DIRECTION_VISION_SHADOW=1."""
    import os
    return os.environ.get("SDA_DIRECTION_VISION_SHADOW", "0").strip().lower() in ("1", "true", "on")


def direction_vision_ttl_ms() -> int:
    """SPR-V4 (Bloco 1): prazo de validade (ms) de um `direction_event`, contado do
    RECEBIMENTO no relogio MONOTONICO DO SERVIDOR (`time.monotonic()`), nunca do
    `captured_at_ms` do cliente — senao um cliente com relogio adulterado renova o
    proprio prazo. Default 30000 (menor que o ciclo real de ~44s, entao um evento
    nunca sobrevive ate o giro seguinte). Idade >= TTL ⇒ `stale`.
    Ler via SDA_DIRECTION_VISION_TTL_MS."""
    import os
    try:
        return max(0, int(os.environ.get("SDA_DIRECTION_VISION_TTL_MS", "30000").strip()))
    except (TypeError, ValueError):
        return 30000
