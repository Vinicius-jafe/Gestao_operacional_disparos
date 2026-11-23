from typing import Callable

import pandas as pd

from src.config import FILIAIS_SP


COLUNAS_DISTRIBUICAO_HORARIA = ["HORA", "FAIXA_HORARIA", "DISPAROS"]
COLUNAS_DISTRIBUICAO_PERIODOS = ["PERIODO", "DISPAROS"]
COLUNAS_MAU_USO = [
    "NUMERO_CONTRATO",
    "DISPAROS_ABERTURA_FECHAMENTO",
    "DISPAROS_OUTROS_PERIODOS",
]
COLUNAS_LIMITADOR = ["NUMERO_CONTRATO", "DATA_EVENTO", "HORA", "OCORRENCIAS"]
COLUNAS_RECORRENCIA_COMPLEMENTAR = [
    "CHAVE_CLIENTE",
    "RAZAO_SOCIAL",
    "EMPRESA",
    "DEPARTAMENTO",
    "TOTAL_DISPAROS",
    "DIAS_DISTINTOS",
    "MESES_ATIVOS",
    "MEDIA_DISPAROS_MES",
    "MAX_DISPAROS_MES",
]
COLUNAS_COMPARACAO_MENSAL = [
    "empresa",
    "departamento",
    "numero_contrato",
    "contrato",
    "razao_social",
    "ano_mes",
    "total_disparos",
]
COLUNAS_TAXA_CARTEIRA = [
    "FILIAL",
    "CLIENTES",
    "DISPAROS",
    "TAXA",
    "SEM_CARTEIRA",
]

PERIODOS_HORARIOS = (
    "Madrugada",
    "Abertura",
    "Comercial",
    "Fechamento",
    "Noite",
)


def _deduplicar_eventos(df: pd.DataFrame) -> pd.DataFrame:
    if "id" in df.columns:
        return df.drop_duplicates(subset=["id"]).copy()
    return df.copy()


def _contrato_valido(serie: pd.Series) -> pd.Series:
    return serie.notna() & serie.astype("string").str.strip().ne("").fillna(False)


def classificar_faixa_horaria(hora_int: object) -> str | None:
    if hora_int is None or pd.isna(hora_int):
        return None

    hora = int(hora_int)
    if hora < 0 or hora > 23:
        raise ValueError("hora_int deve estar entre 0 e 23")
    if hora < 6:
        return "Madrugada"
    if hora < 10:
        return "Abertura"
    if hora < 18:
        return "Comercial"
    if hora < 22:
        return "Fechamento"
    return "Noite"


def calcular_distribuicao_horaria(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame):
        raise TypeError("df deve ser um pandas.DataFrame")
    if "dt_hora" not in df.columns:
        raise KeyError("Coluna obrigatória ausente: dt_hora")

    base = _deduplicar_eventos(df)
    dt_hora = pd.to_datetime(base["dt_hora"], errors="coerce")
    horas = dt_hora.dt.hour
    contagem = horas.dropna().astype(int).value_counts()
    return pd.DataFrame(
        [
            {
                "HORA": hora,
                "FAIXA_HORARIA": classificar_faixa_horaria(hora),
                "DISPAROS": int(contagem.get(hora, 0)),
            }
            for hora in range(24)
        ],
        columns=COLUNAS_DISTRIBUICAO_HORARIA,
    )


def calcular_distribuicao_periodos(df: pd.DataFrame) -> pd.DataFrame:
    distribuicao_horaria = calcular_distribuicao_horaria(df)
    contagem_por_periodo = distribuicao_horaria.groupby("FAIXA_HORARIA")[
        "DISPAROS"
    ].sum()
    return pd.DataFrame(
        [
            {
                "PERIODO": periodo,
                "DISPAROS": int(contagem_por_periodo.get(periodo, 0)),
            }
            for periodo in PERIODOS_HORARIOS
        ],
        columns=COLUNAS_DISTRIBUICAO_PERIODOS,
    )


def detectar_possivel_mau_uso(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame):
        raise TypeError("df deve ser um pandas.DataFrame")
    if "numero_contrato" not in df.columns or "dt_hora" not in df.columns:
        raise KeyError("Colunas obrigatórias ausentes: numero_contrato, dt_hora")
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_MAU_USO)

    base = _deduplicar_eventos(df)
    base = base.loc[_contrato_valido(base["numero_contrato"])].copy()
    base["hora"] = pd.to_datetime(base["dt_hora"], errors="coerce").dt.hour
    abertura_fechamento = base["hora"].between(6, 9) | base["hora"].between(18, 21)
    base["abertura_fechamento"] = abertura_fechamento.fillna(False)
    base["outros_periodos"] = ~abertura_fechamento.fillna(False)

    resultado = (
        base.groupby("numero_contrato", as_index=False, dropna=False)
        .agg(
            DISPAROS_ABERTURA_FECHAMENTO=("abertura_fechamento", "sum"),
            DISPAROS_OUTROS_PERIODOS=("outros_periodos", "sum"),
        )
        .rename(columns={"numero_contrato": "NUMERO_CONTRATO"})
    )
    resultado = resultado.loc[
        (resultado["DISPAROS_ABERTURA_FECHAMENTO"] >= 4)
        & (resultado["DISPAROS_OUTROS_PERIODOS"] == 0)
    ].sort_values("DISPAROS_ABERTURA_FECHAMENTO", ascending=False)
    return resultado.loc[:, COLUNAS_MAU_USO].reset_index(drop=True)


def detectar_limitador(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame):
        raise TypeError("df deve ser um pandas.DataFrame")
    colunas_obrigatorias = {"numero_contrato", "data_evento", "dt_hora"}
    faltantes = colunas_obrigatorias.difference(df.columns)
    if faltantes:
        raise KeyError(f"Colunas obrigatórias ausentes: {sorted(faltantes)}")
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_LIMITADOR)

    base = _deduplicar_eventos(df)
    base = base.loc[_contrato_valido(base["numero_contrato"])].copy()
    base["DATA_EVENTO"] = pd.to_datetime(
        base["data_evento"], errors="coerce"
    ).dt.date
    base["HORA"] = pd.to_datetime(base["dt_hora"], errors="coerce").dt.hour
    base = base.dropna(subset=["DATA_EVENTO", "HORA"])

    resultado = (
        base.groupby(
            ["numero_contrato", "DATA_EVENTO", "HORA"],
            as_index=False,
            dropna=False,
        )
        .size()
        .rename(
            columns={
                "numero_contrato": "NUMERO_CONTRATO",
                "size": "OCORRENCIAS",
            }
        )
    )
    resultado = resultado.loc[resultado["OCORRENCIAS"] >= 5]
    return resultado.loc[:, COLUNAS_LIMITADOR].reset_index(drop=True)


def calcular_recorrencia_complementar(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame):
        raise TypeError("df deve ser um pandas.DataFrame")
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_RECORRENCIA_COMPLEMENTAR)

    colunas_obrigatorias = {
        "chave_cliente",
        "razao_social",
        "empresa",
        "departamento",
        "data_evento",
    }
    faltantes = colunas_obrigatorias.difference(df.columns)
    if faltantes:
        raise KeyError(f"Colunas obrigatórias ausentes: {sorted(faltantes)}")

    base = _deduplicar_eventos(df)
    chave = base["chave_cliente"].astype("string").str.strip()
    base = base.loc[chave.notna() & chave.ne("")].copy()
    if base.empty:
        return pd.DataFrame(columns=COLUNAS_RECORRENCIA_COMPLEMENTAR)

    base["data_evento"] = pd.to_datetime(
        base["data_evento"], errors="coerce"
    ).dt.date
    base["mes"] = pd.to_datetime(base["data_evento"], errors="coerce").dt.strftime(
        "%Y-%m"
    )
    totais = base.groupby("chave_cliente", as_index=False, dropna=False).agg(
        RAZAO_SOCIAL=("razao_social", "first"),
        EMPRESA=("empresa", "first"),
        DEPARTAMENTO=("departamento", "first"),
        TOTAL_DISPAROS=("chave_cliente", "size"),
        DIAS_DISTINTOS=("data_evento", "nunique"),
    )
    mensais = (
        base.dropna(subset=["mes"])
        .groupby(["chave_cliente", "mes"], as_index=False)
        .size()
        .rename(columns={"size": "disparos_mes"})
    )
    resumo_mensal = mensais.groupby("chave_cliente", as_index=False).agg(
        MESES_ATIVOS=("mes", "nunique"),
        MEDIA_DISPAROS_MES=("disparos_mes", "mean"),
        MAX_DISPAROS_MES=("disparos_mes", "max"),
    )
    resultado = totais.merge(resumo_mensal, on="chave_cliente", how="left")
    resultado["MESES_ATIVOS"] = resultado["MESES_ATIVOS"].fillna(0).astype(int)
    resultado["MEDIA_DISPAROS_MES"] = resultado["MEDIA_DISPAROS_MES"].fillna(0.0)
    resultado["MAX_DISPAROS_MES"] = resultado["MAX_DISPAROS_MES"].fillna(0).astype(int)
    resultado = resultado.rename(columns={"chave_cliente": "CHAVE_CLIENTE"})
    return (
        resultado.loc[:, COLUNAS_RECORRENCIA_COMPLEMENTAR]
        .sort_values("TOTAL_DISPAROS", ascending=False)
        .reset_index(drop=True)
    )


def comparar_disparos_mensais(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame):
        raise TypeError("df deve ser um pandas.DataFrame")
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_COMPARACAO_MENSAL)

    colunas_dimensao = [
        "empresa",
        "departamento",
        "numero_contrato",
        "contrato",
        "razao_social",
    ]
    faltantes = set(colunas_dimensao).difference(df.columns)
    if faltantes:
        raise KeyError(f"Colunas obrigatórias ausentes: {sorted(faltantes)}")
    if "data_evento" not in df.columns and "ano_mes" not in df.columns:
        raise KeyError("É necessário fornecer data_evento ou ano_mes")

    base = _deduplicar_eventos(df)
    if "data_evento" in base.columns:
        mes_por_data = pd.to_datetime(
            base["data_evento"], errors="coerce"
        ).dt.strftime("%Y-%m")
        if "ano_mes" in base.columns:
            mes_informado = base["ano_mes"].astype("string")
            mes_informado = mes_informado.where(
                mes_informado.str.fullmatch(r"\d{4}-\d{2}", na=False)
            )
            base["ano_mes"] = mes_por_data.fillna(mes_informado)
        else:
            base["ano_mes"] = mes_por_data
    else:
        base["ano_mes"] = base["ano_mes"].astype("string")
    base = base.dropna(subset=["ano_mes"])
    if base.empty:
        return pd.DataFrame(columns=COLUNAS_COMPARACAO_MENSAL)

    resultado = (
        base.groupby(
            colunas_dimensao + ["ano_mes"],
            as_index=False,
            dropna=False,
        )
        .size()
        .rename(columns={"size": "total_disparos"})
    )
    return resultado.loc[:, COLUNAS_COMPARACAO_MENSAL].sort_values(
        ["ano_mes", "empresa", "departamento", "numero_contrato"],
        na_position="last",
    ).reset_index(drop=True)


def calcular_taxa_por_carteira(
    df_eventos: pd.DataFrame,
    df_carteira: pd.DataFrame,
    normalizador: Callable[[str], str],
) -> pd.DataFrame:
    if not callable(normalizador):
        raise TypeError("normalizador deve ser uma função")
    if not isinstance(df_eventos, pd.DataFrame):
        raise TypeError("df_eventos deve ser um pandas.DataFrame")
    if not isinstance(df_carteira, pd.DataFrame):
        raise TypeError("df_carteira deve ser um pandas.DataFrame")
    if not {"empresa", "id"}.issubset(df_eventos.columns):
        raise KeyError("df_eventos deve conter empresa e id")
    if not {"filial", "clientes"}.issubset(df_carteira.columns):
        raise KeyError("df_carteira deve conter filial e clientes")

    carteiras = df_carteira.copy()
    if "tipo" in carteiras.columns:
        carteiras = carteiras.loc[
            carteiras["tipo"].astype("string").str.upper().isin(["FILIAL", "SMART"])
        ].copy()

    def chave_filial(valor: object) -> str:
        if pd.isna(valor) or not str(valor).strip():
            return ""
        normalizada = normalizador(str(valor).strip())
        return "SP" if normalizada in FILIAIS_SP else normalizada

    carteiras["FILIAL"] = carteiras["filial"].map(chave_filial)
    carteiras["CLIENTES"] = pd.to_numeric(carteiras["clientes"], errors="coerce").fillna(0)
    carteiras = carteiras.groupby("FILIAL", as_index=False).agg(
        CLIENTES=("CLIENTES", "sum")
    )

    eventos = _deduplicar_eventos(df_eventos)
    eventos["FILIAL"] = eventos["empresa"].map(chave_filial)
    eventos_por_filial = eventos.groupby("FILIAL", as_index=False).size().rename(
        columns={"size": "DISPAROS"}
    )

    resultado = carteiras.merge(eventos_por_filial, on="FILIAL", how="outer")
    resultado["CLIENTES"] = resultado["CLIENTES"].fillna(0)
    resultado["DISPAROS"] = resultado["DISPAROS"].fillna(0).astype(int)
    resultado["SEM_CARTEIRA"] = resultado["CLIENTES"].isna()
    resultado["TAXA"] = (
        resultado["DISPAROS"].astype(float)
        .div(resultado["CLIENTES"].replace(0, pd.NA))
        .fillna(0.0)
    )
    resultado["SEM_CARTEIRA"] = ~resultado["FILIAL"].isin(carteiras["FILIAL"])
    return (
        resultado.loc[:, COLUNAS_TAXA_CARTEIRA]
        .sort_values(["TAXA", "FILIAL"], ascending=[False, True])
        .reset_index(drop=True)
    )


def calcular_metricas_filiais(
    df_filtrado: pd.DataFrame,
    filiais_selecionadas: list,
    dict_carteiras: dict,
    dias_decorridos: int,
    dias_totais_mes: int,
    modo_historico: bool,
) -> pd.DataFrame:
    if df_filtrado is None or not isinstance(df_filtrado, pd.DataFrame):
        df_filtrado = pd.DataFrame(columns=["empresa", "id"])

    linhas = []
    contagem = (
        df_filtrado.groupby("empresa", dropna=False)["id"].count().to_dict()
        if "empresa" in df_filtrado.columns and "id" in df_filtrado.columns
        else {}
    )

    filiais = filiais_selecionadas or []
    carteira = dict_carteiras or {}
    dias_decorridos = int(dias_decorridos) if isinstance(dias_decorridos, (int, float)) else 0
    dias_totais_mes = int(dias_totais_mes) if isinstance(dias_totais_mes, (int, float)) else 0

    for filial in filiais:
        clientes = int(carteira.get(filial, 0) or 0)
        disparos = contagem.get(filial, 0)

        if "REDES" in str(filial).upper():
            fator_teto = 3.54999
        elif "TOTEN" in str(filial).upper():
            fator_teto = 10.0
        elif "SMART P" in str(filial).upper():
            fator_teto = 11.0
        elif "DGP" in str(filial).upper() or "EPA" in str(filial).upper() or "BH" in str(filial).upper():
            fator_teto = 2.0
        elif "ARAUJO" in str(filial).upper():
            fator_teto = 6.89
        else:
            fator_teto = 1.5499

        if modo_historico:
            media_dia = disparos / dias_decorridos if dias_decorridos > 0 else 0.0
            prev_fechamento = disparos
            taxa_atual = round(disparos / clientes, 2) if clientes > 0 else 0.0
            taxa_prev = taxa_atual
        else:
            media_dia = disparos / dias_decorridos if dias_decorridos > 0 else 0.0
            prev_fechamento = int(round(media_dia * dias_totais_mes)) if dias_totais_mes > 0 else 0
            taxa_atual = round(disparos / clientes, 2) if clientes > 0 else 0.0
            taxa_prev = (
                round((disparos / clientes) / dias_decorridos * dias_totais_mes, 2)
                if (clientes > 0 and dias_decorridos > 0)
                else 0.0
            )

        teto = int(round(clientes * fator_teto))
        saldo = prev_fechamento - teto

        linhas.append(
            {
                "FILIAIS": filial,
                "CLIENTES": clientes,
                "DISPAROS": disparos,
                "MEDIA": round(media_dia, 1),
                "PREVISAO": prev_fechamento,
                "TETO": teto,
                "SALDO": saldo,
                "TAXA ATUAL": taxa_atual,
                "TAXA PREV": taxa_prev,
                "STATUS": "Dentro da Meta"
                if taxa_prev <= round(fator_teto, 1)
                else "Fora da Meta",
            }
        )

    df_res = pd.DataFrame(linhas)
    if not df_res.empty:
        df_res = df_res.sort_values(by="TAXA PREV", ascending=False)
    return df_res


def processar_reincidencia_clientes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa os disparos pela chave do cliente e calcula sua classificação Pareto.
    """
    colunas_esperadas = [
        "CHAVE_CLIENTE",
        "RAZAO_SOCIAL",
        "EMPRESA",
        "DEPARTAMENTO",
        "TOTAL_DISPAROS",
        "DIAS_DISTINTOS",
        "CRITICIDADE_PARETO",
    ]

    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame(columns=colunas_esperadas)

    if df.empty:
        return pd.DataFrame(columns=colunas_esperadas)

    if "chave_cliente" not in df.columns:
        return pd.DataFrame(columns=colunas_esperadas)

    dados = df.copy()
    dados = dados[dados["chave_cliente"].notna()].copy()
    if dados.empty:
        return pd.DataFrame(columns=colunas_esperadas)

    grp = dados.groupby("chave_cliente", as_index=False, dropna=False).agg(
        RAZAO_SOCIAL=("razao_social", "first"),
        EMPRESA=("empresa", "first"),
        DEPARTAMENTO=("departamento", "first"),
        TOTAL_DISPAROS=("id", "count"),
        DIAS_DISTINTOS=("data_evento", "nunique"),
    )

    grp = grp.sort_values(by="TOTAL_DISPAROS", ascending=False).reset_index(drop=True)

    total_acumulado = grp["TOTAL_DISPAROS"].sum()
    if total_acumulado > 0:
        grp["soma_acumulada"] = grp["TOTAL_DISPAROS"].cumsum()
        grp["pct_acumulado"] = grp["soma_acumulada"] / total_acumulado
        grp["CRITICIDADE_PARETO"] = grp["pct_acumulado"].apply(
            lambda x: "🟥 Crítico" if x <= 0.80 else "Regular"
        )
        grp = grp.drop(columns=["soma_acumulada", "pct_acumulado"])
    else:
        grp["CRITICIDADE_PARETO"] = "Regular"

    grp = grp.rename(columns={"chave_cliente": "CHAVE_CLIENTE"})
    return grp
