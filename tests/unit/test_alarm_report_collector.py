from datetime import date

import pytest

import src.alarm_report_collector as collector


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeAuthManager:
    origin_url = "https://example.test"
    referer_url = "https://example.test/"

    def get_valid_token(self, forcar_renovacao=False):
        return "test-token"


def api_item(contract_id, top_zone=None):
    return {
        "contractIdErp": contract_id,
        "customerIdErp": contract_id + 100,
        "alphanumeric": f"C{contract_id}",
        "siteId": 1,
        "startDate": "2024-01-02T00:00:00",
        "endDate": None,
        "contractType": "Smart Alarm",
        "branch": "FILIAL TESTE",
        "departmentId": 4,
        "messageCount": 12,
        "socialReason": "CLIENTE TESTE",
        "address": "RUA TESTE, 1, CENTRO - CIDADE, MG, 30180002",
        "topZone": top_zone,
    }


def test_coletar_relatorio_pagina_todas_as_paginas_e_salva_snapshot(monkeypatch):
    paginas = {
        1: {
            "contracts": {
                "pageCount": 2,
                "totalItemCount": 2,
                "pageNumber": 1,
                "pageSize": 1,
                "hasNextPage": True,
                "items": [
                    api_item(
                        10,
                        {
                            "zoneNumber": 3,
                            "zoneDescription": "Entrada",
                            "partitionNumber": -1,
                            "partitionDescription": "Sistema",
                            "triggerCount": 8,
                        },
                    )
                ],
            }
        },
        2: {
            "contracts": {
                "pageCount": 2,
                "totalItemCount": 2,
                "pageNumber": 2,
                "pageSize": 1,
                "hasNextPage": False,
                "items": [api_item(11)],
            }
        },
    }
    requisicoes = []

    class FakeClient:
        def __init__(self, timeout):
            assert timeout == collector.REQUEST_TIMEOUT_SECONDS

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, params, headers, content):
            requisicoes.append((url, params, headers, content))
            return FakeResponse(paginas[params["page"]])

    salvo = {}
    monkeypatch.setattr(collector, "API_BASE_URL", "https://api.example.test")
    monkeypatch.setattr(collector, "API_ENDPOINT", "/reports/contracts")
    monkeypatch.setattr(collector, "DEPARTMENTS_IDS", "1,4,6")
    monkeypatch.setattr(collector, "PAGE_SIZE", 1)
    monkeypatch.setattr(collector, "REQUEST_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(collector, "auth_manager", FakeAuthManager())
    monkeypatch.setattr(collector.httpx, "Client", FakeClient)

    def salvar(**kwargs):
        salvo.update(kwargs)
        return 42

    monkeypatch.setattr(collector, "salvar_snapshot_relatorio_contratos", salvar)

    snapshot_id = collector.coletar_relatorio_contratos(
        date(2026, 11, 17), date(2026, 11, 24)
    )

    assert snapshot_id == 42
    assert len(requisicoes) == 2
    assert [request[1]["page"] for request in requisicoes] == [1, 2]
    assert all(request[1]["pageSize"] == 1 for request in requisicoes)
    assert all(request[1]["departmentsIds"] == "1,4,6" for request in requisicoes)
    assert salvo["period_start"] == date(2026, 11, 17)
    assert salvo["period_end"] == date(2026, 11, 24)
    assert salvo["total_item_count"] == 2
    assert salvo["items"][0]["zona_disparos"] == "Entrada"
    assert salvo["items"][0]["disparos"] == 8
    assert salvo["items"][0]["message_count"] == 12
    assert salvo["items"][0]["empresa"] == "FILIAL TESTE"
    assert salvo["items"][0]["estado"] == "MG"
    assert salvo["items"][0]["data"] == date(2026, 11, 24)
    assert salvo["items"][0]["mes"] == 11
    assert salvo["items"][1]["zona_disparos"] is None
    assert salvo["items"][1]["disparos"] == 12


def test_normalizar_item_preserva_incerteza_do_departamento_semax():
    item = api_item(12)
    item.update({"departmentId": 17, "contractType": "Alarme Cabeado"})

    resultado = collector._normalizar_item(item, date(2026, 11, 24))

    assert resultado["departamento"] == "SEMAX"
    assert resultado["department_mapping_confidence"] == "INFERIDO"


def test_coletar_relatorio_nao_salva_resultado_paginado_incompleto(monkeypatch):
    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, params, headers, content):
            return FakeResponse(
                {
                    "contracts": {
                        "pageCount": 1,
                        "totalItemCount": 2,
                        "pageNumber": 1,
                        "pageSize": 25,
                        "hasNextPage": False,
                        "items": [api_item(10)],
                    }
                }
            )

    monkeypatch.setattr(collector, "API_BASE_URL", "https://api.example.test")
    monkeypatch.setattr(collector, "DEPARTMENTS_IDS", "1")
    monkeypatch.setattr(collector, "PAGE_SIZE", 25)
    monkeypatch.setattr(collector, "REQUEST_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(collector, "auth_manager", FakeAuthManager())
    monkeypatch.setattr(collector.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        collector,
        "salvar_snapshot_relatorio_contratos",
        lambda **kwargs: pytest.fail("Não deveria salvar um snapshot incompleto"),
    )

    with pytest.raises(ValueError, match="contratos únicos recebidos"):
        collector.coletar_relatorio_contratos(
            date(2026, 11, 17), date(2026, 11, 24)
        )


def test_coletar_relatorio_salva_snapshot_vazio(monkeypatch):
    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, params, headers, content):
            return FakeResponse(
                {
                    "contracts": {
                        "pageCount": 0,
                        "totalItemCount": 0,
                        "pageNumber": 0,
                        "pageSize": 25,
                        "hasNextPage": False,
                        "items": [],
                    }
                }
            )

    salvo = {}
    monkeypatch.setattr(collector, "API_BASE_URL", "https://api.example.test")
    monkeypatch.setattr(collector, "DEPARTMENTS_IDS", "1")
    monkeypatch.setattr(collector, "PAGE_SIZE", 25)
    monkeypatch.setattr(collector, "REQUEST_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(collector, "auth_manager", FakeAuthManager())
    monkeypatch.setattr(collector.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        collector,
        "salvar_snapshot_relatorio_contratos",
        lambda **kwargs: salvo.update(kwargs) or 74,
    )

    assert collector.coletar_relatorio_contratos(
        date(2026, 11, 17), date(2026, 11, 24)
    ) == 74
    assert salvo["page_count"] == 0
    assert salvo["items"] == []


def test_coletar_relatorio_acomoda_mudanca_de_total_e_remove_contrato_repetido(
    monkeypatch,
):
    paginas = {
        1: {
            "contracts": {
                "pageCount": 2,
                "totalItemCount": 3,
                "pageNumber": 1,
                "pageSize": 2,
                "hasNextPage": True,
                "items": [api_item(10), api_item(11)],
            }
        },
        2: {
            "contracts": {
                "pageCount": 3,
                "totalItemCount": 5,
                "pageNumber": 2,
                "pageSize": 2,
                "hasNextPage": True,
                "items": [api_item(11), api_item(12)],
            }
        },
        3: {
            "contracts": {
                "pageCount": 3,
                "totalItemCount": 5,
                "pageNumber": 3,
                "pageSize": 2,
                "hasNextPage": False,
                "items": [api_item(13), api_item(14)],
            }
        },
    }

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, params, headers, content):
            return FakeResponse(paginas[params["page"]])

    salvo = {}
    monkeypatch.setattr(collector, "API_BASE_URL", "https://api.example.test")
    monkeypatch.setattr(collector, "DEPARTMENTS_IDS", "1")
    monkeypatch.setattr(collector, "PAGE_SIZE", 2)
    monkeypatch.setattr(collector, "REQUEST_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(collector, "auth_manager", FakeAuthManager())
    monkeypatch.setattr(collector.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        collector,
        "salvar_snapshot_relatorio_contratos",
        lambda **kwargs: salvo.update(kwargs) or 75,
    )

    assert collector.coletar_relatorio_contratos(
        date(2026, 11, 17), date(2026, 11, 24)
    ) == 75
    assert salvo["page_count"] == 3
    assert salvo["total_item_count"] == 5
    assert [item["num_contrato"] for item in salvo["items"]] == [10, 11, 12, 13, 14]


def test_request_pacer_aplica_intervalo_minimo(monkeypatch):
    agora = [10.0]
    esperas = []

    def dormir(segundos):
        esperas.append(segundos)
        agora[0] += segundos

    monkeypatch.setattr(collector.time, "monotonic", lambda: agora[0])
    monkeypatch.setattr(collector.time, "sleep", dormir)

    pacer = collector.RequestPacer(1.0)
    pacer.wait()
    agora[0] += 0.2
    pacer.wait()

    assert esperas == pytest.approx([0.8])
    assert agora[0] == pytest.approx(11.0)
