import json
import os
import time
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class ExtractorService:
    def __init__(self, root_path: str):
        self.root_path = root_path
        self.providers_path = os.path.join(root_path, "providers")
        self.mesas_path = os.path.join(root_path, "mesas")
        self.providers = self._load_providers()
        
    def _load_providers(self) -> Dict[str, dict]:
        providers = {}
        try:
            for file in os.listdir(self.providers_path):
                if file.endswith(".json"):
                    with open(os.path.join(self.providers_path, file), 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        provider_name = config.get("provider")
                        if provider_name:
                            providers[provider_name] = config
            logger.info(f"Carragados {len(providers)} templates de providers")
        except Exception as e:
            logger.error(f"Erro ao carregar templates de providers: {e}")
        return providers

    def _detect_provider(self, url: str) -> str:
        """Detecta o provider baseado na URL."""
        for provider, config in self.providers.items():
            patterns = config.get("detection", {}).get("urlPatterns", [])
            if any(pattern in url for pattern in patterns):
                return provider
        return "evolution"  # Fallback padrão

    def _generate_mesa_id(self, url: str, provider: str) -> str:
        """Gera um ID único e amigável para a mesa."""
        # Tenta extrair ID da mesa da URL ou usa um hash
        path_parts = url.split("/")
        last_part = path_parts[-1] if path_parts[-1] else path_parts[-2]
        clean_name = last_part.replace("-", "_").lower()
        return f"{provider}_{clean_name}"

    def process_mesa(self, data: Dict) -> Dict:
        """Processa snapshot DOM e gera configuração de mesa."""
        url = data.get("url", "")
        provider = self._detect_provider(url)
        base_config = self.providers.get(provider, self.providers.get("evolution"))
        
        # Snapshot DOM enriquecido enviado pela extensão
        dom_snapshot = data.get("dom_snapshot", {})
        
        # Mesclagem básica (por enquanto apenas replica o base, no futuro pode ser dinâmico)
        mesa_config = base_config.copy()
        mesa_config["mesa_info"] = {
            "url": url,
            "captured_at": time.time(),
            "elements_found": dom_snapshot.get("stats", {})
        }
        
        mesa_id = self._generate_mesa_id(url, provider)
        file_path = os.path.join(self.mesas_path, f"{mesa_id}.json")
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(mesa_config, f, indent=2, ensure_ascii=False)
            logger.info(f"Configuração da mesa salva: {mesa_id}")
        except Exception as e:
            logger.error(f"Erro ao salvar config da mesa: {e}")
            return {"status": "error", "message": str(e)}

        return {
            "mesa_id": mesa_id,
            "config": mesa_config,
            "status": "success"
        }

    def list_mesas(self) -> List[Dict]:
        """Lista todas as mesas configuradas."""
        mesas = []
        try:
            for file in os.listdir(self.mesas_path):
                if file.endswith(".json"):
                    with open(os.path.join(self.mesas_path, file), 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        mesas.append({
                            "id": file.replace(".json", ""),
                            "name": config.get("mesa_info", {}).get("url", file),
                            "provider": config.get("provider")
                        })
        except Exception as e:
            logger.error(f"Erro ao listar mesas: {e}")
        return mesas

    def get_mesa_config(self, mesa_id: str) -> Optional[dict]:
        """Retorna config de uma mesa específica."""
        file_path = os.path.join(self.mesas_path, f"{mesa_id}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Erro ao ler config da mesa {mesa_id}: {e}")
        return None
