# Azure standby freshness — 2026-08-16

## Medições

Probe externo executado em 2026-08-16 (horário local do sprint):

| Endpoint | Resultado |
|---|---|
| `https://20-226-77-194.sslip.io/healthz` | HTTP 200; `status=ok`, `version=4.4.1`, `uptime_sec=969138` |
| `https://20-226-77-194.sslip.io/health` | HTTP 404 (endpoint incorreto) |
| `https://20-226-77-194.sslip.io/` | HTTP 200 |
| `http://20-226-77-194.sslip.io/healthz` | HTTP 200 |
| SSH `azureuser@20.226.77.194` | timeout na porta 22; inspeção local não foi possível |

O timestamp retornado pelo health check (`ts=1786928502`, com incremento de um
segundo entre as duas sondas) comprova que a VM responde, mas não mede o
manifesto de restore. Portanto, o lag snapshot→restore medido é **indisponível
externamente**, e não deve ser inferido a partir do uptime ou do health.

## Desenho atual e gap

O HostDime produz um snapshot autoritativo a cada 10 minutos. A VM Azure
consulta manifests a cada 2 minutos e recusa snapshots com mais de 900 segundos;
o manifesto é publicado por último, depois da validação de integridade e
SHA-256. O endpoint `/healthz` confirma apenas a disponibilidade da réplica.

Ainda falta uma medição autenticada do manifesto mais recente em
`/opt/roleta/standby` (ou `standby-status.json`) para afirmar freshness real.
O povoamento em tempo real continua bloqueado até o cutover: depois do freeze e
da promoção do último snapshot, dual-write/CDC poderá ser avaliado em janela
própria, com gate e soak observados. Este sprint não liga dual-write, não toca
DNS e não altera o escritor HostDime.

## Publicação de imagens

Durante a coleta, `AZURE_PUBLISH_ENABLED=1` e os três nomes de secrets OIDC
(`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`) já estavam
presentes. O workflow `Publish Azure images` teve runs anteriores `skipped` e
um run posterior concluído com sucesso; a issue do sprint registra a
verificação e a necessidade de manter esse gate sem afetar a produção
HostDime.
