#!/bin/bash
# Setup script para Roleta Cloud

# 1. Configurar SSH key
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC1KZ9zkThmkoRiVc7y6FsTKGQUDIfAKw0a6qyGMdOhfTkZVzzLcV/euBGBGRgpaEMZEGxvr4pCsA4rY9wPnSVKk+6IH+m0nMKuPtVENPlUhfbJa1wWvDhmI3n9tpsTu+7zKwTp0ZLbC4cpyeZZjImo73wnTTwGQInOHlH36jxWQstQx7MOSwP7tXVB8syj9o5FaF6hLBOd7Q74esipPVxXnIF3OgJNcPbFkdGNzrVyNyhCEdXpcqVvcuN41XQH2wauDZsn/722Xq/Lv7jPf0/ePe9L7MUsxfHk+heSeevcLb2DF8eaJcdWnwHBFdxtld4YgXmzBYv4m1fpjxVlEKODR+Uhuda0nhTkuda2LX5uD7RczpdGwa8GN3i22p6Ry6kWxBRX+uoK+qbrynOJZ+6ZL5geUBDSpoC/8ATBDi5YAYJFC5GogY/YwW9Rd6ldNn1H/Auoh/i5qRRqLaNJRC/0ccUv8YPjjM9unOIyCoAY2ptkcBzJHez5Gazt5XkbMebrrtlq8Zl9sC54lsHTfvlSh3HytCcp2TzLz+Gf7HvFPwQ57+k47TZes79HpiytGC42RBmJJ7sh573iKvM8KeSSokB50Kw8rwkXDM8ZqKbz+yGBIaotMvD7t+Ihf/LUvDpmCbxZ4C1TqkXPZ4zT9RO5vO3szbhC28yhW0xRqX1keQ== windows@IVANDIR" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

echo "✅ Chave SSH configurada!"

# 2. Criar diretório do projeto
mkdir -p ~/roleta-cloud
echo "✅ Diretório criado!"

# 3. Abrir porta no firewall
ufw allow 8765/tcp 2>/dev/null || true
echo "✅ Porta 8765 liberada!"

echo ""
echo "🎉 Setup concluído! Agora copie os arquivos do projeto."
