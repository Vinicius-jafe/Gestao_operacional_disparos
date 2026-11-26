from contextlib import contextmanager
from datetime import date

import pandas as pd
import pytest

import src.database as database


class FakeResult:
    def scalar_one(self):
        return 73


class FakeConnection:
    def __init__(self):
        self.executions = []

    def execute(self, statement, params=None):
        self.executions.append((str(statement), params))
        return FakeResult()


class FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def begin(self):
        yield self.connection


def report_item(contract_id):
    return {
        "cod_contrato": f"C{contract_id}",
        "empresa": "FILIAL TESTE",
        "razao_social": "CLIENTE TESTE",
        "num_contrato": contract_id,
        "departamento": "Smart Alarm",
        "department_id": 4,
        "department_mapping_confidence": "OFICIAL",
        "disparos": 8,
        "message_count": 12,
        "zona_disparos": "Entrada",
        "data": date(2026, 11, 24),
        "mes": 11,
        "estado": "MG",
    }


def test_salvar_snapshot_insere_metadados_e_itens_na_mesma_transacao(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(database, "engine", FakeEngine(connection))

    snapshot_id = database.salvar_snapshot_relatorio_contratos(
        period_start=date(2026, 11, 17),
        period_end=date(2026, 11, 24),
        page_size=25,
        page_count=1,
        total_item_count=1,
        items=[report_item(10)],
    )

    assert snapshot_id == 73
    assert len(connection.executions) == 2
    assert "INSERT INTO alarm_report_snapshots" in connection.executions[0][0]
    assert "INSERT INTO disparos_sensor" in connection.executions[1][0]
    assert connection.executions[1][1][0]["snapshot_id"] == 73


def test_salvar_snapshot_rejeita_itens_repetidos(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(database, "engine", FakeEngine(connection))

    with pytest.raises(ValueError, match="Contrato repetido"):
        database.salvar_snapshot_relatorio_contratos(
            period_start=date(2026, 11, 17),
            period_end=date(2026, 11, 24),
            page_size=25,
            page_count=1,
            total_item_count=2,
            items=[report_item(10), report_item(10)],
        )

    assert connection.executions == []


def test_carregar_relatorio_sensores_consulta_origens_unificadas(
    monkeypatch,
):
    chamadas = {}

    class ReadEngine:
        @contextmanager
        def connect(self):
            yield object()

    def ler_sql(consulta, conexao):
        chamadas["consulta"] = str(consulta)
        return pd.DataFrame()

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    resultado = database.carregar_relatorio_sensores()

    assert resultado.empty
    assert "FROM vw_disparos_sensor_unificados" in chamadas["consulta"]
    assert "origem_sensor" in chamadas["consulta"]


def test_carregar_periodos_analise_sensores_retorna_datas_e_horas_com_sensor(
    monkeypatch,
):
    chamadas = {}

    class ReadEngine:
        @contextmanager
        def connect(self):
            yield object()

    def ler_sql(consulta, conexao):
        chamadas["consulta"] = str(consulta)
        return pd.DataFrame(
            [{"dia": date(2026, 11, 10), "hora_cheia": 12}]
        )

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    resultado = database.carregar_periodos_analise_sensores()

    assert resultado.loc[0, "hora_cheia"] == 12
    assert "FROM vw_analise_disp_sensor" in chamadas["consulta"]
    assert "sensores_no_dia <> 'SEM SENSOR NO DIA'" in chamadas["consulta"]
    assert "hora_cheia BETWEEN 0 AND 23" in chamadas["consulta"]


def test_carregar_contratos_analise_sensores_filtra_data_e_hora(monkeypatch):
    chamadas = {}

    class ReadEngine:
        @contextmanager
        def connect(self):
            yield object()

    def ler_sql(consulta, conexao, params):
        chamadas["consulta"] = str(consulta)
        chamadas["params"] = params
        return pd.DataFrame(
            [
                {
                    "num_contrato": 10,
                    "departamento": "SMART ALARM",
                    "estado": "MG",
                }
            ]
        )

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    resultado = database.carregar_contratos_analise_sensores(
        date(2026, 11, 10), 12
    )

    assert resultado.loc[0, "num_contrato"] == 10
    assert "hora_cheia = :hora_analise" in chamadas["consulta"]
    assert chamadas["params"] == {
        "data_analise": date(2026, 11, 10),
        "hora_analise": 12,
    }


def test_carregar_contratos_analise_sensores_rejeita_hora_invalida():
    with pytest.raises(ValueError, match="entre 0 e 23"):
        database.carregar_contratos_analise_sensores(date(2026, 11, 10), 24)


def test_carregar_relatorio_sensores_filtra_datas_horas_e_contratos_no_banco(
    monkeypatch,
):
    chamadas = {}

    class ReadEngine:
        @contextmanager
        def connect(self):
            yield object()

    def ler_sql(consulta, conexao, params=None):
        chamadas["consulta"] = str(consulta)
        chamadas["params"] = params
        return pd.DataFrame()

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    database.carregar_relatorio_sensores_periodo(
        date(2026, 9, 1),
        date(2026, 9, 7),
        2,
        16,
    )

    assert "FROM vw_disparos_sensor_unificados d" in chamadas["consulta"]
    assert "d.data BETWEEN :data_inicio AND :data_fim" in chamadas["consulta"]
    assert "d.origem_sensor" in chamadas["consulta"]
    assert "a.dia BETWEEN :data_inicio AND :data_fim" in chamadas["consulta"]
    assert "a.hora_cheia BETWEEN :hora_inicio AND :hora_fim" in chamadas["consulta"]
    assert "EXISTS (" in chamadas["consulta"]
    assert chamadas["params"] == {
        "data_inicio": date(2026, 9, 1),
        "data_fim": date(2026, 9, 7),
        "hora_inicio": 2,
        "hora_fim": 16,
    }


def test_carregar_relatorio_sensores_rejeita_intervalos_invalidos():
    with pytest.raises(ValueError, match="data_inicio"):
        database.carregar_relatorio_sensores_periodo(
            date(2026, 9, 8),
            date(2026, 9, 7),
            2,
            16,
        )
    with pytest.raises(ValueError, match="faixa horária"):
        database.carregar_relatorio_sensores_periodo(
            date(2026, 9, 1),
            date(2026, 9, 7),
            16,
            2,
        )


def test_carregar_distribuicao_horaria_filtra_periodo_e_horas(monkeypatch):
    chamadas = {}

    class ReadEngine:
        @contextmanager
        def connect(self):
            yield object()

    def ler_sql(consulta, conexao, params=None):
        chamadas["consulta"] = str(consulta)
        chamadas["params"] = params
        return pd.DataFrame([{"hora": 2, "analises": 5}])

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    resultado = database.carregar_distribuicao_horaria_analise_sensores(
        date(2026, 9, 1),
        date(2026, 9, 7),
        2,
        16,
    )

    assert resultado.loc[0, "analises"] == 5
    assert "dia BETWEEN :data_inicio AND :data_fim" in chamadas["consulta"]
    assert "hora_cheia BETWEEN :hora_inicio AND :hora_fim" in chamadas["consulta"]
