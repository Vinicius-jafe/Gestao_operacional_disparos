from contextlib import contextmanager
from datetime import date
import sqlite3

import pytest

from src.migrate_legacy_sensors import migrar_sensores_sqlite


class FakeResult:
    def scalar_one(self):
        return "disparos_sensor_legado"


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
    with sqlite3.connect(path) as source:
        source.execute("""
            CREATE TABLE disparos_sensor (
                id INTEGER PRIMARY KEY,
                cod_contrato TEXT,
                empresa TEXT,
                razao_social TEXT,
                num_contrato INTEGER,
                departamento TEXT,
                disparos INTEGER,
                zona_disparos TEXT,
                data TEXT,
                mes INTEGER,
                estado TEXT
            )
        """)
        source.executemany(
            """
            INSERT INTO disparos_sensor (
                id, cod_contrato, empresa, razao_social, num_contrato,
                departamento, disparos, zona_disparos, data, mes, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    7,
                    "AB12",
                    "FILIAL TESTE",
                    "CLIENTE TESTE",
                    12345,
                    "Smart Alarm",
                    3,
                    "Sensor Entrada",
                    "01/09/26",
                    9,
                    "MG",
                ),
                (
                    8,
                    "CD34",
                    "FILIAL TESTE",
                    "CLIENTE DOIS",
                    67890,
                    "Smart Alarm",
                    5,
                    "Sensor Janela",
                    "2026-10-31",
                    10,
                    "RJ",
                ),
            ],
        )


def test_migrar_sensores_preserva_zonas_e_normaliza_datas_em_lotes(tmp_path):
    sqlite_path = tmp_path / "legacy.db"
    create_legacy_database(sqlite_path)
    connection = FakeConnection()

    total_lidos = migrar_sensores_sqlite(
        sqlite_path=sqlite_path,
        target_engine=FakeEngine(connection),
        batch_size=1,
    )

    assert total_lidos == 2
    inserts = [
        params
        for statement, params in connection.executions
        if "INSERT INTO disparos_sensor_legado" in statement
    ]
    assert len(inserts) == 2
    assert inserts[0][0]["id"] == 7
    assert inserts[0][0]["data"] == date(2026, 9, 1)
    assert inserts[0][0]["zona_disparos"] == "Sensor Entrada"
    assert inserts[1][0]["data"] == date(2026, 10, 31)
    assert "ON CONFLICT (id) DO UPDATE" in connection.executions[1][0]


def test_migrar_sensores_falha_se_a_tabela_origem_nao_existir(tmp_path):
    sqlite_path = tmp_path / "empty.db"
    sqlite3.connect(sqlite_path).close()

    with pytest.raises(RuntimeError, match="disparos_sensor"):
        migrar_sensores_sqlite(
            sqlite_path=sqlite_path,
            target_engine=FakeEngine(FakeConnection()),
        )


def test_migrar_sensores_cancela_registro_com_data_invalida(tmp_path):
    sqlite_path = tmp_path / "legacy.db"
    create_legacy_database(sqlite_path)
    with sqlite3.connect(sqlite_path) as source:
        source.execute("UPDATE disparos_sensor SET data = '31/13/2026' WHERE id = 7")
    connection = FakeConnection()

    with pytest.raises(ValueError, match="Registro inválido"):
        migrar_sensores_sqlite(
            sqlite_path=sqlite_path,
            target_engine=FakeEngine(connection),
        )
