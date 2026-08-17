# ADENDO 16/08/2026 — Ativação total da camada de dados + paridade rumo ao cutover Azure

**Origem:** diretriz do dono 16/08 21:47 ("estrutura funcionando e depois migrar 100% pra
Azure; nada de shadow — a cópia da HostDime já valida a estrutura") + auditoria
`estrutura_dados_16_08.md` (PR #88). **Documento-mãe** `Manutenabilidade_iso.md` congelado —
este adendo É o registro ISO da mudança (convenção 06/08).

## 1. O que este PR liga (E1 + E5 da auditoria)

| Flag | Antes | Agora | Classe | Efeito |
|---|---|---|---|---|
| `SDA_PG_FEATURE_CONTEXT` | 0 (hd/az/pg-compose) | **1 nos três** | dado (sem efeito em aposta) | produtor projeta dealer/mesa/visão/fase/centro/gale no payload; CDC grava em `spin_features` |
| `SDA_DNA_REALIZE` | 0 hd / 1 az (exceção pré-cutover) | **1 nos dois** | audit | buckets de lift realizados voltam a popular o PG |

Contrato `tests/test_azure_pre_cutover.py::test_azure_strategy_flags_match_live_production_contract`
atualizado no MESMO PR: a exceção `hd=0/az=1` do DNA_REALIZE **deixa de existir** —
paridade PLENA de flags entre HostDime e Azure é pré-condição do cutover 100%.

**Fora deste PR (comportamento de aposta, decisão separada):** `SDA_R2_DEALER*`,
`SDA_ERROR_ENGINE` — mudam stake/assinatura; não são necessárias para "estrutura 100%".

## 2. Credenciais/ativações executadas FORA do repo (mesma janela, pelo dono via az/gh)

1. **Pipeline de imagem ACR (E2):** app registration `gh-roleta-acr-publish`
   (appId `8638a696-…`), federated credential OIDC `repo:ivandirfilho/roleta-cloud:ref:refs/heads/main`,
   role `AcrPush` no `acrroletaprod`; secrets `AZURE_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID`
   no repo; repo variable `AZURE_PUBLISH_ENABLED=1`. **O push deste merge na main é o
   primeiro publish real** (`azure-<sha>` + `azure-latest`).
2. **Data-lab (E4):** role `Storage Blob Data Reader` para o dono no `stroletaprod` —
   leitura de snapshots sem account key.

## 3. Sequência de efeito (zero-humano)

merge → deploy HostDime ~2min (containers recriados com flags=1) → produtor emite
contexto → CDC preenche `spin_features.*` novos → **backfill histórico**
`tools/backfill_pg_feature_context.py --apply` (4 travas, idempotente; executado via
acesso autorizado do dono; evidência abaixo) → ACR recebe imagem → `deploy-azure.sh`
na VM standby puxa digest novo (fecha o drift de 11 dias, E3).

## 4. Como reverter

- Flags: `SDA_PG_FEATURE_CONTEXT=0` / `SDA_DNA_REALIZE=0` na compose + redeploy (ou
  `git revert` deste PR). Dados gravados são verdadeiros — nada a limpar.
- Pipeline de imagem: `gh variable set AZURE_PUBLISH_ENABLED --body 0` (gate volta a skip).
- Backfill: não requer reversão (não sobrescreve, não inventa — só preenche NULL/unknown).

## 5. Evidência pós-ativação (preenchida na execução)

- [ ] Flags vivas nos containers (env de `roleta-cloud` e `cdc-worker`)
- [ ] `spin_features` novos com contexto (fill > 0 em vision/dealer nas linhas pós-deploy)
- [ ] Backfill `--apply`: relatório (filled/target_absent/already_filled)
- [ ] Run "Publish Azure images" = success + digest no ACR
- [ ] VM standby rodando digest do ACR (fim do drift)

## 6. Checklist do cutover 100% Azure (próxima etapa, PR próprio)

1. Congelar escritor HostDime → 2. último snapshot → 3. restore no standby →
4. `cutover-caddy.sh` (DNS/writer allowlist) → 5. observação → 6. desligar HostDime.
Pré-condições JÁ satisfeitas por esta onda: paridade de flags, imagem por digest,
dados replicando, backup Azure-local ativo. Pendências: SPR-D3/D4 (vhost/deploy),
janela de validação do contexto, decisão de data.

## 7. Lição ISO (25010 — Adequação funcional / 14764)

Réplica de DADOS sem réplica de CÓDIGO é meio-standby: o Blob estava fresco (10min)
enquanto a VM rodava imagem de 11 dias porque o gate de publicação nunca foi ativado.
Regra nova: **checklist de cutover exige provar as DUAS réplicas** (dado E código por
digest) — uma sonda de cada, na mesma janela.
