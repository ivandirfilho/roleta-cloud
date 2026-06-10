# Docker — Containers e Infraestrutura

## Containers
```
NAMES                 IMAGE                                                   STATUS                    PORTS
roleta-cloud          roleta-cloud-roleta-cloud                               Up 10 minutes (healthy)   127.0.0.1:8765-8766->8765-8766/tcp
roleta-cdc-worker     roleta/cdc-worker:latest                                Up 10 minutes (healthy)   
roleta-alertmanager   prom/alertmanager:v0.27.0                               Up 10 minutes (healthy)   127.0.0.1:9093->9093/tcp
roleta-grafana        grafana/grafana:10.4.2                                  Up 10 minutes (healthy)   127.0.0.1:3000->3000/tcp
roleta-prometheus     prom/prometheus:v2.51.2                                 Up 10 minutes (healthy)   127.0.0.1:9090->9090/tcp
roleta-pg             roleta/postgres-stack:pg15-age15                        Up 10 minutes (healthy)   127.0.0.1:5432->5432/tcp
node-exporter         quay.io/prometheus/node-exporter:v1.8.2                 Up 10 minutes             
pg-exporter           quay.io/prometheuscommunity/postgres-exporter:v0.15.0   Up 10 minutes             127.0.0.1:9187->9187/tcp
```

## Imagens
```
REPOSITORY                                      TAG          SIZE      CREATED
roleta-cloud-roleta-cloud                       latest       302MB     2 weeks ago
roleta/cdc-worker                               latest       194MB     2 weeks ago
roleta/postgres-stack                           pg15-age15   1.01GB    2 weeks ago
python                                          3.11-slim    188MB     3 weeks ago
python                                          3.12-slim    179MB     3 weeks ago
postgres                                        16           642MB     3 weeks ago
quay.io/prometheus/node-exporter                v1.8.2       38.2MB    23 months ago
grafana/grafana                                 10.4.2       577MB     2 years ago
prom/prometheus                                 v2.51.2      369MB     2 years ago
prom/alertmanager                               v0.27.0      106MB     2 years ago
quay.io/prometheuscommunity/postgres-exporter   v0.15.0      32.4MB    2 years ago
```

## Volumes
```
VOLUME NAME                      DRIVER
roleta-cloud_alertmanager-data   local
roleta-cloud_grafana-data        local
roleta-cloud_prometheus-data     local
roleta-cloud_roleta-data         local
roleta_pgdata_prod               local
```

## Redes
```
NAME                   DRIVER
bridge                 bridge
host                   host
none                   null
roleta-cloud_default   bridge
```

## Restart policies + healthchecks
```
roleta-cloud              restart=unless-stopped  health=healthy
roleta-cdc-worker         restart=unless-stopped  health=healthy
roleta-alertmanager       restart=unless-stopped  health=healthy
roleta-grafana            restart=unless-stopped  health=healthy
roleta-prometheus         restart=unless-stopped  health=healthy
roleta-pg                 restart=unless-stopped  health=healthy
node-exporter             restart=unless-stopped  health=none
pg-exporter               restart=unless-stopped  health=none
```

## Uso de recursos (snapshot)
```
NAME                  CPU %     MEM USAGE / LIMIT
roleta-cloud          2.06%     59.89MiB / 512MiB
roleta-cdc-worker     0.02%     22.63MiB / 57.64GiB
roleta-alertmanager   0.26%     18.16MiB / 128MiB
roleta-grafana        0.08%     67.27MiB / 384MiB
roleta-prometheus     1.72%     41.03MiB / 512MiB
roleta-pg             0.08%     152.5MiB / 57.64GiB
node-exporter         0.00%     11.13MiB / 57.64GiB
pg-exporter           0.00%     11.39MiB / 57.64GiB
```
