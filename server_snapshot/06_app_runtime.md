# Aplicação Roleta Cloud — Runtime

## Git no servidor
```
e7461a7 Merge pull request #6 from ivandirfilho/copilot/fix-dealer-capture-issue
2235a7d fix: hydrate listener metadata from extractor frames
313fe2b Initial plan
--- status ---
?? models/spin_autoencoder.joblib
```

## Arquivos não versionados relevantes
```
?? models/spin_autoencoder.joblib
```

## .env — somente NOMES de variáveis (valores omitidos)
```
ROLETA_PG_DSN
```

## Estrutura /root/roleta-cloud (nivel 2)
```
.
./app_config
./archive
./archive/backup_antes_sync
./archive/contexto_sessoes
./archive/dashboard
./archive/extensao_legacy
./archive/historico_dev
./archive/RoletaV11
./archive/sessoes
./archive/tests
./archive/tools
./auth
./backups
./backups/pg
./config
./config/grafana-agent
./core
./data
./database
./database/age
./docker
./docker/cdc-worker
./docker/postgres
./docs
./docs/compliance
./docs/grafana
./docs/runbooks
./extension
./extension/icons
./frontend
./graphify-out
./graphify-out/cache
./migrations
./migrations/versions
./models
./obs
./obs/grafana
./.pytest_cache
./.pytest_cache/v
./scripts
./scripts/sim_temp
./server
./server/configs
./state
./strategies
./tests
./tools
./tools/systemd
./wal-g
```

## Health endpoint
```
{"status": "ok", "uptime_sec": 619, "version": "4.4.0", "ts": 1781117482}
```

## state.json / configs runtime
```
total 8
drwxr-xr-x 2 root root 4096 May 24 21:29 .
drwxr-xr-x 4 root root 4096 May 24 21:15 ..
-rw-r--r-- 1 root root    0 May 24 21:29 .gitkeep
-rw-r--r-- 1 root root 14714 Jun 10 18:51 /root/roleta-cloud/state.json
-rw-r--r-- 1 root root 14714 Jun 10 18:51 /root/roleta-cloud/state.json
```
