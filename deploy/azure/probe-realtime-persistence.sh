#!/usr/bin/env bash
# Prova WS -> decisão SQLite -> state.json -> restart sem tocar /opt/roleta/data.
set -euo pipefail
umask 077

APP_DIR="${APP_DIR:-/opt/roleta}"
ACTIVE_CONTAINER="${ACTIVE_CONTAINER:-roleta-cloud}"
ACTIVE_DATA_DIR="${ACTIVE_DATA_DIR:-/opt/roleta/data}"
PROBE_CONTAINER="${PROBE_CONTAINER:-roleta-probe}"
PROBE_DATA_DIR="${PROBE_DATA_DIR:-/opt/roleta/probe-data}"
RESULTS_DIR="${RESULTS_DIR:-/opt/roleta/probe-results}"
SPIN_COUNT="${SPIN_COUNT:-100}"
CLIENT_SCRIPT="${CLIENT_SCRIPT:-$APP_DIR/ws-persistence-probe.py}"

for cmd in docker findmnt python3 realpath sha256sum sqlite3; do
  command -v "$cmd" >/dev/null || { echo "ERRO: comando ausente: $cmd" >&2; exit 1; }
done
[[ "$SPIN_COUNT" =~ ^[1-9][0-9]*$ ]] && [ "$SPIN_COUNT" -le 1000 ] || {
  echo "ERRO: SPIN_COUNT deve estar entre 1 e 1000" >&2
  exit 2
}
[ -f "$CLIENT_SCRIPT" ] || { echo "ERRO: cliente ausente: $CLIENT_SCRIPT" >&2; exit 1; }

ACTIVE_RESOLVED="$(realpath -m -- "$ACTIVE_DATA_DIR")"
PROBE_RESOLVED="$(realpath -m -- "$PROBE_DATA_DIR")"
case "$PROBE_RESOLVED" in
  /opt/roleta/probe-data|/opt/roleta/probe-data-*) ;;
  *) echo "ERRO: PROBE_DATA_DIR fora do namespace seguro /opt/roleta/probe-data*" >&2; exit 2 ;;
esac
[ "$PROBE_RESOLVED" != "$ACTIVE_RESOLVED" ] || {
  echo "ERRO: probe e dados ativos apontam para o mesmo diretório" >&2
  exit 2
}
[ -f "$ACTIVE_RESOLVED/decisions.db" ] && [ -f "$ACTIVE_RESOLVED/state.json" ] || {
  echo "ERRO: par ativo decisions.db/state.json ausente" >&2
  exit 1
}
[ "$(docker inspect -f '{{.State.Running}}' "$ACTIVE_CONTAINER")" = "true" ] || {
  echo "ERRO: container ativo não está rodando" >&2
  exit 1
}

resolve_data_device() {
  local container="$1"
  local mount_type mount_name mount_source device
  mount_type="$(docker inspect "$container" --format \
    '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Type}}{{end}}{{end}}')"
  mount_name="$(docker inspect "$container" --format \
    '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Name}}{{end}}{{end}}')"
  mount_source="$(docker inspect "$container" --format \
    '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}')"
  if [ "$mount_type" = "volume" ] && [ -n "$mount_name" ]; then
    device="$(docker volume inspect "$mount_name" --format '{{index .Options "device"}}' 2>/dev/null || true)"
    if [ -n "$device" ] && [ "$device" != "<no value>" ]; then
      realpath -m -- "$device"
      return
    fi
  fi
  realpath -m -- "$mount_source"
}

ACTIVE_MOUNT="$(resolve_data_device "$ACTIVE_CONTAINER")"
[ "$ACTIVE_MOUNT" = "$ACTIVE_RESOLVED" ] || {
  echo "ERRO: mount ativo inesperado: $ACTIVE_MOUNT (esperado $ACTIVE_RESOLVED)" >&2
  exit 1
}
if docker inspect "$PROBE_CONTAINER" >/dev/null 2>&1; then
  echo "ERRO: container $PROBE_CONTAINER já existe" >&2
  exit 1
fi

TMP="$(mktemp -d /run/roleta-probe.XXXXXX)"
cleanup() {
  docker rm -f "$PROBE_CONTAINER" >/dev/null 2>&1 || :
  rm -rf -- "$PROBE_RESOLVED"
  rm -rf -- "$TMP"
}
trap cleanup EXIT

rm -rf -- "$PROBE_RESOLVED"
install -d -m 0700 "$PROBE_RESOLVED" "$RESULTS_DIR"
sqlite3 "$ACTIVE_RESOLVED/decisions.db" ".backup '$PROBE_RESOLVED/decisions.db'"
install -m 0600 "$ACTIVE_RESOLVED/state.json" "$PROBE_RESOLVED/state.json"
ACTIVE_HASH_BEFORE="$(sha256sum "$ACTIVE_RESOLVED/decisions.db" "$ACTIVE_RESOLVED/state.json")"
INITIAL_COUNT="$(sqlite3 "$PROBE_RESOLVED/decisions.db" 'SELECT COUNT(*) FROM decisions;')"
INITIAL_SEQ="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1], encoding="utf-8")).get("spin_seq",0)))' "$PROBE_RESOLVED/state.json")"
IMAGE_REF="$(docker inspect "$ACTIVE_CONTAINER" --format '{{.Config.Image}}')"

docker inspect "$ACTIVE_CONTAINER" > "$TMP/inspect.json"
python3 - "$TMP/inspect.json" "$TMP/probe.env" <<'PY'
import json
import sys

source, output = sys.argv[1:]
with open(source, encoding="utf-8") as handle:
    env = json.load(handle)[0]["Config"]["Env"]
allowed_prefixes = ("SDA_", "GALE_", "C_")
blocked = {
    "AUTH_ENABLED",
    "ROLETA_API_KEY",
    "ROLETA_PG_DSN",
    "STATE_FILE",
    "WS_HOST",
    "WS_PORT",
}
with open(output, "w", encoding="utf-8") as handle:
    for item in env:
        key = item.split("=", 1)[0]
        if key not in blocked and key.startswith(allowed_prefixes):
            if "\n" in item or "\r" in item:
                raise SystemExit(f"env inválido: {key}")
            handle.write(item + "\n")
PY

docker run -d \
  --name "$PROBE_CONTAINER" \
  --restart=no \
  --env-file "$TMP/probe.env" \
  -e AUTH_ENABLED=false \
  -e ROLETA_PG_DSN= \
  -e STATE_FILE=/app/data/state.json \
  -e WS_HOST=0.0.0.0 \
  -e WS_PORT=8765 \
  -p 127.0.0.1:18765:8765 \
  -p 127.0.0.1:18766:8766 \
  -v "$PROBE_RESOLVED:/app/data" \
  -v "$APP_DIR/server/configs:/app/server/configs:ro" \
  "$IMAGE_REF" >/dev/null

PROBE_MOUNT="$(resolve_data_device "$PROBE_CONTAINER")"
[ "$PROBE_MOUNT" = "$PROBE_RESOLVED" ] || {
  echo "ERRO: probe montou diretório inesperado: $PROBE_MOUNT" >&2
  exit 1
}

wait_healthy() {
  local status="starting"
  for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$PROBE_CONTAINER" 2>/dev/null || echo starting)"
    [ "$status" = "healthy" ] && return 0
    sleep 2
  done
  echo "ERRO: probe não ficou healthy (status=$status)" >&2
  return 1
}

run_client() {
  local count="$1"
  docker run --rm \
    --network "container:$PROBE_CONTAINER" \
    --entrypoint python \
    -v "$CLIENT_SCRIPT:/probe-client.py:ro" \
    "$IMAGE_REF" /probe-client.py --url ws://127.0.0.1:8765 --count "$count"
}

wait_healthy
run_client "$SPIN_COUNT" > "$TMP/client-first.json"
AFTER_FIRST_COUNT="$(sqlite3 "$PROBE_RESOLVED/decisions.db" 'SELECT COUNT(*) FROM decisions;')"
[ "$AFTER_FIRST_COUNT" -eq $((INITIAL_COUNT + SPIN_COUNT)) ] || {
  echo "ERRO: delta de decisões inesperado: $INITIAL_COUNT -> $AFTER_FIRST_COUNT" >&2
  exit 1
}

docker stop --time 60 "$PROBE_CONTAINER" >/dev/null
SEQ_BEFORE_RESTART="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1])).get("spin_seq",0)))' "$PROBE_RESOLVED/state.json")"
python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$PROBE_RESOLVED/state.json"
docker start "$PROBE_CONTAINER" >/dev/null
wait_healthy
SEQ_AFTER_RESTART="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1])).get("spin_seq",0)))' "$PROBE_RESOLVED/state.json")"
[ "$SEQ_AFTER_RESTART" -eq "$SEQ_BEFORE_RESTART" ] || {
  echo "ERRO: spin_seq mudou no restart: $SEQ_BEFORE_RESTART -> $SEQ_AFTER_RESTART" >&2
  exit 1
}
run_client 1 > "$TMP/client-restart.json"
FINAL_COUNT="$(sqlite3 "$PROBE_RESOLVED/decisions.db" 'SELECT COUNT(*) FROM decisions;')"
[ "$FINAL_COUNT" -eq $((AFTER_FIRST_COUNT + 1)) ] || {
  echo "ERRO: escrita pós-restart não persistiu" >&2
  exit 1
}
docker stop --time 60 "$PROBE_CONTAINER" >/dev/null
FINAL_SEQ="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1])).get("spin_seq",0)))' "$PROBE_RESOLVED/state.json")"
FINAL_INTEGRITY="$(sqlite3 "$PROBE_RESOLVED/decisions.db" 'PRAGMA integrity_check;')"
[ "$FINAL_INTEGRITY" = "ok" ] || { echo "ERRO: integrity_check=$FINAL_INTEGRITY" >&2; exit 1; }
[ "$FINAL_SEQ" -eq $((INITIAL_SEQ + SPIN_COUNT + 1)) ] || {
  echo "ERRO: spin_seq não avançou sem gaps: $INITIAL_SEQ -> $FINAL_SEQ" >&2
  exit 1
}

ACTIVE_HASH_AFTER="$(sha256sum "$ACTIVE_RESOLVED/decisions.db" "$ACTIVE_RESOLVED/state.json")"
[ "$ACTIVE_HASH_AFTER" = "$ACTIVE_HASH_BEFORE" ] || {
  echo "ERRO: volume ativo mudou durante o probe" >&2
  exit 1
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
python3 - "$RESULTS_DIR/probe-$STAMP.json" "$IMAGE_REF" "$INITIAL_COUNT" \
  "$FINAL_COUNT" "$INITIAL_SEQ" "$FINAL_SEQ" "$SPIN_COUNT" <<'PY'
import datetime as dt
import json
import sys

path, image, initial_count, final_count, initial_seq, final_seq, count = sys.argv[1:]
payload = {
    "status": "PASS",
    "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "image": image,
    "requested_spins": int(count),
    "verified_spins": int(count) + 1,
    "decisions_before": int(initial_count),
    "decisions_after": int(final_count),
    "spin_seq_before": int(initial_seq),
    "spin_seq_after": int(final_seq),
    "integrity_check": "ok",
    "active_volume_unchanged": True,
    "inv3": "APOSTAR",
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
print(json.dumps(payload, sort_keys=True))
PY
