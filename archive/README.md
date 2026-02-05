# Roleta Cloud

Backend para processamento de roleta em tempo real com WebSocket SSL.

## 🚀 Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## ✨ Features

- **SDA17 Strategy**: Análise de forças com regressão linear
- **Triple Rate Advisor**: Sistema de veto baseado em tendência multi-timeframe
- **Martingale Inteligente**: Janela de 5 jogadas com 3 níveis
- **Database Logging**: SQLite para análise posterior
- **WebSocket SSL**: Comunicação segura em tempo real

## 📡 Endpoints

| Protocolo | URL |
|-----------|-----|
| WebSocket | `wss://roleta.xma-ia.com:8765` |

## 📁 Estrutura

```
├── app_config/     # Configurações (Pydantic Settings)
├── main.py         # Entry point
├── auth/           # Middleware de autenticação
├── core/           # Física da roleta
├── models/         # Modelos Pydantic
├── server/         # WebSocket handler & Logic
├── state/          # GameState, Timeline, BetAdvisor
├── strategies/     # SDA17 Strategy
├── database/       # SQLite repository & Service
└── tools/          # Scripts e Ferramentas (Dashboard, Backtest, Analysis)
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
{
  "type": "sugestao",
  "data": {
    "acao": "APOSTAR",
    "centro": 2,
    "numeros": [4, 21, 2, 25, 17],
    "martingale": "1x",
    "gale_display": "G1 2/5",
    "bet_advice": {
      "should_bet": true,
      "confidence": "alta",
      "reason": "📈 CRESCENTE (75% > 50% > 42%)"
    }
  }
}
```

## 🎯 Triple Rate Advisor

Sistema de veto baseado em análise de tendência:

| Condição | Decisão |
|----------|---------|
| C4 >= M6 >= L12 | ✅ APOSTAR (crescente) |
| C4 >= M6 | ✅ APOSTAR (estável) |
| C4 < M6 | ⛔ PULAR (decrescente) |
| C4 < 25% | ⛔ PULAR (cold streak) |

## 📊 Database

Todas as decisões são logadas em SQLite (`data/decisions.db`) para análise posterior.

```sql
SELECT final_action, COUNT(*) FROM decisions GROUP BY final_action;
```

## 📄 License

MIT
