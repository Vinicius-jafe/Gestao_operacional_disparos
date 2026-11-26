import argparse
import logging
import sqlite3
from pathlib import Path

from sqlalchemy import text

from src.migrate_legacy_analise import DEFAULT_SQLITE_PATH, _parse_data_legada


logger = logging.getLogger(__name__)
BATCH_SIZE = 1000
SENSOR_COLUMNS = (
    "id",
    "cod_contrato",
    "empresa",
    "razao_social",
    "num_contrato",
    "departamento",
    "disparos",
    "zona_disparos",
    "data",
    "mes",
    "estado",
)


def _normalizar_sensor(row: sqlite3.Row) -> dict:
    sensor = dict(row)
    try:
        sensor["id"] = int(sensor["id"])
        for column in ("num_contrato", "disparos", "mes"):
            if sensor[column] is not None:
                sensor[column] = int(sensor[column])
        if sensor["data"] is not None:
            sensor["data"] = _parse_data_legada(
                sensor["data"],
                tabela="disparos_sensor",
                coluna="data",
            )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "Registro inválido na tabela disparos_sensor; migração cancelada."
        ) from error
    return sensor


def migrar_sensores_sqlite(
    sqlite_path: Path = DEFAULT_SQLITE_PATH,
    target_engine=None,
    batch_size: int = BATCH_SIZE,
) -> int:
    if batch_size <= 0:
        raise ValueError("batch_size deve ser maior que zero.")
    sqlite_path = Path(sqlite_path).resolve()
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"Banco SQLite não encontrado: {sqlite_path}")
    if target_engine is None:
        from src.database import engine

        target_engine = engine

    source_uri = f"{sqlite_path.as_uri()}?mode=ro"
    source = sqlite3.connect(source_uri, uri=True)
    source.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in source.execute('PRAGMA table_info("disparos_sensor")')
        }
        missing_columns = set(SENSOR_COLUMNS).difference(columns)
        if missing_columns:
            raise RuntimeError(
                "A tabela SQLite disparos_sensor não possui todas as colunas "
                f"esperadas: {sorted(missing_columns)}"
            )

        cursor = source.execute(
            f'SELECT {", ".join(SENSOR_COLUMNS)} '
            "FROM disparos_sensor ORDER BY id"
        )
        update_columns = [column for column in SENSOR_COLUMNS if column != "id"]
        insert_columns = ", ".join(SENSOR_COLUMNS)
        insert_values = ", ".join(f":{column}" for column in SENSOR_COLUMNS)
        update_assignments = ", ".join(
            f"{column} = EXCLUDED.{column}" for column in update_columns
        )
        insert_sql = text(f"""
            INSERT INTO disparos_sensor_legado ({insert_columns})
            VALUES ({insert_values})
            ON CONFLICT (id) DO UPDATE SET
                {update_assignments}
        """)
        total_lidos = 0

        with target_engine.begin() as connection:
            tabela = connection.execute(
                text("SELECT to_regclass('disparos_sensor_legado')")
            ).scalar_one()
            if tabela is None:
                raise RuntimeError(
                    "A tabela PostgreSQL disparos_sensor_legado não existe. "
                    "Aplique primeiro o schema atualizado de init.sql."
                )

            while rows := cursor.fetchmany(batch_size):
                registros = [_normalizar_sensor(row) for row in rows]
                connection.execute(insert_sql, registros)
                total_lidos += len(registros)

        logger.info(
            "Migração de sensores concluída: %s registros lidos.",
            total_lidos,
        )
        return total_lidos
    finally:
        source.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copia sensores históricos do SQLite para PostgreSQL."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help="Caminho do Database.db legado.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    migrar_sensores_sqlite(args.sqlite_path)


if __name__ == "__main__":
    main()
