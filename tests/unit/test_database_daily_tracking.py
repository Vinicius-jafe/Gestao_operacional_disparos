from contextlib import contextmanager
from datetime import date

import pandas as pd

import src.database as database


class FakeEngine:
    @contextmanager
    def connect(self):
        yield object()


def test_carregar_acompanhamento_diario_agrega_no_postgresql(monkeypatch):
    chamadas = {}
    dados = pd.DataFrame(
        [
            {
                "dia": pd.Timestamp("2026-01-02"),
                "empresa": "FILIAL ALFA",
                "chave_cliente": "cliente-1",
                "razao_social": "Cliente 1",
                "disparos": 3,
            }
        ]
    )

    def ler_sql(consulta, conexao, params):
        chamadas["consulta"] = str(consulta)
        chamadas["params"] = params
        return dados

    monkeypatch.setattr(database, "engine", FakeEngine())
    monkeypatch.setattr(database.pd, "read_sql", ler_sql)

    resultado = database.carregar_acompanhamento_diario(
        date(2026, 1, 1),
        date(2026, 1, 31),
        ["FILIAL ALFA"],
        ["SMART"],
    )

    assert "GROUP BY data_evento, empresa, chave_cliente" in chamadas["consulta"]
    assert "COUNT(id) AS disparos" in chamadas["consulta"]
    assert chamadas["params"] == {
        "inicio": date(2026, 1, 1),
        "fim": date(2026, 1, 31),
        "empresas": ["FILIAL ALFA"],
        "departamentos": ["SMART"],
    }
    assert resultado.loc[0, "dia"] == date(2026, 1, 2)
    assert resultado.loc[0, "disparos"] == 3


def test_carregar_acompanhamento_diario_nao_consulta_sem_filtros(monkeypatch):
    class EngineNaoUtilizado:
        def connect(self):
            raise AssertionError("Não deveria consultar o banco sem filtros.")

    monkeypatch.setattr(database, "engine", EngineNaoUtilizado())

    resultado = database.carregar_acompanhamento_diario(
        date(2026, 1, 1),
        date(2026, 1, 31),
        [],
        ["SMART"],
    )

    assert resultado.empty
    assert resultado.columns.tolist() == database.COLUNAS_ACOMPANHAMENTO_DIARIO
