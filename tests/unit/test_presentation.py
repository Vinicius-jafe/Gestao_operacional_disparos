import pandas as pd
import pytest

from src.presentation import incluir_cod_contrato, separar_chave_cliente


@pytest.mark.parametrize(
    ("chave", "codigo", "contrato"),
    [
        ("AB12_Contrato-XY", "AB12", "Contrato-XY"),
        ("12345_2026-07", "1234", "2026-07"),
        ("AB-12_Contrato_Extra", "AB12", "Contrato_Extra"),
        ("ABCsem separador", "ABCs", ""),
        ("", "", ""),
        (None, "", ""),
        (float("nan"), "", ""),
    ],
)
def test_separar_chave_cliente(chave, codigo, contrato):
    assert separar_chave_cliente(chave) == (codigo, contrato)


def test_incluir_cod_contrato_preserva_a_chave_de_origem():
    original = pd.DataFrame(
        {
            "CHAVE_CLIENTE": ["AB12_Contrato-XY", None],
            "DISPAROS": [3, 1],
        }
    )

    resultado = incluir_cod_contrato(original)

    assert resultado.columns.tolist() == ["DISPAROS", "COD", "CONTRATO"]
    assert resultado[["COD", "CONTRATO"]].values.tolist() == [
        ["AB12", "Contrato-XY"],
        ["", ""],
    ]
    assert original.columns.tolist() == ["CHAVE_CLIENTE", "DISPAROS"]
