#!/bin/bash
# Instalador/atualizador do entrypoint de deploy — idempotente e reversível.
#
# POR QUE ESTE SCRIPT EXISTE
#   O systemd executa /usr/local/bin/roleta-deploy-pull.sh, que fica FORA do repo.
#   Historicamente esse arquivo era uma COPIA congelada do script de deploy: melhorias
#   versionadas (por exemplo o passo de observabilidade do OBS-INODE) so chegavam em
#   producao se alguem lembrasse de reinstalar a copia — e ninguem lembrava, porque
#   nada tornava o congelamento visivel. `scripts/roleta-deploy-launcher.sh` resolve o
#   futuro (o entrypoint vira um ponteiro para o script versionado), mas alguem precisa
#   INSTALAR o launcher uma vez, com segurança e de forma auditavel. E este script.
#
# USO
#   roleta-deploy-install.sh            instala/atualiza o launcher (idempotente)
#   roleta-deploy-install.sh --check    diagnostica:
#                                         0 = em dia (ou launcher de outra versao:
#                                             as mudancas versionadas CHEGAM)
#                                         1 = copia congelada (o deploy versionado
#                                             NAO esta rodando)
#                                         2 = erro
#   roleta-deploy-install.sh --rollback restaura o entrypoint anterior do backup
#
# LIMITE CONHECIDO DA SONDA
#   Quem chama `--check` no fim do deploy e o script VERSIONADO. Enquanto o
#   entrypoint for a copia congelada de antes deste PR, essa copia nunca executa a
#   sonda — ou seja, a sonda NAO detecta o congelamento ATUAL, so protege contra um
#   re-congelamento FUTURO. Por isso o bootstrap manual e obrigatorio, e a unit
#   systemd tambem chama a sonda em ExecStartPre (nao-fatal), o que a torna
#   independente de qual script esta instalado.
#
# GARANTIAS
#   - idempotente: se o entrypoint ja for o launcher, nao escreve nada;
#   - reversivel: o entrypoint anterior e copiado para $BACKUP_DIR antes de qualquer
#     substituicao, e --rollback o traz de volta;
#   - nao mexe na unit systemd: o caminho e o nome do arquivo instalado nao mudam;
#   - --check e read-only e serve de sonda (o deploy o chama para logar o drift).
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/roleta-cloud}"
LAUNCHER_SRC="${LAUNCHER_SRC:-$REPO_DIR/scripts/roleta-deploy-launcher.sh}"
ENTRYPOINT="${ENTRYPOINT:-/usr/local/bin/roleta-deploy-pull.sh}"
BACKUP_DIR="${BACKUP_DIR:-/usr/local/lib/roleta-deploy}"

log() { echo "[$(date -u +%FT%TZ)] INSTALL $*"; }

# `--check` roda a cada tick (ExecStartPre + fim do deploy): silencioso quando esta
# tudo certo, para nao encher o journal. OBS_VERBOSE=1 forca o log.
log_ok() { if [ "${OBS_VERBOSE:-0}" = "1" ]; then log "$@"; fi; }

# Marcador do launcher: distingue "e um launcher (talvez de outra versao)" de
# "e uma copia congelada do deploy".
LAUNCHER_MARK="ROLETA-DEPLOY-LAUNCHER"

is_launcher() {
    [ -f "$1" ] && grep -q "$LAUNCHER_MARK" "$1" 2>/dev/null
}

sha() {
    if [ ! -f "$1" ]; then
        printf ''
        return 0
    fi
    sha256sum < "$1" | awk '{print $1}'
}

mode="${1:-install}"

if [ ! -f "$LAUNCHER_SRC" ]; then
    log "FAIL launcher ausente no repo: $LAUNCHER_SRC"
    exit 2
fi

src_sha="$(sha "$LAUNCHER_SRC")"
cur_sha="$(sha "$ENTRYPOINT")"

case "$mode" in
    --check)
        if [ -z "$cur_sha" ]; then
            log "DRIFT entrypoint ausente: $ENTRYPOINT"
            exit 1
        fi
        if [ "$cur_sha" = "$src_sha" ]; then
            log_ok "ok — $ENTRYPOINT e o launcher versionado (${src_sha:0:12})"
            exit 0
        fi
        # Hash diferente NAO significa, sozinho, que o deploy versionado parou de
        # chegar: um launcher de outra versao continua fazendo `exec` do script do
        # repo. So a AUSENCIA do marcador prova que voltou a ser uma copia.
        if is_launcher "$ENTRYPOINT"; then
            log "DESATUALIZADO $ENTRYPOINT e um launcher de outra versao (instalado=${cur_sha:0:12} repo=${src_sha:0:12})"
            log "DESATUALIZADO as mudancas versionadas CONTINUAM chegando; atualize quando puder: bash $REPO_DIR/scripts/roleta-deploy-install.sh"
            exit 0
        fi
        log "DRIFT $ENTRYPOINT NAO e um launcher: instalado=${cur_sha:0:12} repo=${src_sha:0:12}"
        log "DRIFT o deploy em uso e uma copia congelada — mudancas versionadas do deploy NAO estao chegando"
        log "DRIFT corrija com: bash $REPO_DIR/scripts/roleta-deploy-install.sh"
        exit 1
        ;;

    --rollback)
        backup="$BACKUP_DIR/$(basename "$ENTRYPOINT").bak"
        if [ ! -f "$backup" ]; then
            log "FAIL sem backup em $backup"
            exit 2
        fi
        install -m755 "$backup" "$ENTRYPOINT"
        log "rollback ok — $ENTRYPOINT restaurado de $backup"
        exit 0
        ;;

    install)
        if [ "$cur_sha" = "$src_sha" ]; then
            log "ok — nada a fazer, $ENTRYPOINT ja e o launcher (${src_sha:0:12})"
            exit 0
        fi
        mkdir -p "$BACKUP_DIR"
        if [ -n "$cur_sha" ]; then
            install -m755 "$ENTRYPOINT" "$BACKUP_DIR/$(basename "$ENTRYPOINT").bak"
            log "backup do entrypoint anterior (${cur_sha:0:12}) em $BACKUP_DIR"
        else
            log "entrypoint inexistente — instalando pela primeira vez"
        fi
        install -m755 "$LAUNCHER_SRC" "$ENTRYPOINT"
        log "launcher instalado em $ENTRYPOINT (${src_sha:0:12})"
        log "a partir daqui o deploy roda sempre $REPO_DIR/scripts/roleta-deploy-pull.sh (via git)"
        log "rollback: bash $REPO_DIR/scripts/roleta-deploy-install.sh --rollback"
        exit 0
        ;;

    *)
        log "FAIL modo desconhecido: $mode (use: install | --check | --rollback)"
        exit 2
        ;;
esac
