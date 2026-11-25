import sys
import types
from datetime import date, time, timedelta
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest


def test_monitoramento_filtra_data_e_intervalo_horario(monkeypatch):
    data_hoje = date.today()
    data_anterior = data_hoje - timedelta(days=1)
    eventos = pd.DataFrame(
        [
            (1, data_anterior, 7, 0),
            (2, data_anterior, 8, 0),
            (3, data_anterior, 14, 0),
            (4, data_anterior, 14, 1),
            (5, data_anterior, 15, 0),
            (6, data_hoje, 10, 0),
        ],
        columns=["id", "data_evento", "hora_int", "minuto"],
    )
    eventos["data_evento"] = pd.to_datetime(eventos["data_evento"]).dt.date
    eventos["ano_mes"] = eventos["data_evento"].map(lambda value: value.strftime("%Y-%m"))
    eventos["empresa"] = "FILIAL ALFA"
    eventos["departamento"] = "Smart Alarm"
    eventos["numero_contrato"] = eventos["id"].map(lambda value: f"contrato-{value}")
    eventos["contrato"] = eventos["id"].map(lambda value: f"COD{value}")
    eventos["chave_cliente"] = eventos["id"].map(lambda value: f"cliente-{value}")
    eventos["razao_social"] = eventos["chave_cliente"]
    eventos["hora_evento"] = eventos.apply(
        lambda row: f"{row['hora_int']:02d}:{row['minuto']:02d}", axis=1
    )
    eventos["dt_hora"] = pd.to_datetime(eventos["data_evento"]) + pd.to_timedelta(
        eventos["hora_int"] * 60 + eventos["minuto"], unit="m"
    )
    eventos["minuto_do_dia"] = eventos["hora_int"] * 60 + eventos["minuto"]
    eventos["final_de_semana"] = False

    carteira = pd.DataFrame(
        [{"filial": "FILIAL ALFA", "clientes": 100, "tipo": "FILIAL"}]
    )
    relatorio_sensores = pd.DataFrame(
        [
            {
                "snapshot_id": 1,
                "period_start": date(2026, 11, 17),
                "period_end": date(2026, 11, 24),
                "collected_at": pd.Timestamp("2026-11-24 12:00:00"),
                "page_size": 25,
                "page_count": 1,
                "total_item_count": 1,
                "id": 1,
                "cod_contrato": "ABCD",
                "empresa": "FILIAL ALFA",
                "razao_social": "CLIENTE ALFA",
                "num_contrato": 123,
                "departamento": "Smart Alarm",
                "department_id": 4,
                "department_mapping_confidence": "OFICIAL",
                "disparos": 3,
                "message_count": 5,
                "zona_disparos": "Entrada",
                "data": date(2026, 11, 24),
                "mes": 11,
                "estado": "MG",
                "modelo_sensor": "PRESENÇA",
            }
        ]
    )
    outro_contrato = relatorio_sensores.iloc[0].copy()
    outro_contrato["id"] = 2
    outro_contrato["num_contrato"] = 456
    outro_contrato["razao_social"] = "CLIENTE FORA DO HORÁRIO"
    outro_dia = relatorio_sensores.iloc[0].copy()
    outro_dia["id"] = 3
    outro_dia["data"] = date(2026, 11, 23)
    relatorio_sensores = pd.concat(
        [
            relatorio_sensores,
            pd.DataFrame([outro_contrato, outro_dia]),
        ],
        ignore_index=True,
    )
    database = types.ModuleType("src.database")
    database.verificar_integridade_banco = lambda: None
    database.sincronizar_planilhas = lambda: None
    database.carregar_eventos = lambda: eventos
    database.carregar_relatorio_sensores = lambda: relatorio_sensores
    database.carregar_periodos_analise_sensores = lambda: pd.DataFrame(
        [{"dia": date(2026, 11, 24), "hora_cheia": 12}]
    )
    database.carregar_contratos_analise_sensores = (
        lambda data_analise, hora_analise: pd.DataFrame(
            [
                {
                    "num_contrato": 123,
                    "departamento": "SMART ALARM",
                    "estado": "MG",
                }
            ]
        )
    )
    database.carregar_acompanhamento_diario = lambda inicio, fim, empresas, departamentos: (
        eventos.loc[
            eventos["data_evento"].between(inicio, fim)
            & eventos["empresa"].isin(empresas)
            & eventos["departamento"].isin(departamentos)
        ]
        .groupby(
            ["data_evento", "empresa", "chave_cliente"],
            as_index=False,
        )
        .agg(
            razao_social=("razao_social", "max"),
            disparos=("id", "count"),
        )
        .rename(columns={"data_evento": "dia"})
    )
    database.normalizar_nome_filial = lambda empresa, logradouro="": str(empresa).strip().upper()
    database.obter_carteira_df = lambda: carteira
    database.obter_carteira_filiais_dict = lambda: {"FILIAL ALFA": 100}
    database.salvar_carteira = lambda _: None
    monkeypatch.setitem(sys.modules, "src.database", database)

    app = AppTest.from_file(
        str(Path(__file__).parents[2] / "src" / "app.py")
    ).run(timeout=10)
    assert not app.exception
    metricas = {elemento.label: elemento.value for elemento in app.metric}
    assert metricas["Disparos na faixa"] == "1"
    assert metricas["Registros de contrato/dia"] == "1"
    assert metricas["Clientes identificados"] == "1"
    assert metricas["Mensagens no período · API"] == "5"
    assert next(
        elemento for elemento in app.date_input if elemento.label == "Data da análise"
    ).value == date(2026, 11, 24)
    assert next(
        elemento
        for elemento in app.selectbox
        if elemento.label == "Hora da análise"
    ).value == 12

    seletor_data = next(
        elemento for elemento in app.date_input if elemento.label == "Dia dos eventos"
    )
    seletor_data.set_value(data_anterior)
    seletor_inicio = next(
        elemento for elemento in app.time_input if elemento.label == "A partir de"
    )
    seletor_inicio.set_value(time(8, 0))
    seletor_fim = next(
        elemento for elemento in app.time_input if elemento.label == "Até"
    )
    seletor_fim.set_value(time(14, 0))
    seletor_periodos = next(
        elemento
        for elemento in app.multiselect
        if elemento.label == "Períodos incluídos"
    )
    seletor_periodos.set_value(["Abertura"])
    app.run(timeout=10)

    metricas = {elemento.label: elemento.value for elemento in app.metric}
    assert metricas["Disparos na faixa"] == "1"
    assert metricas["Disparos SMART"] == "1"

    labels = {
        "Calcular indicadores complementares",
        "Calcular alertas de possível mau uso (todo o histórico)",
        "Calcular limitadores ativos (todo o histórico)",
        "Exibir comparação mensal detalhada (todo o histórico)",
        "Calcular previsões mensais",
    }
    for label in labels:
        next(elemento for elemento in app.checkbox if elemento.label == label).set_value(
            True
        )
    app.run(timeout=10)
    assert not app.exception
