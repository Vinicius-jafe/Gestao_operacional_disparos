from datetime import date, time

import pandas as pd
import pytest

from src.prediction import COLUNAS_PREVISAO, calcular_previsoes


def _eventos_por_mes(contagens):
    linhas = []
    identificacao = {
        "contrato": "contrato-1",
        "numero_contrato": "numero-1",
        "chave_cliente": "cliente-1",
        "razao_social": "Cliente",
        "empresa": "Empresa",
        "departamento": "SMART",
    }
    for mes, total in contagens.items():
        for numero in range(total):
            linhas.append(
                {
                    **identificacao,
                    "id": f"{mes}-{numero}",
                    "data_evento": f"{mes}-01",
                }
            )
    return pd.DataFrame(linhas)


def _eventos_com_data_hora(eventos):
    linhas = []
    identificacao = {
        "contrato": "contrato-1",
        "numero_contrato": "numero-1",
        "chave_cliente": "cliente-1",
        "razao_social": "Cliente",
        "empresa": "Empresa",
        "departamento": "SMART",
    }
    for numero, (data, horario) in enumerate(eventos):
        linhas.append(
            {
                **identificacao,
                "id": numero,
                "data_evento": data,
                "dt_hora": pd.Timestamp(f"{data} {horario}"),
            }
        )
    return pd.DataFrame(linhas)


def test_calcular_previsoes_aplica_formulas_e_dias_reais():
    eventos = _eventos_por_mes(
        {"2026-08": 31, "2026-09": 30, "2026-10": 31, "2026-11": 6}
    )

    previsao = calcular_previsoes(eventos, date(2026, 11, 15)).iloc[0]

    assert previsao["F_DISPAROS_MENOS_3_MESES"] == 31
    assert previsao["G_DISPAROS_MENOS_2_MESES"] == 30
    assert previsao["H_DISPAROS_MES_ANTERIOR"] == 31
    assert previsao["I_DISPAROS_MES_ATUAL"] == 6
    assert previsao["J_INDICADOR"] == 6
    assert previsao["K_CLASSIFICACAO"] == "Média"
    assert previsao["L_MEDIA_DIARIA_HISTORICA"] == pytest.approx(1.0)
    assert previsao["M_TAXA_DIARIA_ATUAL"] == pytest.approx(6 / 14)
    assert previsao["N_RAZAO_TENDENCIA"] == pytest.approx(6 / 14)
    assert previsao["O_ALERTA_REINCIDENCIA"] == "NÃO"
    assert previsao["P_PREVISAO_REGRESSAO"] == pytest.approx(92 / 3)
    assert previsao["Q_PROJECAO_FECHAMENTO"] == pytest.approx(6 / 14 * 30)
    assert previsao["R_COMPARATIVO_ULTIMO_MES"] == pytest.approx((6 / 14) / 1.0)


def test_calcular_previsoes_filtra_faixa_comercial_antes_das_agregacoes():
    eventos_por_mes = {
        "2026-08": ["07:59", "08:00", "12:30", "18:00:59", "18:01"],
        "2026-09": ["08:00", "17:59", "18:01"],
        "2026-10": ["07:59", "08:00", "10:00", "18:00"],
        "2026-11": ["08:00", "12:00", "18:00:59", "18:01", "07:59"],
    }
    eventos = _eventos_com_data_hora(
        [
            (f"{mes}-01", horario)
            for mes, horarios in eventos_por_mes.items()
            for horario in horarios
        ]
    )

    previsao = calcular_previsoes(
        eventos,
        date(2026, 11, 15),
        horario_abertura=time(8, 0),
        horario_fechamento=time(18, 0),
    ).iloc[0]

    assert previsao["F_DISPAROS_MENOS_3_MESES"] == 3
    assert previsao["G_DISPAROS_MENOS_2_MESES"] == 2
    assert previsao["H_DISPAROS_MES_ANTERIOR"] == 3
    assert previsao["I_DISPAROS_MES_ATUAL"] == 3
    assert previsao["J_INDICADOR"] == 3
    assert previsao["M_TAXA_DIARIA_ATUAL"] == pytest.approx(3 / 14)


def test_calcular_previsoes_filtra_turno_noturno_com_virada_de_dia():
    eventos = _eventos_com_data_hora(
        [
            ("2026-11-01", "21:59"),
            ("2026-11-01", "22:00"),
            ("2026-11-01", "23:59"),
            ("2026-11-02", "00:00"),
            ("2026-11-02", "05:59"),
            ("2026-11-02", "06:00"),
            ("2026-11-02", "12:00"),
        ]
    )

    previsao = calcular_previsoes(
        eventos,
        date(2026, 11, 10),
        horario_abertura=time(22, 0),
        horario_fechamento=time(6, 0),
    ).iloc[0]

    assert previsao["I_DISPAROS_MES_ATUAL"] == 5
    assert previsao["J_INDICADOR"] == 5


def test_calcular_previsoes_exige_cliente_em_todos_periodos_selecionados():
    eventos = pd.DataFrame(
        [
            {
                "contrato": "contrato-a",
                "numero_contrato": "numero-a",
                "chave_cliente": "cliente-a",
                "razao_social": "Cliente A",
                "empresa": "Empresa",
                "departamento": "SMART",
                "id": 1,
                "data_evento": "2026-08-01",
                "dt_hora": "2026-08-01 07:00",
            },
            {
                "contrato": "contrato-a",
                "numero_contrato": "numero-a",
                "chave_cliente": "cliente-a",
                "razao_social": "Cliente A",
                "empresa": "Empresa",
                "departamento": "SMART",
                "id": 2,
                "data_evento": "2026-08-01",
                "dt_hora": "2026-08-01 18:00",
            },
            {
                "contrato": "contrato-a",
                "numero_contrato": "numero-a",
                "chave_cliente": "cliente-a",
                "razao_social": "Cliente A",
                "empresa": "Empresa",
                "departamento": "SMART",
                "id": 3,
                "data_evento": "2026-11-01",
                "dt_hora": "2026-11-01 07:00",
            },
            {
                "contrato": "contrato-a",
                "numero_contrato": "numero-a",
                "chave_cliente": "cliente-a",
                "razao_social": "Cliente A",
                "empresa": "Empresa",
                "departamento": "SMART",
                "id": 4,
                "data_evento": "2026-11-01",
                "dt_hora": "2026-11-01 18:00",
            },
            {
                "contrato": "contrato-b",
                "numero_contrato": "numero-b",
                "chave_cliente": "cliente-b",
                "razao_social": "Cliente B",
                "empresa": "Empresa",
                "departamento": "SMART",
                "id": 5,
                "data_evento": "2026-11-01",
                "dt_hora": "2026-11-01 07:00",
            },
        ]
    )

    previsoes = calcular_previsoes(
        eventos,
        date(2026, 11, 15),
        periodos_selecionados=["Abertura", "Fechamento"],
        modo_periodos="todos",
    )

    assert previsoes["chave_cliente"].tolist() == ["cliente-a"]
    assert previsoes.iloc[0]["F_DISPAROS_MENOS_3_MESES"] == 2
    assert previsoes.iloc[0]["I_DISPAROS_MES_ATUAL"] == 2


def test_calcular_previsoes_sinaliza_reincidencia_sem_historico():
    eventos = _eventos_por_mes({"2026-11": 3})

    previsao = calcular_previsoes(eventos, date(2026, 11, 10)).iloc[0]

    assert previsao["L_MEDIA_DIARIA_HISTORICA"] == 0
    assert previsao["N_RAZAO_TENDENCIA"] == 0
    assert previsao["O_ALERTA_REINCIDENCIA"] == "SIM"
    assert previsao["P_PREVISAO_REGRESSAO"] == 0
    assert previsao["R_COMPARATIVO_ULTIMO_MES"] == 0


def test_calcular_previsoes_sinaliza_reincidencia_por_aumento_de_ritmo():
    eventos = _eventos_por_mes(
        {"2026-08": 1, "2026-09": 1, "2026-10": 1, "2026-11": 3}
    )

    previsao = calcular_previsoes(eventos, date(2026, 11, 15)).iloc[0]

    assert previsao["L_MEDIA_DIARIA_HISTORICA"] > 0
    assert previsao["M_TAXA_DIARIA_ATUAL"] >= 2 * previsao["L_MEDIA_DIARIA_HISTORICA"]
    assert previsao["O_ALERTA_REINCIDENCIA"] == "SIM"


def test_previsao_linear_nao_fica_negativa():
    eventos = _eventos_por_mes({"2026-08": 10, "2026-09": 2})

    previsao = calcular_previsoes(eventos, date(2026, 11, 15)).iloc[0]

    assert previsao["P_PREVISAO_REGRESSAO"] == 0


@pytest.mark.parametrize(
    ("total_atual", "classificacao"),
    [(3, "Baixa"), (4, "Média"), (9, "Média"), (10, "Alta")],
)
def test_classificacao_usa_limites_do_indicador(total_atual, classificacao):
    eventos = _eventos_por_mes({"2026-11": total_atual})

    previsao = calcular_previsoes(eventos, date(2026, 11, 15)).iloc[0]

    assert previsao["K_CLASSIFICACAO"] == classificacao


def test_calcular_previsoes_retorna_esquema_estavel_para_base_vazia():
    previsoes = calcular_previsoes(pd.DataFrame())

    assert previsoes.empty
    assert previsoes.columns.tolist() == COLUNAS_PREVISAO
