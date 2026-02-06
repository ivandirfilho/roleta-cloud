# 📱 Escuta Beat v3.0 - Android Overlay

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              FLUXO v3.0                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  KIWI BROWSER (Android)                   SERVIDOR (Local/Cloud)                │
│  ┌─────────────────────────────┐         ┌────────────────────────────────┐    │
│  │ Escuta Beat Extension       │         │ Python                         │    │
│  │                             │         │                                │    │
│  │ background.js               │  WS     │ websocket_server.py            │    │
│  │ ├─ Captura números ─────────┼────────►│ ├─ Recebe dados                │    │
│  │ │                           │         │ ├─ Chama bridge.py             │    │
│  │ │                           │         │ │   └─ Gera sugestão           │    │
│  │ │                           │◄────────┼─┴─ Envia sugestão              │    │
│  │ └─ Envia para content.js    │         │                                │    │
│  │                             │         └────────────────────────────────┘    │
│  │ content.js                  │                                               │
│  │ └─ Atualiza OVERLAY ────────┼────┐                                          │
│  │                             │    │                                          │
│  │ ┌───────────────────────────┼────┘   OVERLAY NA TELA                        │
│  │ │  🎯 APOSTAR              │         ┌─────────────────────────┐            │
│  │ │                          │         │ Último: 14              │            │
│  │ │  [Site Apostas]          ◄─────────┤ ▶ VIZINHOS 17           │            │
│  │ │                          │         │ R$ 20 (2x)              │            │
│  │ └──────────────────────────┘         └─────────────────────────┘            │
│  │                             │                                               │
│  └─────────────────────────────┘                                               │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Arquivos Modificados

| Arquivo | Modificação |
|---------|-------------|
| `bridge.py` | Adicionado geração de sugestões e controle de Martingale |
| `websocket_server.py` | Adicionado envio de sugestões de volta para a extensão |
| `main.py` (Integracao) | Ajustado callback para retornar resultado |
| `manifest.json` | Adicionado content_scripts para overlay |
| `background.js` | Adicionado handler para sugestões e envio para content |
| **NOVO** `content.js` | Overlay de sugestões |
| **NOVO** `overlay.css` | Estilos do overlay |

## Como Usar

### 1. Configurar Servidor

```bash
cd "RoletaV11\Extrator Beat\Integracao Escuta x Roleta"
python main.py
```

O servidor iniciará em `ws://localhost:8765`.

### 2. Configurar Extensão para Android

Para conectar ao servidor na nuvem/PC, edite `background.js`:

```javascript
const WS_CONFIG = {
  url: 'ws://SEU_IP_OU_DOMINIO:8765',  // ← Alterar aqui
  reconnectInterval: 5000,
  maxReconnectAttempts: 10
};
```

### 3. Instalar no Kiwi Browser (Android)

1. Instale o **Kiwi Browser** da Play Store
2. Vá em `...` > `Extensions` > `+ (from .zip or folder)`
3. Selecione a pasta `extensao_chrome` ou o arquivo `.zip`
4. Ative a extensão

### 4. Usar

1. Abra o site de apostas no Kiwi Browser
2. Clique no popup da extensão e inicie o monitoramento
3. O overlay aparecerá automaticamente com sugestões

## Estados do Overlay

| Estado | Cor | Significado |
|--------|-----|-------------|
| 🎯 APOSTAR | Verde | Sugestão ativa - apostar na região indicada |
| ⏸️ PULAR | Laranja | Não apostar nesta rodada |
| ⏳ AGUARDANDO | Cinza | Aguardando dados/conexão |

## Martingale

O sistema rastreia perdas consecutivas:
- Primeira aposta: 1x
- Após 1 perda: 2x
- Após 2 perdas: 4x
- Após 3 perdas: 8x
- Após 4+ perdas: 16x

## Estrutura de Sugestão JSON

```json
{
  "type": "sugestao",
  "data": {
    "tipo": "sugestao",
    "acao": "APOSTAR",
    "regiao": "Vizinhos do 17",
    "centro": 17,
    "numeros": [17, 34, 6, ...],
    "estrategia": "SDA-7",
    "confianca": 75,
    "ultimo_numero": 14,
    "martingale": "2x"
  }
}
```
