# ADENDO ISO — SPR-AZ1

- **Origem:** SPR-AZ1; PR a registrar no closeout.
- **Mudança:** adicionada sonda HTTPS best-effort do standby Azure ao kickoff e
  criado relatório de freshness com medições externas reais.
- **Decisão:** `/healthz` é o endpoint de saúde; o lag do manifesto permanece
  não mensurável externamente porque o SSH da VM expirou. Não houve acesso ao
  Debian de produção, DNS, dual-write ou dados.
- **Flags/secrets:** nenhuma flag foi criada ou alterada. A coleta encontrou
  `AZURE_PUBLISH_ENABLED=1` e os três nomes de secrets OIDC já configurados;
  nenhum segredo foi lido ou gravado.
- **Rollback:** reverter o PR remove a linha adicional do kickoff e o relatório;
  não há mudança de runtime.
- **ISO 25010/14764:** observabilidade aditiva, disponibilidade preservada e
  evidência de manutenção limitada ao endpoint público.
- **Replay envelope:** modelo gpt-5.6-luna; skills graphify-first e verification;
  MCPs de filesystem/execução; duração aproximada de 45 minutos.
