import calendar
from datetime import date, time

import pandas as pd

from src.metrics import filtrar_por_janela_horaria, filtrar_por_periodos_horarios


COLUNAS_IDENTIFICACAO = [
    "contrato",
    "numero_contrato",
    "chave_cliente",
    "razao_social",
    "empresa",
    "departamento",
]

COLUNAS_PREVISAO = [
    *COLUNAS_IDENTIFICACAO,
    "F_DISPAROS_MENOS_3_MESES",
    "G_DISPAROS_MENOS_2_MESES",
    "H_DISPAROS_MES_ANTERIOR",
    "I_DISPAROS_MES_ATUAL",
    "J_INDICADOR",
    "K_CLASSIFICACAO",
    "L_MEDIA_DIARIA_HISTORICA",
    "M_TAXA_DIARIA_ATUAL",
    "N_RAZAO_TENDENCIA",
    "O_ALERTA_REINCIDENCIA",
    "P_PREVISAO_REGRESSAO",
    "Q_PROJECAO_FECHAMENTO",
    "R_COMPARATIVO_ULTIMO_MES",
]


def _forecast_linear(values: list[int]) -> float:
    x_mean = 2.0
    y_mean = sum(values) / len(values)
    slope = sum(
        (x - x_mean) * (value - y_mean)
        for x, value in zip((1.0, 2.0, 3.0), values)
    ) / 2.0
    return max(0.0, y_mean + slope * (4.0 - x_mean))


def calcular_previsoes(
    df_eventos: pd.DataFrame,
    data_referencia: date | None = None,
    horario_abertura: time = time(0, 0),
    horario_fechamento: time = time(23, 59),
    periodos_selecionados: list[str] | tuple[str, ...] = (),
    modo_periodos: str = "qualquer",
) -> pd.DataFrame:
    if not isinstance(df_eventos, pd.DataFrame):
        raise TypeError("df_eventos deve ser um pandas.DataFrame")
    if df_eventos.empty:
        return pd.DataFrame(columns=COLUNAS_PREVISAO)

    colunas_obrigatorias = {*COLUNAS_IDENTIFICACAO, "data_evento"}
    faltantes = colunas_obrigatorias.difference(df_eventos.columns)
    if faltantes:
        raise KeyError(f"Colunas obrigatórias ausentes: {sorted(faltantes)}")
    if data_referencia is not None and not isinstance(data_referencia, date):
        raise TypeError("data_referencia deve ser uma datetime.date")

    referencia = data_referencia or date.today()
    primeiro_dia_mes_atual = date(referencia.year, referencia.month, 1)
    periodos = [
        (pd.Period(primeiro_dia_mes_atual, freq="M") - meses).strftime("%Y-%m")
        for meses in (3, 2, 1, 0)
    ]
    primeiro_dia_historico = pd.Period(periodos[0], freq="M").start_time.date()
    ultimo_dia_fechado = referencia - pd.Timedelta(days=1)

    base = df_eventos.copy()
    if "id" in base.columns:
        base = base.drop_duplicates(subset=["id"])
    base["data_evento"] = pd.to_datetime(base["data_evento"], errors="coerce").dt.date
    base = base.loc[
        base["data_evento"].between(primeiro_dia_historico, ultimo_dia_fechado)
    ].copy()
    if periodos_selecionados:
        base = filtrar_por_periodos_horarios(
            base,
            periodos_selecionados=periodos_selecionados,
            modo=modo_periodos,
        )
    else:
        base = filtrar_por_janela_horaria(
            base,
            horario_abertura=horario_abertura,
            horario_fechamento=horario_fechamento,
        )
    if base.empty:
        return pd.DataFrame(columns=COLUNAS_PREVISAO)

    base["_mes"] = pd.to_datetime(base["data_evento"]).dt.strftime("%Y-%m")
    contagens = (
        base.groupby(COLUNAS_IDENTIFICACAO + ["_mes"], dropna=False)
        .size()
        .unstack("_mes", fill_value=0)
        .reindex(columns=periodos, fill_value=0)
        .reset_index()
    )
    contagens.columns = [
        *COLUNAS_IDENTIFICACAO,
        "F_DISPAROS_MENOS_3_MESES",
        "G_DISPAROS_MENOS_2_MESES",
        "H_DISPAROS_MES_ANTERIOR",
        "I_DISPAROS_MES_ATUAL",
    ]

    dias_meses_anteriores = [
        calendar.monthrange(
            int(periodo[:4]),
            int(periodo[5:]),
        )[1]
        for periodo in periodos[:3]
    ]
    dias_mes_atual = calendar.monthrange(referencia.year, referencia.month)[1]
    dias_decorridos = max(1, referencia.day - 1)
    previsoes = []

    for linha in contagens.itertuples(index=False, name=None):
        identificacao = linha[: len(COLUNAS_IDENTIFICACAO)]
        f, g, h, i = (int(valor) for valor in linha[len(COLUNAS_IDENTIFICACAO) :])
        media_historica = sum(
            total / dias for total, dias in zip((f, g, h), dias_meses_anteriores)
        ) / 3.0
        taxa_atual = i / dias_decorridos
        previsoes.append(
            {
                **dict(zip(COLUNAS_IDENTIFICACAO, identificacao)),
                "F_DISPAROS_MENOS_3_MESES": f,
                "G_DISPAROS_MENOS_2_MESES": g,
                "H_DISPAROS_MES_ANTERIOR": h,
                "I_DISPAROS_MES_ATUAL": i,
                "J_INDICADOR": i,
                "K_CLASSIFICACAO": (
                    "Alta" if i >= 10 else "Média" if i >= 4 else "Baixa"
                ),
                "L_MEDIA_DIARIA_HISTORICA": media_historica,
                "M_TAXA_DIARIA_ATUAL": taxa_atual,
                "N_RAZAO_TENDENCIA": (
                    taxa_atual / media_historica if media_historica else 0.0
                ),
                "O_ALERTA_REINCIDENCIA": (
                    "SIM"
                    if i >= 3
                    and (media_historica == 0 or taxa_atual >= 2 * media_historica)
                    else "NÃO"
                ),
                "P_PREVISAO_REGRESSAO": _forecast_linear([f, g, h]),
                "Q_PROJECAO_FECHAMENTO": taxa_atual * dias_mes_atual,
                "R_COMPARATIVO_ULTIMO_MES": (
                    taxa_atual / (h / dias_meses_anteriores[2]) if h else 0.0
                ),
            }
        )

    return (
        pd.DataFrame(previsoes, columns=COLUNAS_PREVISAO)
        .sort_values("J_INDICADOR", ascending=False, kind="stable")
        .reset_index(drop=True)
    )
