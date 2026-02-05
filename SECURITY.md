# Política de Segurança

## Reporte de Vulnerabilidades

A segurança deste projeto é levada a sério. Se você descobrir uma vulnerabilidade de segurança, por favor:

1.  **NÃO** abra uma Issue pública.
2.  Envie um relato detalhado para o proprietário do repositório (Ivan).

## Regras de Credenciais

*   **NUNCA** commite arquivos `*.json` que contenham chaves privadas (ex: Firebase credentials).
*   **NUNCA** hardcode chaves de API (`sk-...`) no código fonte. Use variáveis de ambiente.
*   O arquivo `config.py` não deve ser versionado se contiver senhas reais de produção. Use `config.template.py` como exemplo.

## Arquivos Protegidos

Os seguintes arquivos são considerados sensíveis e devem ser ignorados pelo Git:
*   `firebase-credentials.json`
*   `*.db` (Bancos de dados de produção)
*   `.env`
