# Roleta Cloud

Backend para processamento de roleta em tempo real com WebSocket SSL.

## 🚀 Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## 📡 Endpoints

| Protocolo | URL |
|-----------|-----|
| WebSocket | `wss://roleta.xma-ia.com:8765` |

## 📁 Estrutura

```
├── config.py       # Configurações
├── main.py         # Entry point
├── auth/           # Middleware de autenticação
├── core/           # Física da roleta
├── models/         # Modelos Pydantic
├── server/         # WebSocket handler
├── state/          # GameState e Timeline
├── strategies/     # SDA Strategy
└── deploy/         # Arquivos de deploy
```

## 🔧 Deploy

```bash
# Copiar para servidor
scp -r * root@servidor:~/roleta-cloud/

# Instalar e rodar
ssh root@servidor "cd roleta-cloud && pip3 install -r requirements.txt && systemctl restart roleta-cloud"
```

## 📝 Mensagens WebSocket

### Entrada
```json
{"type": "novo_resultado", "numero": 17, "direcao": "horario"}
```

### Saída
```json
{"type": "sugestao", "data": {"acao": "APOSTAR", "centro": 2, "numeros": [4,21,2,25,17]}}
```

## 📄 License

MIT
