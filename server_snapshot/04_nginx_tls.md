# Nginx + TLS

## Sites habilitados
```
roleta
```

## server_name + proxy_pass por site
```
server_name roleta.xma-ia.com www.roleta.xma-ia.com;
proxy_pass http://127.0.0.1:8765;
listen 443 ssl; # managed by Certbot
listen 80;
server_name roleta.xma-ia.com www.roleta.xma-ia.com;
```

## Certificados (certbot)
```
  Certificate Name: roleta.xma-ia.com
    Domains: roleta.xma-ia.com www.roleta.xma-ia.com
    Expiry Date: 2026-07-06 00:28:14+00:00 (VALID: 25 days)
```
