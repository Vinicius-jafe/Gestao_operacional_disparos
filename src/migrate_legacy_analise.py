import argparse
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "BD DISPAROS" / "Database.db"
BATCH_SIZE = 1000
ANALISE_COLUMNS = (
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
)


def _parse_data_legada(
    value: Any,
    *,
    tabela: str = "analise",
    coluna: str = "dia",
) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        raise ValueError(f"A tabela {tabela} contém {coluna} vazio.")

    raw_value = str(value).strip()
    for date_format in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw_value, date_format).date()
        except ValueError:
            continue
    raise ValueError(
        f"A tabela {tabela} contém {coluna} em formato não reconhecido."
    )


def _normalizar_registro(row: sqlite3.Row) -> dict:
    registro = dict(row)
    try:
        registro["id"] = int(registro["id"])
        registro["dia"] = _parse_data_legada(registro["dia"])
        for column in ("id_providencia", "disparos", "hora_cheia"):
            if registro[column] is not None:
                registro[column] = int(registro[column])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "Registro inválido na tabela analise; migração cancelada."
        ) from error
    return registro


def migrar_analise_sqlite(
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
            row["name"] for row in source.execute('PRAGMA table_info("analise")')
        }
        missing_columns = set(ANALISE_COLUMNS).difference(columns)
        if missing_columns:
            raise RuntimeError(
                "A tabela SQLite analise não possui todas as colunas esperadas: "
                f"{sorted(missing_columns)}"
            )

        cursor = source.execute(
            f'SELECT {", ".join(ANALISE_COLUMNS)} FROM analise ORDER BY id'
        )
        total_lidos = 0
        insert_sql = text(f"""
            INSERT INTO analise ({", ".join(ANALISE_COLUMNS)})
            VALUES ({", ".join(f":{column}" for column in ANALISE_COLUMNS)})
            ON CONFLICT (id) DO NOTHING
        """)

        with target_engine.begin() as connection:
            tabela = connection.execute(
                text("SELECT to_regclass('analise')")
            ).scalar_one()
            if tabela is None:
                raise RuntimeError(
                    "A tabela PostgreSQL analise não existe. "
                    "Aplique primeiro o schema de init.sql."
                )

            while rows := cursor.fetchmany(batch_size):
                registros = [_normalizar_registro(row) for row in rows]
                connection.execute(insert_sql, registros)
                total_lidos += len(registros)

            connection.execute(text("""
                SELECT setval(
                    pg_get_serial_sequence('analise', 'id'),
                    COALESCE(MAX(id), 1),
                    COUNT(*) > 0
                )
                FROM analise
            """))

        logger.info("Migração concluída: %s registros de analise lidos.", total_lidos)
        return total_lidos
    finally:
        source.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copia os dados da tabela SQLite analise para PostgreSQL."
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
    migrar_analise_sqlite(args.sqlite_path)


if __name__ == "__main__":
    main()
