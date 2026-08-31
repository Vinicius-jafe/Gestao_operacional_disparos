import os
import logging
import requests

logger = logging.getLogger(__name__)


class EmiveAuthManager:
    def __init__(self):
        self.jwt_token = os.getenv("EMIVE_JWT_TOKEN", "").strip()
        self.refresh_token = os.getenv("EMIVE_REFRESH_TOKEN", "").strip()
        self.refresh_url = os.getenv(
            "EMIVE_REFRESH_URL",
            "https://ap-speed-api-prd.azurewebsites.net/identity/api/Identity/refreshToken",
        )
        self.origin_url = os.getenv("EMIVE_ORIGIN_URL", "https://speed.emive.app.br")
        self.referer_url = os.getenv("EMIVE_REFERER_URL", "https://speed.emive.app.br/")

    def _renovar_via_emive(self) -> str:
        if not self.refresh_token:
            raise ValueError("EMIVE_REFRESH_TOKEN nao configurado no .env")

        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": self.origin_url,
            "referer": self.referer_url,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        body = {
            "token": self.jwt_token,
            "refreshToken": self.refresh_token,
        }

        print("[AUTH] Renovando token direto na API da Emive...")
        response = requests.post(self.refresh_url, json=body, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            self.jwt_token = data.get("accessToken", self.jwt_token)
            self.refresh_token = data.get("refreshToken", self.refresh_token)
            print("[AUTH] Token renovado com sucesso pela Emive!")
            return self.jwt_token
        
        raise RuntimeError(f"Falha ao renovar token na Emive: {response.status_code} - {response.text}")

    def get_valid_token(self, forcar_renovacao: bool = False) -> str:
        if forcar_renovacao:
            return self._renovar_via_emive()
        
        if not self.jwt_token:
            raise ValueError("EMIVE_JWT_TOKEN nao configurado no .env")
            
        return self.jwt_token


auth_manager = EmiveAuthManager()