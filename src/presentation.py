import pandas as pd


def separar_chave_cliente(chave: object) -> tuple[str, str]:
    if chave is None or pd.isna(chave):
        return "", ""

    valor = str(chave).strip()
    if not valor:
        return "", ""

    codigo_origem, separador, contrato = valor.partition("_")
    codigo = "".join(
        caractere for caractere in codigo_origem if caractere.isalnum()
    )[:4]
    return codigo, contrato.strip() if separador else ""


def incluir_cod_contrato(
    dataframe: pd.DataFrame,
    coluna_chave: str = "CHAVE_CLIENTE",
) -> pd.DataFrame:
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe deve ser um pandas.DataFrame")

    if coluna_chave not in dataframe.columns:
        raise KeyError(f"Coluna obrigatória ausente: {coluna_chave}")

    resultado = dataframe.copy()
    for coluna_derivada in ["COD", "CONTRATO"]:
        if coluna_derivada in resultado.columns:
            resultado = resultado.drop(columns=[coluna_derivada])

    partes = resultado[coluna_chave].map(separar_chave_cliente)
    resultado["COD"] = partes.map(lambda parte: parte[0])
    resultado["CONTRATO"] = partes.map(lambda parte: parte[1])
    return resultado.drop(columns=[coluna_chave])
