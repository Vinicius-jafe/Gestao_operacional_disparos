import sys
import types
from datetime import date, time
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest


def test_monitoramento_filtra_data_e_intervalo_horario(monkeypatch):
    eventos = pd.DataFrame(
        [
            (1, "2026-11-07", 7, 0),
            (2, "2026-11-07", 8, 0),
            (3, "2026-11-07", 14, 0),
            (4, "2026-11-07", 14, 1),
            (5, "2026-11-07", 15, 0),
            (6, "2026-11-08", 10, 0),
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
    database = types.ModuleType("src.database")
    database.verificar_integridade_banco = lambda: None
    database.sincronizar_planilhas = lambda: None
    database.carregar_eventos = lambda: eventos
    database.normalizar_nome_filial = lambda empresa, logradouro="": str(empresa).strip().upper()
    database.obter_carteira_df = lambda: carteira
    database.obter_carteira_filiais_dict = lambda: {"FILIAL ALFA": 100}
    database.salvar_carteira = lambda _: None
    monkeypatch.setitem(sys.modules, "src.database", database)

    app = AppTest.from_file(
        str(Path(__file__).parents[2] / "src" / "app.py")
    ).run()
    assert not app.exception

    seletor_data = next(
        elemento for elemento in app.date_input if elemento.label == "Dia dos eventos"
    )
    seletor_data.set_value(date(2026, 11, 7))
    seletor_inicio = next(
        elemento for elemento in app.time_input if elemento.label == "A partir de"
    )
    seletor_inicio.set_value(time(8, 0))
    seletor_fim = next(
        elemento for elemento in app.time_input if elemento.label == "Até"
    )
    seletor_fim.set_value(time(14, 0))
    app.run()

    metricas = {elemento.label: elemento.value for elemento in app.metric}
    assert metricas["Disparos na faixa"] == "2"
    assert metricas["Disparos SMART"] == "2"

    labels = {
        "Calcular indicadores complementares",
        "Calcular alertas de possível mau uso (todo o histórico)",
        "Calcular limitadores ativos (todo o histórico)",
        "Exibir comparação mensal detalhada (todo o histórico)",
    }
    for label in labels:
        next(elemento for elemento in app.checkbox if elemento.label == label).set_value(
            True
        )
    app.run()
    assert not app.exception
