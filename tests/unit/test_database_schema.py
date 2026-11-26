from contextlib import contextmanager

import pytest

import src.database as database


SCHEMA_EXISTENTE = {
    "disparos_eventos": {
        "id",
        "contrato",
        "numero_contrato",
        "chave_cliente",
        "empresa",
        "razao_social",
        "departamento",
        "hora_evento",
        "dt_hora",
        "data_evento",
        "ano_mes",
        "hora_int",
        "minuto_do_dia",
        "final_de_semana",
    },
    "carteira_filiais": {"filial", "clientes", "tipo"},
    "arquivos_processados": {
        "nome_arquivo",
        "hash_sha256",
        "tamanho_bytes",
        "status",
        "linhas_lidas",
        "linhas_inseridas",
        "mensagem_erro",
        "data_processamento",
    },
    "analise": {
        "id",
        "id_providencia",
        "contrato",
        "numero_contrato",
        "empresa",
        "razao_social",
        "bairro",
        "cidade",
        "hora_evento",
        "departamento",
        "disparos",
        "dia",
        "hora",
        "hora_cheia",
        "dia_semana",
        "periodo",
        "mes",
        "estado",
        "possivel_padrao",
    },
    "alarm_report_snapshots": {
        "id",
        "period_start",
        "period_end",
        "collected_at",
        "page_size",
        "page_count",
        "total_item_count",
    },
    "disparos_sensor": {
        "id",
        "snapshot_id",
        "cod_contrato",
        "empresa",
        "razao_social",
        "num_contrato",
        "departamento",
        "department_id",
        "department_mapping_confidence",
        "disparos",
        "message_count",
        "zona_disparos",
        "data",
        "mes",
        "estado",
        "modelo_sensor",
    },
    "vw_analise_disp_sensor": {
        "id",
        "id_providencia",
        "contrato",
        "numero_contrato",
        "empresa",
        "razao_social",
        "departamento",
        "estado",
        "dia",
        "mes",
        "hora_cheia",
        "dia_semana",
        "periodo",
        "sensores_no_dia",
        "zona_referencia_dia",
        "total_disparos_sensor_dia",
    },
}


class FakeResult:
    def __init__(self, rows=(), scalar=None):
        self.rows = rows
        self.scalar_value = scalar

    def all(self):
        return self.rows

    def scalar(self):
        return self.scalar_value


class FakeConnection:
    def __init__(self, columns, indexes=None):
        self.columns = columns
        self.indexes = indexes if indexes is not None else {"idx_analise_dia_hora"}
        self.statements = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        assert "CREATE " not in sql.upper()
        assert "ALTER " not in sql.upper()
        assert "DROP " not in sql.upper()
        if "information_schema.columns" in sql:
            assert params == {"table_names": list(SCHEMA_EXISTENTE)}
            return FakeResult(
                [
                    (tabela, coluna)
                    for tabela, colunas in self.columns.items()
                    for coluna in colunas
                ]
            )
        if "FROM pg_indexes" in sql:
            assert params == {"index_names": ["idx_analise_dia_hora"]}
            return FakeResult([(index,) for index in sorted(self.indexes)])
        if sql.strip().upper() == "SELECT COUNT(*) FROM CARTEIRA_FILIAIS":
            return FakeResult(scalar=1)
        raise AssertionError(f"Consulta inesperada: {sql}")


class FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def begin(self):
        yield self.connection


def test_verificar_integridade_consulta_schema_sem_executar_ddl(monkeypatch):
    connection = FakeConnection(SCHEMA_EXISTENTE)
    monkeypatch.setattr(database, "engine", FakeEngine(connection))

    database.verificar_integridade_banco()

    assert len(connection.statements) == 3
    assert "information_schema.columns" in connection.statements[0]
    assert "FROM pg_indexes" in connection.statements[1]
    assert connection.statements[2].strip().upper() == (
        "SELECT COUNT(*) FROM CARTEIRA_FILIAIS"
    )


def test_verificar_integridade_falha_explicitamente_com_schema_incompleto(
    monkeypatch,
):
    schema_incompleto = {
        tabela: colunas - {"data_evento"} if tabela == "disparos_eventos" else colunas
        for tabela, colunas in SCHEMA_EXISTENTE.items()
    }
    connection = FakeConnection(schema_incompleto)
    monkeypatch.setattr(database, "engine", FakeEngine(connection))

    with pytest.raises(RuntimeError, match="data_evento"):
        database.verificar_integridade_banco()

    assert len(connection.statements) == 1


def test_verificar_integridade_exige_indice_de_data_e_hora(monkeypatch):
    connection = FakeConnection(SCHEMA_EXISTENTE, indexes=set())
    monkeypatch.setattr(database, "engine", FakeEngine(connection))

    with pytest.raises(RuntimeError, match="idx_analise_dia_hora"):
        database.verificar_integridade_banco()

    assert len(connection.statements) == 2
