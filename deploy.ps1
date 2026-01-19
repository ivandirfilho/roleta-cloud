# Deploy para Windows PowerShell
# Uso: .\deploy.ps1 "mensagem do commit"

param([string]$CommitMessage = "")

$SERVER = "root@187.45.181.75"
$REMOTE_PATH = "~/roleta-cloud"
$SERVICE_NAME = "roleta-cloud"

Write-Host "🚀 Iniciando deploy..." -ForegroundColor Green

# 1. Git commit e push
if ($CommitMessage) {
    Write-Host "📝 Commitando: $CommitMessage" -ForegroundColor Yellow
    git add -A
    git commit -m $CommitMessage
    git push origin main
} else {
    Write-Host "⚠️ Sem mensagem de commit, apenas deploy" -ForegroundColor Yellow
}

# 2. Copiar arquivos para servidor
Write-Host "📦 Copiando arquivos..." -ForegroundColor Yellow

$files = @(
    "config.py",
    "main.py",
    "requirements.txt"
)

foreach ($file in $files) {
    scp $file "${SERVER}:${REMOTE_PATH}/"
}

$folders = @("auth", "core", "models", "server", "state", "strategies")

foreach ($folder in $folders) {
    scp -r "$folder/*" "${SERVER}:${REMOTE_PATH}/${folder}/"
}

# 3. Reiniciar serviço
Write-Host "🔄 Reiniciando serviço..." -ForegroundColor Yellow
ssh $SERVER "systemctl restart $SERVICE_NAME"

# 4. Verificar status
Write-Host "✅ Verificando status..." -ForegroundColor Yellow
ssh $SERVER "systemctl status $SERVICE_NAME --no-pager"

Write-Host "🎉 Deploy concluído!" -ForegroundColor Green
