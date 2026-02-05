#!/bin/bash
# deploy.sh - Script de deploy para Roleta Cloud
# Uso: ./deploy.sh [mensagem do commit]

set -e

# Configurações
SERVER="root@187.45.181.75"
REMOTE_PATH="~/roleta-cloud"
SERVICE_NAME="roleta-cloud"

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Iniciando deploy...${NC}"

# 1. Git commit e push
if [ -n "$1" ]; then
    echo -e "${YELLOW}📝 Commitando: $1${NC}"
    git add -A
    git commit -m "$1" || echo "Nada para commitar"
    git push origin main
else
    echo -e "${YELLOW}⚠️ Sem mensagem de commit, apenas deploy${NC}"
fi

# 2. Copiar arquivos para servidor
echo -e "${YELLOW}📦 Copiando arquivos...${NC}"
scp -r config.py main.py requirements.txt $SERVER:$REMOTE_PATH/
scp -r auth/ core/ models/ server/ state/ strategies/ dashboard/ $SERVER:$REMOTE_PATH/

# 3. Reiniciar serviço
echo -e "${YELLOW}🔄 Reiniciando serviço...${NC}"
ssh $SERVER "systemctl restart $SERVICE_NAME"

# 4. Verificar status
echo -e "${YELLOW}✅ Verificando status...${NC}"
ssh $SERVER "systemctl status $SERVICE_NAME --no-pager"

echo -e "${GREEN}🎉 Deploy concluído!${NC}"
