# 🎲 Roleta Cloud (v3.5)

Este documento serve como **Contexto Único** para Agentes de IA e Desenvolvedores.
Se você é uma IA (ChatGPT, Claude, Gemini), **LEIA ISTO PRIMEIRO**.

---

## 🏗️ Arquitetura

O sistema é composto por 3 partes interconectadas:

1.  **Engine (Python/WebSocket)**:
    *   **Porta**: `8765` (WSS)
    *   **Local**: `main.py` (Entry point)
    *   **Função**: Recebe dados da roleta, processa estratégias (`strategies/sda17.py`) e envia previsões.
2.  **Dashboard (Web)**:
    *   **Porta**: `80/443` (HTTPS)
    *   **Local**: `dashboard/` (HTML/JS estático servido pelo Nginx).
    *   **Função**: Interface visual "Glass Box" para o usuário ver o estado do jogo.
3.  **Extensão Chrome ("Escuta Beat")**:
    *   **Local**: `extension/`
    *   **Função**: Injeta script na casa de apostas, lê números e envia via WebSocket para a Engine.

---

## 🛠️ Workflow de Desenvolvimento (CI/CD)

**NUNCA** edite arquivos diretamente no servidor de produção.

### 1. Como Desenvolver
1.  Edite os arquivos localmente.
2.  Teste rodando `python main.py`.
3.  Faça commit e push para a branch `main`.
    ```bash
    git push origin main
    ```
    *O GitHub Actions (`.github/workflows/ci.yml`) rodará testes automaticamente.*

### 2. Como Fazer Deploy (Produção)
Para atualizar o servidor (`roleta.xma-ia.com`), crie uma **Tag de Release** no GitHub.

1.  GitHub > Releases > Draft new release.
2.  Tag ex: `v3.5.1`.
3.  **Deploy Automático**: O workflow `deploy.yml` conecta no servidor via SSH, baixa o código e reinicia o serviço.

---

## 🔒 Segurança e Infraestrutura

*   **Servidor**: Debian (`187.45.181.75`).
*   **Domínios**:
    *   `https://roleta.xma-ia.com` (Principal)
    *   `https://www.roleta.xma-ia.com` (Alias)
*   **Segredos**:
    *   `firebase-credentials.json`: **NÃO TENTE CRIAR**. Ele existe apenas no servidor e na máquina local do usuário. É ignorado pelo git.
    *   `config.py`: Existe apenas no servidor.

---

## 📂 Mapa de Pastas

*   `/` (Raiz): Código Python da Engine (Docker-ready).
*   `extension/`: Código fonte da extensão do Chrome.
*   `dashboard/`: Código do site web.
*   `tests/`: Testes unitários (`pytest`).
*   `scripts/`: Scripts DevOps (`setup`, manutenção).
*   `archive/`: Código legado (`RoletaV11`, backups). **Não use como referência de código ativo.**

---

## 🤖 Comandos para Agentes

Se precisar verificar o estado do servidor:

```bash
# Ver se o serviço está rodando
ssh root@187.45.181.75 "systemctl status roleta-cloud"

# Ver logs em tempo real
ssh root@187.45.181.75 "tail -n 20 /root/roleta-cloud/server.log"

# Ver servidor web
ssh root@187.45.181.75 "systemctl status nginx"
```
