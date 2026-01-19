---
description: Deploy Roleta Cloud para servidor de produção
---

# Deploy Roleta Cloud

// turbo-all

## Pré-requisitos
- SSH configurado sem senha para `root@187.45.181.75`
- Git remoto configurado

## Deploy Rápido (PowerShell)

1. Abra terminal na pasta do projeto:
```powershell
cd "c:\Users\Windows\Desktop\Programa Assitente\Roleta Cloud"
```

2. Execute o deploy com commit:
```powershell
.\deploy.ps1 "descrição da mudança"
```

Ou apenas deploy sem commit:
```powershell
.\deploy.ps1
```

## Deploy Manual

1. Commit e push:
```powershell
git add -A
git commit -m "descrição"
git push origin main
```

2. Copiar para servidor:
```powershell
scp -r server/* root@187.45.181.75:~/roleta-cloud/server/
```

3. Reiniciar:
```powershell
ssh root@187.45.181.75 "systemctl restart roleta-cloud"
```

## Ver Logs

```powershell
ssh root@187.45.181.75 "tail -f /root/roleta-cloud/server.log"
```
