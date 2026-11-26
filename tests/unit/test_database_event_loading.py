from contextlib import contextmanager
from datetime import date

import pandas as pd

import src.database as database


class ReadEngine:
    @contextmanager
    def connect(self):
        yield object()


def test_carregar_eventos_projeta_colunas_e_filtra_no_postgresql(monkeypatch):
    chamada = {}

    def ler_sql(consulta, conexao, params=None):
        chamada["consulta"] = str(consulta)
        chamada["params"] = params
        return pd.DataFrame(columns=database.COLUNAS_EVENTOS)

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    database.carregar_eventos(
        date(2026, 11, 1),
        date(2026, 11, 30),
        ["FILIAL ALFA"],
        ["Smart Alarm"],
    )

    consulta = chamada["consulta"]
    assert "SELECT *" not in consulta.upper()
    assert "WHERE data_evento >= :inicio" in consulta
    assert "data_evento <= :fim" in consulta
    assert "empresa IN (" in consulta
    assert "departamento IN (" in consulta
    assert chamada["params"] == {
        "empresas": ["FILIAL ALFA"],
        "departamentos": ["Smart Alarm"],
        "inicio": date(2026, 11, 1),
        "fim": date(2026, 11, 30),
    }


def test_carregar_eventos_aplica_minutos_no_banco(monkeypatch):
    chamada = {}

    def ler_sql(consulta, conexao, params=None):
        chamada["consulta"] = str(consulta)
        chamada["params"] = params
        return pd.DataFrame(columns=database.COLUNAS_EVENTOS)

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    database.carregar_eventos(
        date(2026, 11, 25),
        date(2026, 11, 25),
        ["FILIAL ALFA"],
        ["Smart Alarm"],
        minuto_inicio=480,
        minuto_fim=840,
    )

    assert "minuto_do_dia BETWEEN :minuto_inicio AND :minuto_fim" in chamada["consulta"]
    assert chamada["params"]["minuto_inicio"] == 480
    assert chamada["params"]["minuto_fim"] == 840


def test_carregar_eventos_aplica_ano_mes_no_banco(monkeypatch):
    chamada = {}

    def ler_sql(consulta, conexao, params=None):
        chamada["consulta"] = str(consulta)
        chamada["params"] = params
        return pd.DataFrame(columns=database.COLUNAS_EVENTOS)

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    database.carregar_eventos(
        None,
        None,
        ["FILIAL ALFA"],
        ["Smart Alarm"],
        ano_mes="2026-11",
    )

    assert "ano_mes = :ano_mes" in chamada["consulta"]
    assert chamada["params"]["ano_mes"] == "2026-11"


def test_carregar_eventos_nao_consulta_sem_filtros_de_empresa_ou_departamento(
    monkeypatch,
):
    class NoQueryEngine:
        def connect(self):
            raise AssertionError("A consulta deve ser ignorada sem filtros.")

    monkeypatch.setattr(database, "engine", NoQueryEngine())

    resultado = database.carregar_eventos(
        date(2026, 11, 1),
        date(2026, 11, 30),
        [],
        ["Smart Alarm"],
    )

    assert resultado.empty
    assert resultado.columns.tolist() == database.COLUNAS_EVENTOS


def test_carregar_comparacao_mensal_agrega_no_postgresql(monkeypatch):
    chamada = {}

    def ler_sql(consulta, conexao, params=None):
        chamada["consulta"] = str(consulta)
        chamada["params"] = params
        return pd.DataFrame(
            columns=[
                "empresa",
                "departamento",
                "numero_contrato",
                "contrato",
                "razao_social",
                "ano_mes",
                "total_disparos",
            ]
        )

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    resultado = database.carregar_comparacao_disparos_mensais(
        ["FILIAL ALFA"],
        ["Smart Alarm"],
    )

    assert resultado.empty
    assert "COUNT(id) AS total_disparos" in chamada["consulta"]
    assert "GROUP BY" in chamada["consulta"]
    assert "data_evento IS NOT NULL" in chamada["consulta"]
    assert chamada["params"] == {
        "empresas": ["FILIAL ALFA"],
        "departamentos": ["Smart Alarm"],
    }


def test_consultas_de_alertas_agregam_historico_no_postgresql(monkeypatch):
    consultas = []

    def ler_sql(consulta, conexao, params=None):
        consultas.append(str(consulta))
        return pd.DataFrame()

    monkeypatch.setattr(database, "engine", ReadEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    database.carregar_alertas_mau_uso()
    database.carregar_limitadores()

    assert "COUNT(*) FILTER" in consultas[0]
    assert "BETWEEN 6 AND 9" in consultas[0]
    assert "BETWEEN 18 AND 21" in consultas[0]
    assert "disparos_abertura_fechamento >= 4" in consultas[0]
    assert "GROUP BY" in consultas[1]
    assert "HAVING COUNT(*) >= 5" in consultas[1]
