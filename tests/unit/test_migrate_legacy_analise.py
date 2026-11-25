from contextlib import contextmanager
from datetime import date
import sqlite3

import pytest

from src.migrate_legacy_analise import (
    ANALISE_COLUMNS,
    _parse_data_legada,
    migrar_analise_sqlite,
)


class FakeResult:
    def scalar_one(self):
        return "analise"


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


def create_legacy_database(path):
    source = sqlite3.connect(path)
    definitions = {
        "id": "INTEGER",
        "id_providencia": "INTEGER",
        "contrato": "TEXT",
        "numero_contrato": "TEXT",
        "empresa": "TEXT",
        "razao_social": "TEXT",
        "bairro": "TEXT",
        "cidade": "TEXT",
        "hora_evento": "TEXT",
        "departamento": "TEXT",
        "disparos": "INTEGER",
        "dia": "TEXT",
        "hora": "TEXT",
        "hora_cheia": "INTEGER",
        "dia_semana": "TEXT",
        "periodo": "TEXT",
        "mes": "TEXT",
        "estado": "TEXT",
        "possivel_padrao": "TEXT",
    }
    columns = ", ".join(f"{name} {definitions[name]}" for name in ANALISE_COLUMNS)
    source.execute(f"CREATE TABLE analise ({columns})")
    values = (
        1,
        2,
        "AB12",
        "12345",
        "FILIAL TESTE",
        "CLIENTE TESTE",
        "CENTRO",
        "BELO HORIZONTE",
        "01/11/2026 10:30:00",
        "Smart Alarm",
        3,
        "01/11/26",
        "10:30",
        10,
        "domingo",
        "Comercial",
        "11",
        "MG",
        None,
    )
    placeholders = ", ".join("?" for _ in ANALISE_COLUMNS)
    source.execute(
        f"INSERT INTO analise ({', '.join(ANALISE_COLUMNS)}) "
        f"VALUES ({placeholders})",
        values,
    )
    source.commit()
    source.close()


def test_parse_data_legada_aceita_ano_com_quatro_ou_dois_digitos():
    assert _parse_data_legada("01/11/2026") == date(2026, 11, 1)
    assert _parse_data_legada("01/11/26") == date(2026, 11, 1)
    assert _parse_data_legada("2026-11-01") == date(2026, 11, 1)
    with pytest.raises(ValueError, match="formato não reconhecido"):
        _parse_data_legada("31/13/2026")


def test_migrar_analise_lê_sqlite_e_grava_em_lotes_no_postgres(tmp_path):
    sqlite_path = tmp_path / "legacy.db"
    create_legacy_database(sqlite_path)
    connection = FakeConnection()
    engine = FakeEngine(connection)

    total_lidos = migrar_analise_sqlite(
        sqlite_path=sqlite_path,
        target_engine=engine,
        batch_size=1,
    )

    assert total_lidos == 1
    inserts = [
        params
        for statement, params in connection.executions
        if "INSERT INTO analise" in statement
    ]
    assert len(inserts) == 1
    assert inserts[0][0]["dia"] == date(2026, 11, 1)
    assert inserts[0][0]["id"] == 1
    assert any("setval" in statement for statement, _ in connection.executions)
