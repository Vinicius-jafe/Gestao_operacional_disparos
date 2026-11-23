import pandas as pd
import pytest


@pytest.fixture
def eventos_reincidencia():
    return pd.DataFrame(
        [
            ("cliente-a", "Empresa A", "Smart Alarm", "SMART", 1, "2026-01-01"),
            ("cliente-a", "Empresa A", "Smart Alarm", "SMART", 2, "2026-01-01"),
            ("cliente-a", "Empresa A", "Smart Alarm", "SMART", 3, "2026-01-02"),
            ("cliente-a", "Empresa A", "Smart Alarm", "SMART", 4, "2026-01-02"),
            ("cliente-b", "Empresa B", "Convencional", "CONVENCIONAL", 5, "2026-01-01"),
            ("cliente-b", "Empresa B", "Convencional", "CONVENCIONAL", 6, "2026-01-02"),
            ("cliente-b", "Empresa B", "Convencional", "CONVENCIONAL", 7, "2026-01-02"),
            ("cliente-c", "Empresa C", "Convencional", "CONVENCIONAL", 8, "2026-01-03"),
        ],
        columns=[
            "chave_cliente",
            "razao_social",
            "empresa",
            "departamento",
            "id",
            "data_evento",
        ],
    ).assign(data_evento=lambda df: pd.to_datetime(df["data_evento"]))

