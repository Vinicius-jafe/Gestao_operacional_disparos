import pandas as pd
import pytest

from src.config import FILIAIS_SP
from src.database import normalizar_nome_filial
from src.metrics import (
    calcular_distribuicao_horaria,
    calcular_distribuicao_periodos,
    calcular_recorrencia_complementar,
    calcular_taxa_por_carteira,
    classificar_faixa_horaria,
    comparar_disparos_mensais,
    detectar_limitador,
    detectar_possivel_mau_uso,
)


@pytest.mark.parametrize(
    ("hora", "periodo"),
    [
        (0, "Madrugada"),
        (5, "Madrugada"),
        (6, "Abertura"),
        (9, "Abertura"),
        (10, "Comercial"),
        (17, "Comercial"),
        (18, "Fechamento"),
        (21, "Fechamento"),
        (22, "Noite"),
        (23, "Noite"),
        (None, None),
    ],
)
def test_classificar_faixa_horaria_preserva_limites(hora, periodo):
    assert classificar_faixa_horaria(hora) == periodo


def test_classificar_faixa_horaria_rejeita_hora_fora_do_dia():
    with pytest.raises(ValueError, match="entre 0 e 23"):
        classificar_faixa_horaria(24)


def test_distribuicao_horaria_ignora_dt_hora_nulo_e_evento_duplicado():
    eventos = pd.DataFrame(
        {
            "id": [1, 2, 2, 3],
            "dt_hora": [
                "2026-11-16 05:59:00",
                "2026-11-16 06:00:00",
                "2026-11-16 06:00:00",
                None,
            ],
        }
    )

    por_hora = calcular_distribuicao_horaria(eventos).set_index("HORA")
    por_periodo = calcular_distribuicao_periodos(eventos).set_index("PERIODO")

    assert len(por_hora) == 24
    assert por_hora.loc[5, "DISPAROS"] == 1
    assert por_hora.loc[6, "DISPAROS"] == 1
    assert int(por_hora["DISPAROS"].sum()) == 2
    assert por_periodo.loc["Madrugada", "DISPAROS"] == 1
    assert por_periodo.loc["Abertura", "DISPAROS"] == 1


def _eventos_contrato(rows):
    eventos = pd.DataFrame(
        rows,
        columns=["id", "numero_contrato", "empresa", "dt_hora", "data_evento"],
    )
    eventos["dt_hora"] = pd.to_datetime(eventos["dt_hora"], errors="coerce")
    eventos["data_evento"] = pd.to_datetime(
        eventos["data_evento"], errors="coerce"
    ).dt.date
    return eventos


def test_mau_uso_exige_quatro_eventos_e_nenhum_em_outro_periodo():
    eventos = _eventos_contrato(
        [
            (1, "contrato-3", "EMPRESA A", "2026-11-01 06:00", "2026-11-01"),
            (2, "contrato-3", "EMPRESA A", "2026-11-01 18:00", "2026-11-01"),
            (3, "contrato-3", "EMPRESA A", "2026-11-02 06:00", "2026-11-02"),
            (4, "contrato-4", "EMPRESA A", "2026-11-01 06:00", "2026-11-01"),
            (5, "contrato-4", "EMPRESA A", "2026-11-01 18:00", "2026-11-01"),
            (6, "contrato-4", "EMPRESA A", "2026-11-02 06:00", "2026-11-02"),
            (7, "contrato-4", "EMPRESA A", "2026-11-03 21:59", "2026-11-03"),
        ]
    )

    resultado = detectar_possivel_mau_uso(eventos)

    assert resultado["NUMERO_CONTRATO"].tolist() == ["contrato-4"]
    assert resultado.iloc[0]["DISPAROS_ABERTURA_FECHAMENTO"] == 4
    assert resultado.iloc[0]["DISPAROS_OUTROS_PERIODOS"] == 0


def test_mau_uso_agrupa_numero_entre_empresas_e_ignora_contrato_vazio():
    eventos = _eventos_contrato(
        [
            (1, "compartilhado", "EMPRESA A", "2026-11-01 06:00", "2026-11-01"),
            (2, "compartilhado", "EMPRESA A", "2026-11-01 18:00", "2026-11-01"),
            (3, "compartilhado", "EMPRESA B", "2026-11-02 06:00", "2026-11-02"),
            (4, "compartilhado", "EMPRESA B", "2026-11-02 18:00", "2026-11-02"),
            (5, " ", "EMPRESA A", "2026-11-01 06:00", "2026-11-01"),
            (6, " ", "EMPRESA A", "2026-11-01 18:00", "2026-11-01"),
            (7, " ", "EMPRESA A", "2026-11-02 06:00", "2026-11-02"),
            (8, " ", "EMPRESA A", "2026-11-02 18:00", "2026-11-02"),
        ]
    )

    resultado = detectar_possivel_mau_uso(eventos)

    assert resultado["NUMERO_CONTRATO"].tolist() == ["compartilhado"]


def test_mau_uso_nao_sinaliza_evento_sem_horario_como_faixa_valida():
    eventos = _eventos_contrato(
        [
            (1, "contrato-a", "EMPRESA A", "2026-11-01 06:00", "2026-11-01"),
            (2, "contrato-a", "EMPRESA A", "2026-11-01 18:00", "2026-11-01"),
            (3, "contrato-a", "EMPRESA A", "2026-11-02 06:00", "2026-11-02"),
            (4, "contrato-a", "EMPRESA A", None, "2026-11-02"),
        ]
    )

    assert detectar_possivel_mau_uso(eventos).empty


def test_limitador_exige_cinco_e_separa_por_data_e_hora():
    eventos = _eventos_contrato(
        [
            (1, "quatro", "EMPRESA A", "2026-11-01 10:01", "2026-11-01"),
            (2, "quatro", "EMPRESA A", "2026-11-01 10:02", "2026-11-01"),
            (3, "quatro", "EMPRESA A", "2026-11-01 10:03", "2026-11-01"),
            (4, "quatro", "EMPRESA A", "2026-11-01 10:04", "2026-11-01"),
            (5, "cinco", "EMPRESA A", "2026-11-01 10:10", "2026-11-01"),
            (6, "cinco", "EMPRESA A", "2026-11-01 10:11", "2026-11-01"),
            (7, "cinco", "EMPRESA B", "2026-11-01 10:12", "2026-11-01"),
            (8, "cinco", "EMPRESA B", "2026-11-01 10:13", "2026-11-01"),
            (9, "cinco", "EMPRESA B", "2026-11-01 10:14", "2026-11-01"),
            (10, "cinco", "EMPRESA B", "2026-11-01 11:10", "2026-11-01"),
            (11, "cinco", "EMPRESA B", "2026-11-02 10:10", "2026-11-02"),
        ]
    )

    resultado = detectar_limitador(eventos)

    assert len(resultado) == 1
    assert resultado.iloc[0]["NUMERO_CONTRATO"] == "cinco"
    assert resultado.iloc[0]["HORA"] == 10
    assert resultado.iloc[0]["OCORRENCIAS"] == 5


def test_limitador_ignora_numero_vazio_e_id_duplicado():
    eventos = _eventos_contrato(
        [
            (1, " ", "EMPRESA A", "2026-11-01 10:00", "2026-11-01"),
            (2, "valid", "EMPRESA A", "2026-11-01 10:00", "2026-11-01"),
            (2, "valid", "EMPRESA B", "2026-11-01 10:00", "2026-11-01"),
            (3, "valid", "EMPRESA A", "2026-11-01 10:00", "2026-11-01"),
            (4, "valid", "EMPRESA A", "2026-11-01 10:00", "2026-11-01"),
            (5, "valid", "EMPRESA A", "2026-11-01 10:00", "2026-11-01"),
        ]
    )

    assert detectar_limitador(eventos).empty


def test_recorrencia_complementar_calcula_dias_meses_e_medias():
    eventos = pd.DataFrame(
        [
            ("cliente-a", "Cliente A", "FILIAL A", "Smart", 1, "2026-01-01"),
            ("cliente-a", "Cliente A", "FILIAL A", "Smart", 2, "2026-01-01"),
            ("cliente-a", "Cliente A", "FILIAL A", "Smart", 3, "2026-02-02"),
            ("cliente-a", "Cliente A", "FILIAL A", "Smart", 4, "2026-02-02"),
            ("cliente-a", "Cliente A", "FILIAL A", "Smart", 5, "2026-02-03"),
            (None, "Sem chave", "FILIAL A", "Smart", 6, "2026-02-03"),
            (" ", "Chave vazia", "FILIAL A", "Smart", 7, "2026-02-03"),
        ],
        columns=[
            "chave_cliente",
            "razao_social",
            "empresa",
            "departamento",
            "id",
            "data_evento",
        ],
    )

    resultado = calcular_recorrencia_complementar(eventos)
    cliente = resultado.iloc[0]

    assert len(resultado) == 1
    assert cliente["CHAVE_CLIENTE"] == "cliente-a"
    assert cliente["TOTAL_DISPAROS"] == 5
    assert cliente["DIAS_DISTINTOS"] == 3
    assert cliente["MESES_ATIVOS"] == 2
    assert cliente["MEDIA_DISPAROS_MES"] == 2.5
    assert cliente["MAX_DISPAROS_MES"] == 3


def test_recorrencia_complementar_deduplica_eventos():
    eventos = pd.DataFrame(
        [
            ("cliente-a", "Cliente A", "FILIAL A", "Smart", 1, "2026-01-01"),
            ("cliente-a", "Cliente A", "FILIAL A", "Smart", 1, "2026-01-01"),
        ],
        columns=[
            "chave_cliente",
            "razao_social",
            "empresa",
            "departamento",
            "id",
            "data_evento",
        ],
    )

    resultado = calcular_recorrencia_complementar(eventos)

    assert resultado.iloc[0]["TOTAL_DISPAROS"] == 1
    assert resultado.iloc[0]["MESES_ATIVOS"] == 1


def test_recorrencia_complementar_uma_data_e_um_mes():
    eventos = pd.DataFrame(
        [
            ("cliente-a", "Cliente A", "FILIAL A", "Smart", 1, "2026-01-01"),
        ],
        columns=[
            "chave_cliente",
            "razao_social",
            "empresa",
            "departamento",
            "id",
            "data_evento",
        ],
    )

    cliente = calcular_recorrencia_complementar(eventos).iloc[0]

    assert cliente["TOTAL_DISPAROS"] == 1
    assert cliente["DIAS_DISTINTOS"] == 1
    assert cliente["MESES_ATIVOS"] == 1
    assert cliente["MEDIA_DISPAROS_MES"] == 1
    assert cliente["MAX_DISPAROS_MES"] == 1


def test_comparacao_mensal_preserva_ano_e_deduplica():
    eventos = pd.DataFrame(
        [
            (
                "Empresa A",
                "Smart",
                "N1",
                "C1",
                "Cliente",
                1,
                "2025-11-02",
                "2025-11",
            ),
            (
                "Empresa A",
                "Smart",
                "N1",
                "C1",
                "Cliente",
                1,
                "2025-11-02",
                "2025-11",
            ),
            (
                "Empresa A",
                "Smart",
                "N1",
                "C1",
                "Cliente",
                2,
                "2026-11-02",
                "2026-11",
            ),
            ("Empresa A", "Smart", "N1", "C1", "Cliente", 3, None, "2027-01"),
        ],
        columns=[
            "empresa",
            "departamento",
            "numero_contrato",
            "contrato",
            "razao_social",
            "id",
            "data_evento",
            "ano_mes",
        ],
    )

    resultado = comparar_disparos_mensais(eventos)

    assert resultado["ano_mes"].tolist() == ["2025-11", "2026-11", "2027-01"]
    assert resultado["total_disparos"].tolist() == [1, 1, 1]


def test_taxa_carteira_consolida_sp_e_nao_duplica_join():
    eventos = pd.DataFrame(
        [
            ("FILIAL EMIVE SP BERRINI", 1),
            ("FILIAL EMIVE CAMPINAS", 2),
            ("FILIAL SEM CARTEIRA", 3),
            ("FILIAL SEM CARTEIRA", 3),
        ],
        columns=["empresa", "id"],
    )
    carteira = pd.DataFrame(
        [
            (FILIAIS_SP[0], 10, "FILIAL"),
            (FILIAIS_SP[0], 5, "FILIAL"),
            (FILIAIS_SP[3], 20, "FILIAL"),
            ("FILIAL SEM EVENTOS", 100, "FILIAL"),
            ("CARTEIRA ZERO", 0, "FILIAL"),
        ],
        columns=["filial", "clientes", "tipo"],
    )

    resultado = calcular_taxa_por_carteira(
        eventos,
        carteira,
        normalizar_nome_filial,
    ).set_index("FILIAL")

    assert resultado.loc["SP", "CLIENTES"] == 35
    assert resultado.loc["SP", "DISPAROS"] == 2
    assert resultado.loc["SP", "TAXA"] == pytest.approx(2 / 35)
    assert resultado.loc["FILIAL SEM EVENTOS", "DISPAROS"] == 0
    assert resultado.loc["CARTEIRA ZERO", "TAXA"] == 0
    assert resultado.loc["FILIAL SEM CARTEIRA", "DISPAROS"] == 1
    assert resultado.loc["FILIAL SEM CARTEIRA", "SEM_CARTEIRA"]
    assert int(resultado["DISPAROS"].sum()) == 3
