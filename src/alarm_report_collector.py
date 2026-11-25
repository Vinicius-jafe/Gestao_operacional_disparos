import logging
import math
import os
import re
import time
from datetime import date, timedelta
from typing import Any, Dict, Tuple

import httpx

from src.auth import auth_manager
from src.database import normalizar_nome_filial, salvar_snapshot_relatorio_contratos


logger = logging.getLogger(__name__)

API_BASE_URL = os.getenv("EMIVE_API_BASE_URL", "").rstrip("/")
API_ENDPOINT = os.getenv(
    "EMIVE_ALARM_REPORT_ENDPOINT",
    "/operations/api/Reports/GetAlarmEventContractsReport",
)
DEPARTMENTS_IDS = os.getenv(
    "EMIVE_ALARM_REPORT_DEPARTMENTS_IDS",
    ",".join(str(department_id) for department_id in range(1, 51)),
)
PAGE_SIZE = int(os.getenv("EMIVE_ALARM_REPORT_PAGE_SIZE", "25"))
INTERVAL_SECONDS = int(os.getenv("EMIVE_ALARM_REPORT_INTERVAL_SECONDS", "3600"))
REQUEST_INTERVAL_SECONDS = float(
    os.getenv("EMIVE_ALARM_REPORT_REQUEST_INTERVAL_SECONDS", "1")
)
REQUEST_TIMEOUT_SECONDS = 120.0
MAX_PAGINATION_ATTEMPTS = 2
WINDOW_DAYS = 7
DEPARTMENT_MAPPING = {
    1: ("Alarme Cabeado", "OFICIAL"),
    4: ("Smart Alarm", "OFICIAL"),
    6: ("Central", "OFICIAL"),
    3: ("Smart Portaria", "INFERIDO"),
    10: ("TOTEM", "INFERIDO"),
    15: ("DGP", "INFERIDO"),
    17: ("SEMAX", "INFERIDO"),
}
STATE_PATTERN = re.compile(r",\s*([A-Z]{2}),\s*\d{5}-?\d{3}\s*$", re.IGNORECASE)


class RequestPacer:
    def __init__(self, interval_seconds: float):
        if not math.isfinite(interval_seconds) or interval_seconds < 0:
            raise ValueError("O intervalo mínimo entre requisições deve ser >= 0.")
        self.interval_seconds = interval_seconds
        self.last_request_at: float | None = None

    def wait(self) -> None:
        if self.last_request_at is not None:
            elapsed = time.monotonic() - self.last_request_at
            remaining = self.interval_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self.last_request_at = time.monotonic()


def _optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Campo inválido no relatório: {field}") from error


def _normalizar_item(item: Dict[str, Any], period_end: date) -> dict:
    if not isinstance(item, dict):
        raise ValueError("Cada item de contracts.items deve ser um objeto.")
    contract_id_erp = _optional_int(item.get("contractIdErp"), "contractIdErp")
    if contract_id_erp is None:
        raise ValueError("Item do relatório sem contractIdErp.")

    try:
        message_count = int(item["messageCount"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Item do relatório sem messageCount válido.") from error

    top_zone = item.get("topZone")
    if top_zone is not None and not isinstance(top_zone, dict):
        raise ValueError("Campo topZone deve ser um objeto ou null.")
    top_zone = top_zone or {}
    department_id = _optional_int(item.get("departmentId"), "departmentId")
    departamento, confianca_departamento = DEPARTMENT_MAPPING.get(
        department_id,
        (
            str(item.get("contractType") or "OUTROS").strip(),
            "CONTRACT_TYPE",
        ),
    )
    address = str(item.get("address") or "").strip()
    state_match = STATE_PATTERN.search(address)
    top_zone_trigger_count = _optional_int(
        top_zone.get("triggerCount"), "topZone.triggerCount"
    )
    branch = str(item.get("branch") or item.get("company") or "NAO INFORMADA")

    return {
        "cod_contrato": item.get("alphanumeric"),
        "empresa": normalizar_nome_filial(branch, address),
        "razao_social": item.get("socialReason"),
        "num_contrato": contract_id_erp,
        "departamento": departamento,
        "department_id": department_id,
        "department_mapping_confidence": confianca_departamento,
        "disparos": (
            top_zone_trigger_count
            if top_zone_trigger_count is not None
            else message_count
        ),
        "message_count": message_count,
        "zona_disparos": top_zone.get("zoneDescription"),
        "data": period_end,
        "mes": period_end.month,
        "estado": state_match.group(1).upper() if state_match else None,
    }


def _request_page(
    client: httpx.Client,
    token: str,
    period_start: date,
    period_end: date,
    page: int,
    request_pacer: RequestPacer,
) -> Tuple[Dict[str, Any], str]:
    url = (
        f"{API_BASE_URL}{API_ENDPOINT}/"
        f"{period_start.isoformat()}/{period_end.isoformat()}"
    )
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {token}",
        "origin": auth_manager.origin_url,
        "referer": auth_manager.referer_url,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36"
        ),
    }
    params = {
        "page": page,
        "pageSize": PAGE_SIZE,
        "departmentsIds": DEPARTMENTS_IDS,
    }
    request_pacer.wait()
    response = client.post(url, params=params, headers=headers, content=b"")
    if response.status_code == 401:
        token = auth_manager.get_valid_token(forcar_renovacao=True)
        headers["authorization"] = f"Bearer {token}"
        request_pacer.wait()
        response = client.post(url, params=params, headers=headers, content=b"")

    if response.status_code != 200:
        raise RuntimeError(
            f"API do relatório retornou HTTP {response.status_code} na página {page}."
        )

    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("contracts"), dict):
        raise ValueError("Resposta da API não contém o objeto contracts esperado.")
    return payload["contracts"], token


def coletar_relatorio_contratos(
    period_start: date | None = None,
    period_end: date | None = None,
) -> int:
    if not API_BASE_URL:
        raise ValueError("EMIVE_API_BASE_URL não configurada.")
    if PAGE_SIZE <= 0:
        raise ValueError("EMIVE_ALARM_REPORT_PAGE_SIZE deve ser maior que zero.")
    if not math.isfinite(REQUEST_INTERVAL_SECONDS) or REQUEST_INTERVAL_SECONDS < 0:
        raise ValueError(
            "EMIVE_ALARM_REPORT_REQUEST_INTERVAL_SECONDS deve ser >= 0."
        )
    if not DEPARTMENTS_IDS.strip():
        raise ValueError("EMIVE_ALARM_REPORT_DEPARTMENTS_IDS não pode ser vazio.")

    if period_end is None:
        period_end = date.today()
    if period_start is None:
        period_start = period_end - timedelta(days=WINDOW_DAYS)
    if period_start > period_end:
        raise ValueError("period_start deve ser anterior ou igual a period_end.")

    token = auth_manager.get_valid_token()
    request_pacer = RequestPacer(REQUEST_INTERVAL_SECONDS)
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for attempt in range(1, MAX_PAGINATION_ATTEMPTS + 1):
            itens_por_contrato = {}
            duplicados_descartados = 0
            page = 1
            page_count = 0
            total_item_count = 0
            page_size = 0
            max_pages = 0

            while True:
                contracts, token = _request_page(
                    client,
                    token,
                    period_start,
                    period_end,
                    page,
                    request_pacer,
                )
                try:
                    page_count = int(contracts["pageCount"])
                    total_item_count = int(contracts["totalItemCount"])
                    returned_page_number = int(contracts["pageNumber"])
                    received_page_size = int(contracts["pageSize"])
                    has_next_page = contracts["hasNextPage"]
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"Metadados de paginação inválidos na página {page}."
                    ) from error

                if (
                    page_count < 0
                    or total_item_count < 0
                    or received_page_size <= 0
                    or not isinstance(has_next_page, bool)
                ):
                    raise ValueError(
                        f"Metadados de paginação inconsistentes na página {page}."
                    )
                if not isinstance(contracts.get("items"), list):
                    raise ValueError(
                        f"Resposta da página {page} não contém contracts.items como lista."
                    )
                if page == 1:
                    if page_count == 0:
                        if (
                            total_item_count != 0
                            or contracts["items"]
                            or returned_page_number not in (0, 1)
                            or has_next_page
                        ):
                            raise ValueError(
                                "Metadados da resposta vazia são inconsistentes."
                            )
                    elif returned_page_number != 1:
                        raise ValueError(
                            "Metadados da primeira página são inconsistentes."
                        )
                    page_size = received_page_size
                    max_pages = max(1, page_count) + max(
                        10, math.ceil(max(1, page_count) * 0.05)
                    )
                elif returned_page_number != page:
                    raise ValueError(
                        f"A API retornou a página {returned_page_number} "
                        f"quando foi solicitada a página {page}."
                    )
                elif received_page_size != page_size:
                    raise ValueError(
                        f"O tamanho da página mudou durante a coleta "
                        f"(página {page}: {received_page_size}, esperado: {page_size})."
                    )

                for item in contracts["items"]:
                    normalizado = _normalizar_item(item, period_end)
                    contrato_id = normalizado["num_contrato"]
                    if contrato_id in itens_por_contrato:
                        duplicados_descartados += 1
                    itens_por_contrato[contrato_id] = normalizado

                if not has_next_page:
                    break
                if page >= max_pages:
                    raise ValueError(
                        "A paginação continuou além do limite seguro "
                        f"de {max_pages} páginas."
                    )
                page += 1

            itens = list(itens_por_contrato.values())
            if len(itens) == total_item_count:
                logger.info(
                    "Paginação concluída: %s itens únicos; %s repetidos descartados.",
                    len(itens),
                    duplicados_descartados,
                )
                break

            if attempt == MAX_PAGINATION_ATTEMPTS:
                raise ValueError(
                    "A paginação mudou durante todas as tentativas: "
                    f"{len(itens)} contratos únicos recebidos, "
                    f"mas a última resposta informa {total_item_count}."
                )
            logger.warning(
                "A lista mudou durante a coleta (%s contratos únicos; API informa %s). "
                "Reiniciando a paginação (tentativa %s/%s).",
                len(itens),
                total_item_count,
                attempt + 1,
                MAX_PAGINATION_ATTEMPTS,
            )

    snapshot_id = salvar_snapshot_relatorio_contratos(
        period_start=period_start,
        period_end=period_end,
        page_size=page_size,
        page_count=page_count,
        total_item_count=total_item_count,
        items=itens,
    )
    logger.info(
        "Snapshot %s salvo: %s itens, período %s a %s.",
        snapshot_id,
        len(itens),
        period_start,
        period_end,
    )
    return snapshot_id


def loop_coleta_horaria() -> None:
    if INTERVAL_SECONDS <= 0:
        raise ValueError(
            "EMIVE_ALARM_REPORT_INTERVAL_SECONDS deve ser maior que zero."
        )
    while True:
        inicio = time.monotonic()
        try:
            coletar_relatorio_contratos()
        except Exception:
            logger.exception("Falha ao coletar o relatório de contratos de alarmes.")

        restante = max(0, INTERVAL_SECONDS - (time.monotonic() - inicio))
        logger.info("Próxima coleta do relatório em %.0f segundos.", restante)
        time.sleep(restante)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    loop_coleta_horaria()
