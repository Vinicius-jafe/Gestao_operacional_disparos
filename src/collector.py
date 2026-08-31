import os
import time
from datetime import datetime, timedelta
import httpx
from src.auth import auth_manager
from src.database import sincronizar_dados_api

API_BASE_URL = os.getenv("EMIVE_API_BASE_URL", "").rstrip("/")
API_ENDPOINT = os.getenv(
    "EMIVE_API_PEAK_ENDPOINT", "/operations/api/Reports/GetPeakReports"
)
DEPARTAMENTOS_FILTRO = os.getenv("DEPARTAMENTOS_FILTRO", "1,4,6")
ORIGIN_URL = os.getenv("EMIVE_ORIGIN_URL", "")
REFERER_URL = os.getenv("EMIVE_REFERER_URL", "")


def extrair_e_gravar_disparos(horas_retroativas: int = 48) -> int:
    if not API_BASE_URL:
        print("[ERRO CRITICO] EMIVE_API_BASE_URL nao configurada.")
        return 0

    try:
        token = auth_manager.get_valid_token()
    except Exception as e:
        print(f"[ERRO DE AUTENTICACAO]: {e}")
        return 0

    agora = datetime.utcnow()
    inicio = agora - timedelta(hours=horas_retroativas)

    inicio_str = inicio.strftime("%Y-%m-%dT03:00:00.000Z")
    fim_str = agora.strftime("%Y-%m-%dT02:59:59.999Z")

    url = f"{API_BASE_URL}{API_ENDPOINT}/{inicio_str}/{fim_str}?departmentsIds={DEPARTAMENTOS_FILTRO}"

    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {token}",
        "origin": ORIGIN_URL,
        "referer": REFERER_URL,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Solicitando API"
        f" ({inicio_str} ate {fim_str})..."
    )

    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.get(url, headers=headers)

            if resp.status_code == 401:
                print("[AVISO] Token 401 recebido. Renovando...")
                token = auth_manager.get_valid_token(forcar_renovacao=True)
                headers["authorization"] = f"Bearer {token}"
                resp = client.get(url, headers=headers)

        if resp.status_code != 200:
            print(f"[ERRO API] Status {resp.status_code}: {resp.text}")
            return 0

        relatorio = resp.json().get("analyticalReport", [])
        return sincronizar_dados_api(relatorio)

    except Exception as e:
        print(f"[ERRO DE CONEXAO API]: {e}")
        return 0


def loop_horario():
    print("=== Coletor Horario Ativo (Deptos: 1,4,6) ===")
    while True:
        extrair_e_gravar_disparos(horas_retroativas=48)
        print("Aguardando 1 hora (3600s) para o proximo ciclo...")
        time.sleep(3600)


if __name__ == "__main__":
    loop_horario()