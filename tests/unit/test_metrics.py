import pandas as pd
import pytest

from src.metrics import (
    calcular_metricas_filiais,
    preparar_serie_diaria,
    processar_reincidencia_clientes,
)


def test_calcular_metricas_filiais_projeta_mes_e_calcula_saldo():
    eventos = pd.DataFrame(
        {
            "empresa": ["FILIAL ALFA"] * 5,
            "id": [1, 2, 3, 4, 5],
        }
    )

    resultado = calcular_metricas_filiais(
        eventos,
        ["FILIAL ALFA"],
        {"FILIAL ALFA": 10},
        dias_decorridos=10,
        dias_totais_mes=30,
        modo_historico=False,
    ).iloc[0]

    assert resultado["DISPAROS"] == 5
    assert resultado["MEDIA"] == 0.5
    assert resultado["PREVISAO"] == 15
    assert resultado["TETO"] == 15
    assert resultado["SALDO"] == 0
    assert resultado["TAXA ATUAL"] == 0.5
    assert resultado["TAXA PREV"] == 1.5
    assert resultado["STATUS"] == "Dentro da Meta"


def test_calcular_metricas_filiais_modo_historico_nao_projeta_fechamento():
    eventos = pd.DataFrame(
        {
            "empresa": ["FILIAL ALFA"] * 3,
            "id": [1, 2, 3],
        }
    )

    resultado = calcular_metricas_filiais(
        eventos,
        ["FILIAL ALFA"],
        {"FILIAL ALFA": 10},
        dias_decorridos=4,
        dias_totais_mes=30,
        modo_historico=True,
    ).iloc[0]

    assert resultado["MEDIA"] == 0.8
    assert resultado["PREVISAO"] == 3
    assert resultado["TAXA ATUAL"] == 0.3
    assert resultado["TAXA PREV"] == 0.3
    assert resultado["SALDO"] == -12


@pytest.mark.parametrize(
    ("filial", "teto_esperado"),
    [
        ("REDES", 355),
        ("TOTENS", 1000),
        ("SMART P", 1100),
        ("DGP", 200),
        ("EPA", 200),
        ("BH", 200),
        ("ARAUJO", 689),
        ("FILIAL ALFA", 155),
    ],
)
def test_calcular_metricas_filiais_aplica_teto_da_categoria(
    filial, teto_esperado
):
    resultado = calcular_metricas_filiais(
        pd.DataFrame({"empresa": [filial], "id": [1]}),
        [filial],
        {filial: 100},
        dias_decorridos=1,
        dias_totais_mes=1,
        modo_historico=False,
    )

    assert resultado.iloc[0]["TETO"] == teto_esperado


def test_calcular_metricas_filiais_lida_com_periodo_e_carteira_vazios():
    resultado = calcular_metricas_filiais(
        pd.DataFrame(columns=["empresa", "id"]),
        ["FILIAL SEM BASE"],
        {},
        dias_decorridos=0,
        dias_totais_mes=30,
        modo_historico=False,
    ).iloc[0]

    assert resultado["DISPAROS"] == 0
    assert resultado["MEDIA"] == 0
    assert resultado["PREVISAO"] == 0
    assert resultado["TETO"] == 0
    assert resultado["TAXA ATUAL"] == 0
    assert resultado["TAXA PREV"] == 0


def test_processar_reincidencia_clientes_retorna_colunas_para_entrada_vazia():
    resultado = processar_reincidencia_clientes(pd.DataFrame())

    assert resultado.empty
    assert resultado.columns.tolist() == [
        "CHAVE_CLIENTE",
        "RAZAO_SOCIAL",
        "EMPRESA",
        "DEPARTAMENTO",
        "TOTAL_DISPAROS",
        "DIAS_DISTINTOS",
        "CRITICIDADE_PARETO",
    ]


def test_processar_reincidencia_clientes_agrega_e_classifica_pareto(
    eventos_reincidencia,
):
    resultado = processar_reincidencia_clientes(eventos_reincidencia)
    por_cliente = resultado.set_index("CHAVE_CLIENTE")

    assert por_cliente["TOTAL_DISPAROS"].to_dict() == {
        "cliente-a": 4,
        "cliente-b": 3,
        "cliente-c": 1,
    }
    assert por_cliente.loc["cliente-a", "DIAS_DISTINTOS"] == 2
    assert por_cliente.loc["cliente-a", "CRITICIDADE_PARETO"] == "🟥 Crítico"
    assert por_cliente.loc["cliente-b", "CRITICIDADE_PARETO"] == "Regular"
    assert por_cliente.loc["cliente-c", "CRITICIDADE_PARETO"] == "Regular"


def test_processar_reincidencia_clientes_retorna_apenas_metricas_de_disparos(
    eventos_reincidencia,
):
    resultado = processar_reincidencia_clientes(eventos_reincidencia)

    assert resultado.columns.tolist() == [
        "CHAVE_CLIENTE",
        "RAZAO_SOCIAL",
        "EMPRESA",
        "DEPARTAMENTO",
        "TOTAL_DISPAROS",
        "DIAS_DISTINTOS",
        "CRITICIDADE_PARETO",
    ]


def test_preparar_serie_diaria_preenche_dias_sem_disparos_com_zero():
    eventos = pd.DataFrame(
        [
            ("2026-01-01", "FILIAL ALFA", 2),
            ("2026-01-03", "FILIAL ALFA", 1),
            ("2026-01-02", "FILIAL BETA", 4),
        ],
        columns=["dia", "empresa", "disparos"],
    )

    resultado = preparar_serie_diaria(
        eventos,
        "empresa",
        ["FILIAL ALFA", "FILIAL BETA"],
        pd.Timestamp("2026-01-01").date(),
        pd.Timestamp("2026-01-03").date(),
    )

    por_filial = resultado.pivot(
        index="dia",
        columns="serie",
        values="disparos",
    )
    assert por_filial.to_dict() == {
        "FILIAL ALFA": {
            pd.Timestamp("2026-01-01"): 2,
            pd.Timestamp("2026-01-02"): 0,
            pd.Timestamp("2026-01-03"): 1,
        },
        "FILIAL BETA": {
            pd.Timestamp("2026-01-01"): 0,
            pd.Timestamp("2026-01-02"): 4,
            pd.Timestamp("2026-01-03"): 0,
        },
    }
