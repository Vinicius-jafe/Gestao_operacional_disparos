import calendar
from datetime import date, time, timedelta
import io

import pandas as pd
import plotly.express as px
import streamlit as st

from src.database import (
    carregar_acompanhamento_diario,
    carregar_contratos_analise_sensores,
    carregar_eventos,
    carregar_periodos_analise_sensores,
    carregar_relatorio_sensores,
    normalizar_nome_filial,
    obter_carteira_df,
    obter_carteira_filiais_dict,
    salvar_carteira,
    sincronizar_planilhas,
    verificar_integridade_banco,
)
from src.metrics import (
    PERIODOS_HORARIOS,
    calcular_distribuicao_horaria,
    calcular_distribuicao_periodos,
    calcular_metricas_filiais,
    calcular_recorrencia_complementar,
    calcular_taxa_por_carteira,
    comparar_disparos_mensais,
    detectar_limitador,
    detectar_possivel_mau_uso,
    filtrar_por_periodos_horarios,
    preparar_serie_diaria,
    processar_reincidencia_clientes,
)
from src.presentation import incluir_cod_contrato
from src.prediction import calcular_previsoes


st.set_page_config(
    page_title="Gestão de Disparos",
    page_icon="📊",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
        color-scheme: dark;
        --page-bg: #0e1013;
        --surface: #191c21;
        --surface-raised: #20242a;
        --ink: #f1f3f5;
        --muted: #a3aab5;
        --accent: #83aaff;
        --line: #30353d;
        --success-bg: #193024;
        --success-ink: #a9e3bd;
        --danger-bg: #392222;
        --danger-ink: #ffb4aa;
        --radius: 12px;
    }

    html, body {
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
        color: var(--ink);
    }

    .stApp, [data-testid="stAppViewContainer"] {
        background: var(--page-bg);
        color: var(--ink);
    }

    [data-testid="stHeader"], [data-testid="stToolbar"] {
        background-color: var(--page-bg);
    }

    [data-testid="stMarkdownContainer"] {
        color: var(--ink);
    }

    [data-testid="stSidebar"] {
        background: var(--surface);
        border-right: 1px solid var(--line);
    }

    [data-testid="stCaptionContainer"] {
        color: var(--muted);
    }

    .block-container {
        max-width: 1440px;
        padding: 2.25rem 2.5rem 4rem;
    }

    .page-kicker {
        color: var(--accent);
        font-size: 0.8125rem;
        font-weight: 650;
        letter-spacing: 0.04em;
        margin-bottom: 0.35rem;
    }

    h1, h2, h3 {
        color: var(--ink);
        letter-spacing: -0.025em;
    }

    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: 1.1rem 1.2rem;
        box-shadow: none;
    }

    [data-testid="stMetricLabel"] {
        color: var(--muted);
        font-size: 0.85rem;
    }

    [data-testid="stMetricValue"] {
        color: var(--ink);
        font-weight: 650;
        letter-spacing: -0.03em;
    }

    [data-testid="stMetricDelta"] {
        font-weight: 550;
    }

    [data-baseweb="tab-list"] {
        gap: 1.5rem;
        border-bottom: 1px solid var(--line);
    }

    [data-baseweb="tab"] {
        color: var(--muted);
        font-weight: 550;
    }

    [aria-selected="true"][data-baseweb="tab"] {
        color: var(--accent);
    }

    [data-baseweb="tab-highlight"] {
        background-color: var(--accent);
    }

    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        overflow: hidden;
    }

    [data-testid="stExpander"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--radius);
    }

    input, textarea, [data-baseweb="select"] > div {
        background-color: var(--surface-raised);
        color: var(--ink);
        border-color: var(--line);
    }

    .stButton > button, .stDownloadButton > button {
        border-radius: 8px;
        font-weight: 550;
        min-height: 2.75rem;
        transition: transform 160ms ease, border-color 160ms ease, background-color 160ms ease;
    }

    .stButton > button:hover, .stDownloadButton > button:hover {
        border-color: var(--accent);
        transform: translateY(-2px);
    }

    @media (max-width: 700px) {
        .block-container {
            padding: 1.5rem 1rem 3rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    verificar_integridade_banco()
    sincronizar_planilhas()
except Exception as erro:
    st.error(f"Não foi possível carregar os dados: {erro}")
    st.stop()


@st.cache_data(ttl=60)
def obter_dados_painel():
    return carregar_eventos(), obter_carteira_df(), obter_carteira_filiais_dict()


@st.cache_data(ttl=60)
def obter_dados_acompanhamento(
    data_inicio: date,
    data_fim: date,
    empresas: tuple[str, ...],
    departamentos: tuple[str, ...],
) -> pd.DataFrame:
    return carregar_acompanhamento_diario(
        data_inicio,
        data_fim,
        list(empresas),
        list(departamentos),
    )


@st.cache_data(ttl=60)
def obter_relatorio_sensores() -> pd.DataFrame:
    return carregar_relatorio_sensores()


@st.cache_data(ttl=60)
def obter_periodos_analise_sensores() -> pd.DataFrame:
    return carregar_periodos_analise_sensores()


@st.cache_data(ttl=60)
def obter_contratos_analise_sensores(
    data_analise: date, hora_analise: int
) -> pd.DataFrame:
    return carregar_contratos_analise_sensores(data_analise, hora_analise)


df, df_carteira, dict_carteiras = obter_dados_painel()

st.markdown('<div class="page-kicker">Operações · monitoramento</div>', unsafe_allow_html=True)
st.title("Gestão de disparos")
st.caption("Acompanhamento de eventos, metas por filial e recorrência de clientes.")

if df is None or df.empty:
    st.warning("O banco está disponível, mas ainda não há eventos para exibir.")
    if st.button("Atualizar dados"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

hoje = date.today()
ontem = hoje - timedelta(days=1)
mes_atual = hoje.strftime("%Y-%m")

with st.sidebar:
    st.header("Filtros")
    if st.button("Atualizar dados", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    empresas_disponiveis = sorted(df["empresa"].dropna().unique().tolist())
    filiais_carteira = (
        df_carteira.loc[df_carteira["tipo"] == "FILIAL", "filial"].tolist()
        if not df_carteira.empty
        else []
    )
    opcoes_filiais = sorted(set(empresas_disponiveis + filiais_carteira))
    filiais_selecionadas = st.multiselect(
        "Filiais",
        options=opcoes_filiais,
        default=opcoes_filiais,
    )

    departamentos_disponiveis = sorted(
        df["departamento"].dropna().unique().tolist()
    )
    departamentos_selecionados = st.multiselect(
        "Departamentos",
        options=departamentos_disponiveis,
        default=departamentos_disponiveis,
    )

    st.divider()
    st.subheader("Base de clientes")
    with st.expander("Ajustar carteira"):
        carteira_editada = st.data_editor(
            df_carteira,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "filial": st.column_config.TextColumn("FILIAL", width="large"),
                "clientes": st.column_config.NumberColumn(
                    "CLIENTES", min_value=0, step=1, format="%d"
                ),
                "tipo": st.column_config.TextColumn("TIPO", width="medium"),
            },
        )
        if st.button("Salvar carteira", type="primary", width="stretch"):
            salvar_carteira(carteira_editada)
            st.cache_data.clear()
            st.success("Carteira atualizada.")
            st.rerun()

df_filtrado = df[
    df["empresa"].isin(filiais_selecionadas)
    & df["departamento"].isin(departamentos_selecionados)
].copy()

historico_label = "Todo o histórico"
meses_disponiveis = sorted(
    df_filtrado["ano_mes"].dropna().unique().tolist(), reverse=True
)
opcoes_periodo = [historico_label, *meses_disponiveis]

with st.sidebar:
    periodo = st.selectbox(
        "Período",
        options=opcoes_periodo,
        index=opcoes_periodo.index(mes_atual) if mes_atual in opcoes_periodo else 0,
    )
    st.subheader("Faixa horária das análises")
    periodos_selecionados = st.multiselect(
        "Períodos incluídos",
        options=list(PERIODOS_HORARIOS),
        default=[],
        key="periodos_horarios",
    )
    modo_periodos = "qualquer"
    if len(periodos_selecionados) > 1:
        criterio_periodos = st.radio(
            "Clientes com disparos em",
            options=[
                "Qualquer período selecionado",
                "Todos os períodos selecionados",
            ],
            horizontal=True,
            key="criterio_periodos_horarios",
        )
        if criterio_periodos == "Todos os períodos selecionados":
            modo_periodos = "todos"

if periodo == historico_label:
    df_fechamento = df_filtrado[df_filtrado["data_evento"] <= ontem].copy()
    modo_historico = True
    dias_decorridos = max(df_fechamento["data_evento"].nunique(), 1)
    dias_totais_mes = dias_decorridos
    descricao_periodo = f"Histórico até {ontem.strftime('%d/%m/%Y')}"
else:
    df_mes = df_filtrado[df_filtrado["ano_mes"] == periodo].copy()
    ano_selecionado, mes_selecionado = map(int, periodo.split("-"))
    dias_totais_mes = calendar.monthrange(ano_selecionado, mes_selecionado)[1]
    modo_historico = False

    if periodo == mes_atual:
        df_fechamento = df_mes[df_mes["data_evento"] <= ontem].copy()
        dias_decorridos = max(ontem.day, 1)
        descricao_periodo = (
            f"{periodo} · dados fechados até {ontem.strftime('%d/%m/%Y')}"
        )
    else:
        df_fechamento = df_mes
        dias_decorridos = dias_totais_mes
        descricao_periodo = f"{periodo} · mês encerrado"

mascara_smart = df_fechamento["departamento"].str.upper().str.contains(
    "SMART", na=False
)
df_smart = df_fechamento[mascara_smart]
df_outros = df_fechamento[~mascara_smart]

st.caption(f"Período analisado: {descricao_periodo}")

tab_visao, tab_pareto, tab_plantao, tab_acompanhamento, tab_previsao, tab_sensores = st.tabs(
    [
        "Visão geral de filiais",
        "Reincidência e Pareto",
        "Monitoramento",
        "Acompanhamento",
        "Previsões",
        "Sensores",
    ]
)

with tab_visao:
    base_clientes_smart = sum(
        dict_carteiras.get(filial, 0)
        for filial in filiais_selecionadas
        if filial in filiais_carteira
    )
    total_smart = len(df_smart)
    total_geral = len(df_fechamento)
    media_smart_dia = (
        total_smart / dias_decorridos if dias_decorridos > 0 else 0.0
    )
    taxa_smart_real = (
        round(total_smart / base_clientes_smart, 2)
        if base_clientes_smart > 0
        else 0.0
    )
    taxa_smart_prevista = (
        round((media_smart_dia * dias_totais_mes) / base_clientes_smart, 2)
        if base_clientes_smart > 0
        else 0.0
    )

    st.subheader("Resumo operacional")
    metrica_base, metrica_smart, metrica_total = st.columns(3)
    metrica_base.metric("Base de clientes SMART", f"{base_clientes_smart:,}")
    metrica_smart.metric("Disparos SMART", f"{total_smart:,}")
    metrica_total.metric("Disparos totais", f"{total_geral:,}")
    metrica_real, metrica_prev = st.columns(2)
    metrica_real.metric("Taxa SMART atual", f"{taxa_smart_real:.2f}")
    metrica_prev.metric(
        "Projeção SMART",
        f"{taxa_smart_prevista:.2f}",
        delta=(
            f"{taxa_smart_prevista - 1.55:+.2f} vs. meta 1,55"
            if not modo_historico
            else None
        ),
        delta_color="inverse",
    )

    st.divider()
    st.subheader("Metas e projeções por filial")
    st.caption(
        "Comparação entre o volume projetado no período e o teto definido para cada filial."
    )

    metricas_filiais = calcular_metricas_filiais(
        df_smart,
        filiais_selecionadas,
        dict_carteiras,
        dias_decorridos,
        dias_totais_mes,
        modo_historico,
    )
    if metricas_filiais.empty:
        st.info("Selecione ao menos uma filial para calcular as métricas.")
    else:
        metricas_exibicao = metricas_filiais.copy()
        metricas_exibicao["STATUS"] = metricas_exibicao["STATUS"].map(
            {
                "Dentro da Meta": "🟢 Dentro da meta",
                "Fora da Meta": "🔴 Acima da meta",
            }
        )
        estilo_metricas = metricas_exibicao.style.apply(
            lambda linha: [
                (
                    "background-color: #193024; color: #a9e3bd; font-weight: 600"
                    if linha["STATUS"] == "🟢 Dentro da meta"
                    else "background-color: #392222; color: #ffb4aa; font-weight: 600"
                )
                if coluna == "STATUS"
                else ""
                for coluna in linha.index
            ],
            axis=1,
        )
        estilo_metricas = estilo_metricas.format(
            {
                "CLIENTES": "{:,.0f}",
                "DISPAROS": "{:,.0f}",
                "MEDIA": "{:,.1f}",
                "PREVISAO": "{:,.0f}",
                "TETO": "{:,.0f}",
                "SALDO": "{:+,.0f}",
                "TAXA ATUAL": "{:.2f}",
                "TAXA PREV": "{:.2f}",
            }
        )
        st.dataframe(
            estilo_metricas,
            hide_index=True,
            width="stretch",
            column_config={
                "FILIAIS": st.column_config.TextColumn("FILIAL", width="large"),
                "CLIENTES": st.column_config.NumberColumn("CLIENTES", format="%d"),
                "DISPAROS": st.column_config.NumberColumn("DISPAROS", format="%d"),
                "MEDIA": st.column_config.NumberColumn("MÉDIA/DIA", format="%.1f"),
                "PREVISAO": st.column_config.NumberColumn("PROJEÇÃO", format="%d"),
                "TETO": st.column_config.NumberColumn("TETO", format="%d"),
                "SALDO": st.column_config.NumberColumn("SALDO", format="%+d"),
                "TAXA ATUAL": st.column_config.NumberColumn(
                    "TAXA ATUAL", format="%.2f"
                ),
                "TAXA PREV": st.column_config.NumberColumn(
                    "TAXA PROJETADA", format="%.2f"
                ),
                "STATUS": st.column_config.TextColumn("STATUS", width="medium"),
            },
        )

        grafico_filiais = px.bar(
            metricas_filiais.sort_values("PREVISAO"),
            x="PREVISAO",
            y="FILIAIS",
            color="STATUS",
            orientation="h",
            barmode="group",
            color_discrete_map={
                "Dentro da Meta": "#83aaff",
                "Fora da Meta": "#ff8178",
            },
            labels={
                "PREVISAO": "Disparos projetados",
                "FILIAIS": "",
                "STATUS": "Consumo",
            },
        )
        grafico_filiais.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"family": "system-ui, sans-serif", "color": "#f1f3f5"},
            margin={"l": 8, "r": 16, "t": 12, "b": 8},
            legend={"orientation": "h", "y": 1.08, "x": 0},
            xaxis={
                "showgrid": True,
                "gridcolor": "#30353d",
                "zeroline": False,
                "title": "Disparos projetados",
            },
            yaxis={"showgrid": False, "title": ""},
        )
        st.plotly_chart(grafico_filiais, width="stretch")

    with st.expander("Taxa de disparos por carteira", expanded=False):
        st.caption(
            "Disparos do período selecionado por cliente da carteira. "
            "As unidades paulistas são consolidadas em SP."
        )
        taxas_carteira = calcular_taxa_por_carteira(
            df_fechamento,
            df_carteira,
            normalizar_nome_filial,
        )
        st.dataframe(
            taxas_carteira,
            hide_index=True,
            width="stretch",
            column_config={
                "FILIAL": st.column_config.TextColumn("FILIAL", width="large"),
                "CLIENTES": st.column_config.NumberColumn("CLIENTES", format="%d"),
                "DISPAROS": st.column_config.NumberColumn("DISPAROS", format="%d"),
                "TAXA": st.column_config.NumberColumn("DISPAROS / CLIENTE", format="%.4f"),
                "SEM_CARTEIRA": st.column_config.CheckboxColumn(
                    "SEM CORRESPONDÊNCIA NA CARTEIRA"
                ),
            },
        )
        sem_carteira = taxas_carteira.loc[taxas_carteira["SEM_CARTEIRA"]]
        if not sem_carteira.empty:
            st.warning(
                f"{len(sem_carteira)} empresa(s)/filial(is) sem correspondência "
                "na carteira."
            )

with tab_pareto:
    st.subheader("Clientes com reincidência")
    st.caption(
        "Disparos agrupados por cliente. A classificação crítica cobre a faixa acumulada até 80%."
    )
    st.caption(
        "COD exibe os quatro primeiros caracteres alfanuméricos; CONTRATO exibe o trecho após _."
    )

    clientes_smart = processar_reincidencia_clientes(df_smart)
    clientes_outros = processar_reincidencia_clientes(df_outros)
    clientes_todos = processar_reincidencia_clientes(df_fechamento)

    def renderizar_clientes(dataframe, nome_arquivo, titulo_aba):
        if dataframe.empty:
            st.info("Não há eventos para este recorte no período selecionado.")
            return

        colunas = [
            "CHAVE_CLIENTE",
            "RAZAO_SOCIAL",
            "EMPRESA",
            "DEPARTAMENTO",
            "TOTAL_DISPAROS",
            "DIAS_DISTINTOS",
            "CRITICIDADE_PARETO",
        ]
        dados_exibicao = incluir_cod_contrato(dataframe.loc[:, colunas])
        dados_exibicao = dados_exibicao.rename(
            columns={
                "RAZAO_SOCIAL": "CLIENTE",
                "EMPRESA": "FILIAL",
                "TOTAL_DISPAROS": "DISPAROS",
                "DIAS_DISTINTOS": "DIAS ATIVOS",
                "CRITICIDADE_PARETO": "PARETO",
            }
        )
        dados_exibicao = dados_exibicao.loc[
            :,
            [
                "COD",
                "CONTRATO",
                "CLIENTE",
                "FILIAL",
                "DEPARTAMENTO",
                "DISPAROS",
                "DIAS ATIVOS",
                "PARETO",
            ],
        ]
        estilo = dados_exibicao.style.apply(
            lambda linha: [
                (
                    "background-color: #392222; color: #ffb4aa; font-weight: 600"
                    if linha["PARETO"] == "🟥 Crítico"
                    else "background-color: #24282e; color: #d3d8e0"
                )
                if coluna == "PARETO"
                else ""
                for coluna in linha.index
            ],
            axis=1,
        )
        st.dataframe(
            estilo,
            hide_index=True,
            width="stretch",
            column_config={
                "COD": st.column_config.TextColumn("COD", width="small"),
                "CONTRATO": st.column_config.TextColumn("CONTRATO", width="medium"),
                "CLIENTE": st.column_config.TextColumn("CLIENTE", width="large"),
                "FILIAL": st.column_config.TextColumn("FILIAL", width="medium"),
                "DEPARTAMENTO": st.column_config.TextColumn(
                    "DEPARTAMENTO", width="medium"
                ),
                "DISPAROS": st.column_config.NumberColumn("DISPAROS", format="%d"),
                "DIAS ATIVOS": st.column_config.NumberColumn(
                    "DIAS ATIVOS", format="%d"
                ),
                "PARETO": st.column_config.TextColumn("PARETO", width="medium"),
            },
        )

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            dados_exibicao.to_excel(
                writer,
                index=False,
                sheet_name=titulo_aba[:31],
            )
        st.download_button(
            "Baixar relatório Excel",
            data=buffer.getvalue(),
            file_name=nome_arquivo,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_{nome_arquivo}",
        )

    aba_smart, aba_outros, aba_todos = st.tabs(
        [
            f"SMART · {len(clientes_smart)}",
            f"Outros · {len(clientes_outros)}",
            f"Todos · {len(clientes_todos)}",
        ]
    )
    with aba_smart:
        renderizar_clientes(clientes_smart, "reincidencia_smart.xlsx", "SMART")
    with aba_outros:
        renderizar_clientes(clientes_outros, "reincidencia_outros.xlsx", "Outros")
    with aba_todos:
        renderizar_clientes(clientes_todos, "reincidencia_geral.xlsx", "Geral")

    with st.expander("Indicadores complementares de recorrência", expanded=False):
        st.caption(
            "Indicadores complementares por chave do cliente; não reproduzem "
            "a aba REINC nem substituem a classificação Pareto."
        )
        if st.checkbox(
            "Calcular indicadores complementares",
            value=False,
            key="calcular_recorrencia_complementar",
        ):
            recorrencia = calcular_recorrencia_complementar(df_fechamento)
            if recorrencia.empty:
                st.info("Não há chaves de cliente válidas neste recorte.")
            else:
                st.dataframe(
                    recorrencia,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "CHAVE_CLIENTE": st.column_config.TextColumn(
                            "CHAVE DO CLIENTE", width="medium"
                        ),
                        "RAZAO_SOCIAL": st.column_config.TextColumn(
                            "CLIENTE", width="large"
                        ),
                        "EMPRESA": st.column_config.TextColumn("FILIAL"),
                        "DEPARTAMENTO": st.column_config.TextColumn("DEPARTAMENTO"),
                        "TOTAL_DISPAROS": st.column_config.NumberColumn(
                            "DISPAROS", format="%d"
                        ),
                        "DIAS_DISTINTOS": st.column_config.NumberColumn(
                            "DIAS DISTINTOS", format="%d"
                        ),
                        "MESES_ATIVOS": st.column_config.NumberColumn(
                            "MESES ATIVOS", format="%d"
                        ),
                        "MEDIA_DISPAROS_MES": st.column_config.NumberColumn(
                            "MÉDIA / MÊS", format="%.2f"
                        ),
                        "MAX_DISPAROS_MES": st.column_config.NumberColumn(
                            "MÁXIMO EM UM MÊS", format="%d"
                        ),
                    },
                )

with tab_plantao:
    @st.fragment(run_every="5m")
    def renderizar_monitoramento():
        st.subheader("Monitoramento por dia e horário")

        st.caption("Atualização automática a cada 5 minutos.")
        dados_monitoramento, _, _ = obter_dados_painel()
        df_monitoramento = dados_monitoramento[
            dados_monitoramento["empresa"].isin(filiais_selecionadas)
            & dados_monitoramento["departamento"].isin(departamentos_selecionados)
        ].copy()
        datas_normalizadas = pd.to_datetime(
            df_monitoramento["data_evento"], errors="coerce"
        ).dt.date
        df_monitoramento = df_monitoramento.loc[datas_normalizadas <= hoje].copy()
        datas_eventos = sorted(
            pd.to_datetime(df_monitoramento["data_evento"], errors="coerce")
            .dropna()
            .dt.date.unique()
        )

        if not datas_eventos:
            st.info("Não há datas de eventos disponíveis para os filtros selecionados.")
        else:
            data_padrao = hoje
            coluna_data, coluna_inicio, coluna_fim = st.columns(3)
            with coluna_data:
                data_selecionada = st.date_input(
                    "Dia dos eventos",
                    value=data_padrao,
                    min_value=datas_eventos[0],
                    max_value=hoje,
                    format="DD/MM/YYYY",
                    key="monitoramento_data",
                )
            with coluna_inicio:
                horario_inicio = st.time_input(
                    "A partir de",
                    value=time(8, 0),
                    key="monitoramento_horario_inicio",
                )
            with coluna_fim:
                horario_fim = st.time_input(
                    "Até",
                    value=time(14, 0),
                    key="monitoramento_horario_fim",
                )

            if horario_inicio > horario_fim:
                st.warning("O horário final deve ser igual ou posterior ao inicial.")
            else:
                minutos_inicio = horario_inicio.hour * 60 + horario_inicio.minute
                minutos_fim = horario_fim.hour * 60 + horario_fim.minute
                datas_normalizadas = pd.to_datetime(
                    df_monitoramento["data_evento"], errors="coerce"
                ).dt.date
                minutos_do_dia = pd.to_numeric(
                    df_monitoramento["minuto_do_dia"], errors="coerce"
                )
                df_faixa = df_monitoramento[
                    (datas_normalizadas == data_selecionada)
                    & minutos_do_dia.between(
                        minutos_inicio, minutos_fim, inclusive="both"
                    )
                ].copy()
                df_faixa = filtrar_por_periodos_horarios(
                    df_faixa,
                    periodos_selecionados=periodos_selecionados,
                    modo=modo_periodos,
                )

                descricao_filtro = (
                    ", ".join(periodos_selecionados)
                    if periodos_selecionados
                    else "todos os períodos"
                )
                st.caption(
                    f"{data_selecionada.strftime('%d/%m/%Y')} · "
                    f"{horario_inicio.strftime('%H:%M')}–{horario_fim.strftime('%H:%M')} · "
                    f"períodos: {descricao_filtro}"
                )

                if df_faixa.empty:
                    st.info("Não há eventos nessa data e faixa de horário.")
                else:
                    mascara_smart_faixa = df_faixa["departamento"].str.upper().str.contains(
                        "SMART", na=False
                    )
                    total_faixa = len(df_faixa)
                    total_smart_faixa = int(mascara_smart_faixa.sum())
                    clientes_faixa = df_faixa["chave_cliente"].nunique()
                    ultima_hora = df_faixa["hora_int"].max()

                    col_total, col_smart, col_clientes, col_hora = st.columns(4)
                    col_total.metric("Disparos na faixa", f"{total_faixa:,}")
                    col_smart.metric("Disparos SMART", f"{total_smart_faixa:,}")
                    col_clientes.metric("Clientes distintos", f"{clientes_faixa:,}")
                    col_hora.metric("Último registro", f"{int(ultima_hora):02d}:00")

                    distribuicao_hora = (
                        df_faixa.groupby("hora_int")["id"]
                        .count()
                        .rename("TOTAL_DISPAROS")
                        .reset_index()
                    )
                    grafico_hora = px.bar(
                        distribuicao_hora,
                        x="hora_int",
                        y="TOTAL_DISPAROS",
                        labels={
                            "hora_int": "Hora do dia",
                            "TOTAL_DISPAROS": "Disparos",
                        },
                        color_discrete_sequence=["#83aaff"],
                    )
                    grafico_hora.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font={"family": "system-ui, sans-serif", "color": "#f1f3f5"},
                        margin={"l": 8, "r": 16, "t": 12, "b": 8},
                        xaxis={
                            "tickmode": "linear",
                            "tick0": 0,
                            "dtick": 1,
                            "showgrid": False,
                        },
                        yaxis={
                            "showgrid": True,
                            "gridcolor": "#30353d",
                            "title": "Disparos",
                        },
                    )
                    distribuicao_departamento = (
                        df_faixa.groupby("departamento")["id"]
                        .count()
                        .rename("TOTAL_DISPAROS")
                        .reset_index()
                    )
                    grafico_departamento = px.pie(
                        distribuicao_departamento,
                        names="departamento",
                        values="TOTAL_DISPAROS",
                        hole=0.62,
                        color_discrete_sequence=[
                            "#83aaff",
                            "#5f84d6",
                            "#4766a6",
                            "#34496f",
                            "#273448",
                        ],
                        labels={
                            "departamento": "Departamento",
                            "TOTAL_DISPAROS": "Disparos",
                        },
                    )
                    grafico_departamento.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font={"family": "system-ui, sans-serif", "color": "#f1f3f5"},
                        margin={"l": 8, "r": 16, "t": 12, "b": 8},
                        legend={"orientation": "h", "y": -0.15},
                    )
                    grafico_departamento.update_traces(
                        textfont={"color": "#f1f3f5"}
                    )

                    coluna_horas, coluna_departamentos = st.columns([3, 2])
                    with coluna_horas:
                        st.subheader("Disparos por hora")
                        st.plotly_chart(grafico_hora, width="stretch")
                    with coluna_departamentos:
                        st.subheader("Distribuição por departamento")
                        st.plotly_chart(grafico_departamento, width="stretch")

                    st.subheader("Clientes com mais disparos na faixa")
                    ranking = (
                        df_faixa.groupby("chave_cliente", as_index=False)
                        .agg(
                            RAZAO_SOCIAL=("razao_social", "first"),
                            EMPRESA=("empresa", "first"),
                            DEPARTAMENTO=("departamento", "first"),
                            DISPAROS=("id", "count"),
                            PRIMEIRO_DISPARO=("hora_evento", "min"),
                            ULTIMO_DISPARO=("hora_evento", "max"),
                        )
                        .sort_values("DISPAROS", ascending=False)
                        .reset_index(drop=True)
                        .rename(columns={"chave_cliente": "CHAVE_CLIENTE"})
                    )
                    ranking = incluir_cod_contrato(ranking).rename(
                        columns={
                            "RAZAO_SOCIAL": "CLIENTE",
                            "EMPRESA": "FILIAL",
                        }
                    )
                    ranking = ranking.loc[
                        :,
                        [
                            "COD",
                            "CONTRATO",
                            "CLIENTE",
                            "FILIAL",
                            "DEPARTAMENTO",
                            "DISPAROS",
                            "PRIMEIRO_DISPARO",
                            "ULTIMO_DISPARO",
                        ],
                    ]
                    st.caption(
                        "COD identifica o prefixo alfanumérico; CONTRATO mostra o trecho após _."
                    )
                    st.dataframe(
                        ranking,
                        hide_index=True,
                        width="stretch",
                        column_config={
                            "COD": st.column_config.TextColumn("COD", width="small"),
                            "CONTRATO": st.column_config.TextColumn(
                                "CONTRATO", width="medium"
                            ),
                            "CLIENTE": st.column_config.TextColumn(
                                "CLIENTE", width="large"
                            ),
                            "FILIAL": st.column_config.TextColumn("FILIAL", width="medium"),
                            "DEPARTAMENTO": st.column_config.TextColumn(
                                "DEPARTAMENTO", width="medium"
                            ),
                            "DISPAROS": st.column_config.NumberColumn(
                                "DISPAROS", format="%d"
                            ),
                            "PRIMEIRO_DISPARO": st.column_config.TextColumn(
                                "PRIMEIRO DISPARO", width="small"
                            ),
                            "ULTIMO_DISPARO": st.column_config.TextColumn(
                                "ÚLTIMO DISPARO", width="small"
                            ),
                        },
                    )


    renderizar_monitoramento()
    with st.expander("Análises operacionais complementares", expanded=False):
        st.caption(
            "Disparos por hora, por período e previsões respeitam o período e os "
            "períodos horários da barra lateral. Mau uso e limitador consideram todo "
            "o histórico, sem esses filtros."
        )
        if df_fechamento.empty:
            st.info("Não há eventos no período selecionado.")
        else:
            df_fechamento_horario = filtrar_por_periodos_horarios(
                df_fechamento,
                periodos_selecionados=periodos_selecionados,
                modo=modo_periodos,
            )
            eventos_sem_horario = pd.to_datetime(
                df_fechamento["dt_hora"], errors="coerce"
            ).isna().sum()
            if eventos_sem_horario:
                st.caption(
                    f"{eventos_sem_horario} evento(s) sem data/hora foram excluídos "
                    "da distribuição."
                )

            if df_fechamento_horario.empty:
                st.info("Não há eventos nos períodos selecionados.")
            else:
                distribuicao_horaria = calcular_distribuicao_horaria(
                    df_fechamento_horario
                )
                distribuicao_periodos = calcular_distribuicao_periodos(
                    df_fechamento_horario
                )
                coluna_distribuicao, coluna_periodos = st.columns(2)
                with coluna_distribuicao:
                    st.subheader("Disparos por hora")
                    st.plotly_chart(
                        px.bar(
                            distribuicao_horaria,
                            x="HORA",
                            y="DISPAROS",
                            labels={"HORA": "Hora", "DISPAROS": "Disparos"},
                        ),
                        width="stretch",
                    )
                with coluna_periodos:
                    st.subheader("Disparos por período")
                    st.plotly_chart(
                        px.bar(
                            distribuicao_periodos,
                            x="PERIODO",
                            y="DISPAROS",
                            category_orders={
                                "PERIODO": list(distribuicao_periodos["PERIODO"])
                            },
                            labels={"PERIODO": "Período", "DISPAROS": "Disparos"},
                        ),
                        width="stretch",
                    )

        if st.checkbox(
            "Calcular alertas de possível mau uso (todo o histórico)",
            value=False,
            key="calcular_possivel_mau_uso",
        ):
            alertas_mau_uso = detectar_possivel_mau_uso(df)
            if alertas_mau_uso.empty:
                st.info("Nenhum contrato atende à regra de possível mau uso.")
            else:
                st.dataframe(
                    alertas_mau_uso,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "NUMERO_CONTRATO": st.column_config.TextColumn(
                            "NÚMERO DO CONTRATO"
                        ),
                        "DISPAROS_ABERTURA_FECHAMENTO": st.column_config.NumberColumn(
                            "ABERTURA + FECHAMENTO", format="%d"
                        ),
                        "DISPAROS_OUTROS_PERIODOS": st.column_config.NumberColumn(
                            "OUTROS PERÍODOS", format="%d"
                        ),
                    },
                )

        if st.checkbox(
            "Calcular limitadores ativos (todo o histórico)",
            value=False,
            key="calcular_limitador",
        ):
            limitadores = detectar_limitador(df)
            if limitadores.empty:
                st.info("Nenhum agrupamento atende ao limite de cinco disparos.")
            else:
                st.dataframe(
                    limitadores,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "NUMERO_CONTRATO": st.column_config.TextColumn(
                            "NÚMERO DO CONTRATO"
                        ),
                        "DATA_EVENTO": st.column_config.DateColumn(
                            "DATA DO EVENTO", format="DD/MM/YYYY"
                        ),
                        "HORA": st.column_config.NumberColumn("HORA", format="%02d"),
                        "OCORRENCIAS": st.column_config.NumberColumn(
                            "OCORRÊNCIAS", format="%d"
                        ),
                    },
                )

        if st.checkbox(
            "Exibir comparação mensal detalhada (todo o histórico)",
            value=False,
            key="comparacao_mensal",
        ):
            comparacao_mensal = comparar_disparos_mensais(df_filtrado)
            if comparacao_mensal.empty:
                st.info("Não há eventos com mês válido para comparar.")
            else:
                st.dataframe(
                    comparacao_mensal,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "ano_mes": st.column_config.TextColumn("ANO-MÊS"),
                        "total_disparos": st.column_config.NumberColumn(
                            "DISPAROS", format="%d"
                        ),
                    },
                )

with tab_previsao:
    st.subheader("Previsão mensal por cliente")
    st.caption(
        "Usa os três meses fechados anteriores e os dados do mês atual até ontem. "
        "A severidade considera o volume de disparos do mês atual e os períodos "
        "selecionados na barra lateral."
    )
    if st.checkbox(
        "Calcular previsões mensais",
        value=False,
        key="calcular_previsoes_mensais",
    ):
        previsoes = calcular_previsoes(
            df_filtrado,
            hoje,
            periodos_selecionados=periodos_selecionados,
            modo_periodos=modo_periodos,
        )
        if previsoes.empty:
            st.info("Não há eventos no intervalo necessário para calcular previsões.")
        else:
            st.dataframe(
                previsoes,
                hide_index=True,
                width="stretch",
                column_config={
                    "K_CLASSIFICACAO": st.column_config.TextColumn("SEVERIDADE"),
                    "L_MEDIA_DIARIA_HISTORICA": st.column_config.NumberColumn(
                        "MÉDIA DIÁRIA HISTÓRICA", format="%.2f"
                    ),
                    "M_TAXA_DIARIA_ATUAL": st.column_config.NumberColumn(
                        "TAXA DIÁRIA ATUAL", format="%.2f"
                    ),
                    "N_RAZAO_TENDENCIA": st.column_config.NumberColumn(
                        "RAZÃO DE TENDÊNCIA", format="%.2f"
                    ),
                    "O_ALERTA_REINCIDENCIA": st.column_config.TextColumn(
                        "ALERTA DE REINCIDÊNCIA"
                    ),
                    "P_PREVISAO_REGRESSAO": st.column_config.NumberColumn(
                        "PREVISÃO LINEAR", format="%.2f"
                    ),
                    "Q_PROJECAO_FECHAMENTO": st.column_config.NumberColumn(
                        "PROJEÇÃO DE FECHAMENTO", format="%.2f"
                    ),
                    "R_COMPARATIVO_ULTIMO_MES": st.column_config.NumberColumn(
                        "VS. ÚLTIMO MÊS", format="%.2f"
                    ),
                },
            )

with tab_acompanhamento:
    st.subheader("Acompanhamento diário")
    st.caption(
        "Compare a evolução diária dos disparos para as filiais e os clientes "
        "incluídos nos filtros globais."
    )

    datas_acompanhamento = (
        pd.to_datetime(df["data_evento"], errors="coerce")
        .dropna()
        .dt.date
    )
    if datas_acompanhamento.empty:
        st.info("Não há datas de eventos disponíveis para os filtros selecionados.")
    else:
        if periodo == historico_label:
            data_minima = datas_acompanhamento.min()
            data_maxima = datas_acompanhamento.max()
        else:
            ano_periodo, mes_periodo = map(int, periodo.split("-"))
            data_minima = date(ano_periodo, mes_periodo, 1)
            data_maxima = min(
                date(
                    ano_periodo,
                    mes_periodo,
                    calendar.monthrange(ano_periodo, mes_periodo)[1],
                ),
                hoje,
            )

        datas_selecionadas = st.date_input(
            "Período do acompanhamento",
            value=(data_minima, data_maxima),
            min_value=data_minima,
            max_value=data_maxima,
            format="DD/MM/YYYY",
            key=f"acompanhamento_periodo_{periodo}",
        )
        if len(datas_selecionadas) != 2:
            st.info("Selecione as datas inicial e final para exibir o acompanhamento.")
        else:
            data_inicio, data_fim = datas_selecionadas
            dados_acompanhamento = obter_dados_acompanhamento(
                data_inicio,
                data_fim,
                tuple(filiais_selecionadas),
                tuple(departamentos_selecionados),
            )
            if dados_acompanhamento.empty:
                st.info("Não há disparos no período e nos filtros selecionados.")
            else:
                st.subheader("Disparos diários por filial")
                totais_filiais_acompanhamento = (
                    dados_acompanhamento.groupby("empresa")["disparos"]
                    .sum()
                    .sort_values(ascending=False)
                )
                opcoes_filiais_acompanhamento = sorted(
                    totais_filiais_acompanhamento.index.tolist()
                )
                filiais_padrao_acompanhamento = (
                    totais_filiais_acompanhamento.head(5).index.tolist()
                )
                filiais_grafico = st.multiselect(
                    "Filiais para comparar",
                    options=opcoes_filiais_acompanhamento,
                    default=filiais_padrao_acompanhamento,
                    key="acompanhamento_filiais",
                )
                if not filiais_grafico:
                    st.info("Selecione ao menos uma filial para exibir o gráfico.")
                else:
                    serie_filiais = preparar_serie_diaria(
                        dados_acompanhamento,
                        "empresa",
                        filiais_grafico,
                        data_inicio,
                        data_fim,
                    )
                    grafico_filiais_diario = px.line(
                        serie_filiais,
                        x="dia",
                        y="disparos",
                        color="serie",
                        markers=True,
                        labels={
                            "dia": "Dia",
                            "disparos": "Disparos",
                            "serie": "Filial",
                        },
                    )
                    grafico_filiais_diario.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font={"family": "system-ui, sans-serif", "color": "#f1f3f5"},
                        margin={"l": 8, "r": 16, "t": 12, "b": 8},
                        hovermode="x unified",
                        legend={"orientation": "h", "y": 1.08, "x": 0},
                        xaxis={"title": "", "tickformat": "%d/%m", "showgrid": False},
                        yaxis={
                            "title": "Disparos",
                            "rangemode": "tozero",
                            "showgrid": True,
                            "gridcolor": "#30353d",
                        },
                    )
                    grafico_filiais_diario.update_traces(
                        line={"width": 2},
                        marker={"size": 6},
                    )
                    st.plotly_chart(grafico_filiais_diario, width="stretch")

                st.divider()
                st.subheader("Disparos diários por cliente")
                filiais_clientes = sorted(
                    dados_acompanhamento["empresa"].dropna().unique().tolist()
                )
                filial_clientes = st.selectbox(
                    "Filial dos clientes",
                    options=["Todas as filiais", *filiais_clientes],
                    key="acompanhamento_filial_clientes",
                )
                dados_clientes = dados_acompanhamento
                if filial_clientes != "Todas as filiais":
                    dados_clientes = dados_clientes.loc[
                        dados_clientes["empresa"] == filial_clientes
                    ]

                dados_clientes = dados_clientes.loc[
                    dados_clientes["chave_cliente"].notna()
                    & dados_clientes["chave_cliente"]
                    .astype("string")
                    .str.strip()
                    .ne("")
                ].copy()
                if dados_clientes.empty:
                    st.info("Não há clientes identificados para a filial selecionada.")
                else:
                    resumo_clientes = (
                        dados_clientes.groupby("chave_cliente", as_index=False)
                        .agg(
                            razao_social=("razao_social", "first"),
                            total_disparos=("disparos", "sum"),
                        )
                        .sort_values("total_disparos", ascending=False)
                    )
                    resumo_clientes["rotulo"] = resumo_clientes.apply(
                        lambda linha: (
                            f"{linha['razao_social']} · {linha['chave_cliente']}"
                            if pd.notna(linha["razao_social"])
                            and str(linha["razao_social"]).strip()
                            else str(linha["chave_cliente"])
                        ),
                        axis=1,
                    )
                    rotulos_clientes = dict(
                        zip(resumo_clientes["chave_cliente"], resumo_clientes["rotulo"])
                    )
                    clientes_selecionados = st.multiselect(
                        "Clientes para comparar",
                        options=resumo_clientes["chave_cliente"].tolist(),
                        default=[],
                        format_func=lambda chave: rotulos_clientes.get(
                            chave, str(chave)
                        ),
                        key="acompanhamento_clientes",
                    )
                    if clientes_selecionados:
                        clientes_grafico = clientes_selecionados
                    else:
                        clientes_grafico = (
                            resumo_clientes["chave_cliente"].head(5).tolist()
                        )
                        st.info(
                            "Nenhum cliente selecionado; exibindo os cinco com "
                            "maior volume no período."
                        )

                    dados_clientes_grafico = dados_clientes.loc[
                        dados_clientes["chave_cliente"].isin(clientes_grafico)
                    ].copy()
                    dados_clientes_grafico["cliente"] = (
                        dados_clientes_grafico["chave_cliente"].map(rotulos_clientes)
                    )
                    serie_clientes = preparar_serie_diaria(
                        dados_clientes_grafico,
                        "cliente",
                        [rotulos_clientes[chave] for chave in clientes_grafico],
                        data_inicio,
                        data_fim,
                    )
                    grafico_clientes_diario = px.line(
                        serie_clientes,
                        x="dia",
                        y="disparos",
                        color="serie",
                        markers=True,
                        labels={
                            "dia": "Dia",
                            "disparos": "Disparos",
                            "serie": "Cliente",
                        },
                    )
                    grafico_clientes_diario.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font={"family": "system-ui, sans-serif", "color": "#f1f3f5"},
                        margin={"l": 8, "r": 16, "t": 12, "b": 8},
                        hovermode="x unified",
                        legend={"orientation": "h", "y": 1.08, "x": 0},
                        xaxis={"title": "", "tickformat": "%d/%m", "showgrid": False},
                        yaxis={
                            "title": "Disparos",
                            "rangemode": "tozero",
                            "showgrid": True,
                            "gridcolor": "#30353d",
                        },
                    )
                    grafico_clientes_diario.update_traces(
                        line={"width": 2},
                        marker={"size": 6},
                    )
                    st.plotly_chart(grafico_clientes_diario, width="stretch")

with tab_sensores:
    st.subheader("Relatório de sensores")
    dados_sensores = obter_relatorio_sensores()
    if dados_sensores.empty or dados_sensores["snapshot_id"].isna().all():
        st.info("O coletor ainda não salvou um relatório de sensores.")
    else:
        snapshots = dados_sensores.drop_duplicates("snapshot_id")
        dados_sensores = dados_sensores.loc[dados_sensores["id"].notna()].copy()
        inicio_relatorio = pd.to_datetime(snapshots["period_start"]).min().strftime(
            "%d/%m/%Y"
        )
        fim_relatorio = pd.to_datetime(snapshots["period_end"]).max().strftime(
            "%d/%m/%Y"
        )
        ultima_carga = pd.to_datetime(snapshots["collected_at"]).max().strftime(
            "%d/%m/%Y às %H:%M"
        )
        st.caption(
            f"Período coberto: {inicio_relatorio} a {fim_relatorio} · "
            f"{len(snapshots)} snapshots · última carga: {ultima_carga}"
        )
        st.info(
            "O filtro de hora usa os registros de analise.hora_cheia. Como os dados "
            "de sensor são agregados por dia e não trazem o horário individual, "
            "os sensores exibidos são uma associação aproximada aos contratos com "
            "análise naquela hora."
        )

        periodos_analise_sensores = obter_periodos_analise_sensores()
        if periodos_analise_sensores.empty:
            dados_sensores = dados_sensores.iloc[0:0].copy()
            st.info("Não há datas e horários de análise relacionados a sensores.")
        else:
            periodos_analise_sensores["dia"] = pd.to_datetime(
                periodos_analise_sensores["dia"]
            ).dt.date
            datas_analise_disponiveis = sorted(
                periodos_analise_sensores["dia"].unique()
            )
            col_data_analise, col_hora_analise = st.columns(2)
            with col_data_analise:
                data_analise_selecionada = st.date_input(
                    "Data da análise",
                    value=datas_analise_disponiveis[-1],
                    min_value=datas_analise_disponiveis[0],
                    max_value=datas_analise_disponiveis[-1],
                    key="sensores_data_analise",
                )
            horas_analise_disponiveis = sorted(
                periodos_analise_sensores.loc[
                    periodos_analise_sensores["dia"]
                    == data_analise_selecionada,
                    "hora_cheia",
                ]
                .dropna()
                .astype(int)
                .unique()
            )
            if not horas_analise_disponiveis:
                dados_sensores = dados_sensores.iloc[0:0].copy()
                st.info("Não há análise relacionada a sensores nesta data.")
            else:
                with col_hora_analise:
                    hora_analise_selecionada = st.selectbox(
                        "Hora da análise",
                        options=horas_analise_disponiveis,
                        format_func=lambda hora: f"{hora:02d}:00–{hora + 1:02d}:00",
                        key="sensores_hora_analise",
                    )

                contratos_na_hora = obter_contratos_analise_sensores(
                    data_analise_selecionada,
                    int(hora_analise_selecionada),
                )
                intervalo_hora_analise = (
                    f"{hora_analise_selecionada:02d}:00–"
                    f"{(hora_analise_selecionada + 1) % 24:02d}:00"
                )
                if contratos_na_hora.empty:
                    dados_sensores = dados_sensores.iloc[0:0].copy()
                else:
                    dados_sensores["_data_analise"] = pd.to_datetime(
                        dados_sensores["data"], errors="coerce"
                    ).dt.date
                    dados_sensores["_numero_analise"] = pd.to_numeric(
                        dados_sensores["num_contrato"], errors="coerce"
                    ).astype("Int64")
                    dados_sensores["_departamento_analise"] = (
                        dados_sensores["departamento"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .str.upper()
                    )
                    dados_sensores["_estado_analise"] = (
                        dados_sensores["estado"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .str.upper()
                    )
                    contratos_na_hora["_numero_analise"] = pd.to_numeric(
                        contratos_na_hora["num_contrato"], errors="coerce"
                    ).astype("Int64")
                    chaves_contratos = set(
                        contratos_na_hora[
                            [
                                "_numero_analise",
                                "departamento",
                                "estado",
                            ]
                        ]
                        .itertuples(index=False, name=None)
                    )
                    chaves_sensores = pd.Series(
                        list(
                            zip(
                                dados_sensores["_numero_analise"],
                                dados_sensores["_departamento_analise"],
                                dados_sensores["_estado_analise"],
                            )
                        ),
                        index=dados_sensores.index,
                    )
                    selecionados_na_hora = chaves_sensores.isin(chaves_contratos)
                    dados_sensores = dados_sensores.loc[
                        (dados_sensores["_data_analise"] == data_analise_selecionada)
                        & selecionados_na_hora
                    ].drop(
                        columns=[
                            "_data_analise",
                            "_numero_analise",
                            "_departamento_analise",
                            "_estado_analise",
                        ]
                    )
                    st.caption(
                        f"Análise: {data_analise_selecionada:%d/%m/%Y} · "
                        f"{intervalo_hora_analise}"
                    )
                    dados_sensores["hora_analise"] = intervalo_hora_analise

        if dados_sensores.empty:
            st.info("Não há contratos de sensores para a data e hora selecionadas.")
        else:
            col_filtro_filial, col_filtro_depto, col_filtro_modelo = st.columns(3)
            filiais_sensores = sorted(
                dados_sensores["empresa"].dropna().unique().tolist()
            )
            departamentos_sensores = sorted(
                dados_sensores["departamento"].dropna().unique().tolist()
            )
            modelos_sensores = sorted(
                dados_sensores["modelo_sensor"].dropna().unique().tolist()
            )
            with col_filtro_filial:
                filiais_sensor_selecionadas = st.multiselect(
                    "Filiais do relatório",
                    options=filiais_sensores,
                    default=filiais_sensores,
                    key="sensores_filiais",
                )
            with col_filtro_depto:
                departamentos_sensor_selecionados = st.multiselect(
                    "Departamentos do relatório",
                    options=departamentos_sensores,
                    default=departamentos_sensores,
                    key="sensores_departamentos",
                )
            with col_filtro_modelo:
                modelos_sensor_selecionados = st.multiselect(
                    "Modelos de sensor",
                    options=modelos_sensores,
                    default=modelos_sensores,
                    key="sensores_modelos",
                )

            busca_sensor = st.text_input(
                "Buscar cliente, código ou número do contrato",
                key="sensores_busca",
            ).strip()
            mascara_sensores = (
                dados_sensores["empresa"].isin(filiais_sensor_selecionadas)
                & dados_sensores["departamento"].isin(
                    departamentos_sensor_selecionados
                )
                & dados_sensores["modelo_sensor"].isin(modelos_sensor_selecionados)
            )
            if busca_sensor:
                corresponde_busca = pd.Series(
                    False, index=dados_sensores.index, dtype=bool
                )
                for coluna_busca in (
                    "razao_social",
                    "cod_contrato",
                    "num_contrato",
                ):
                    corresponde_busca |= dados_sensores[coluna_busca].astype(
                        "string"
                    ).str.contains(busca_sensor, case=False, regex=False, na=False)
                mascara_sensores &= corresponde_busca

            sensores_filtrados = dados_sensores.loc[mascara_sensores].copy()
            if sensores_filtrados.empty:
                st.info("Nenhum contrato corresponde aos filtros selecionados.")
            else:
                total_registros_sensor = len(sensores_filtrados)
                total_clientes_sensor = sensores_filtrados["razao_social"].nunique()
                total_mensagens_api = int(
                    pd.to_numeric(
                        sensores_filtrados["message_count"], errors="coerce"
                    )
                    .fillna(0)
                    .sum()
                )
                metrica_contratos, metrica_clientes, metrica_mensagens = st.columns(3)
                metrica_contratos.metric(
                    "Registros de contrato/dia", f"{total_registros_sensor:,}"
                )
                metrica_clientes.metric(
                    "Clientes identificados", f"{total_clientes_sensor:,}"
                )
                metrica_mensagens.metric(
                    "Mensagens no período · API", f"{total_mensagens_api:,}"
                )

                contratos_por_modelo = (
                    sensores_filtrados.groupby("modelo_sensor", as_index=False)
                    .size()
                    .rename(columns={"size": "REGISTROS"})
                    .sort_values("REGISTROS", ascending=False)
                )
                zonas_principais = (
                    sensores_filtrados.dropna(subset=["zona_disparos"])
                    .groupby("zona_disparos", as_index=False)
                    .agg(
                        CONTAGEM_REPORTADA=("disparos", "sum"),
                        REGISTROS=("num_contrato", "count"),
                    )
                    .sort_values("CONTAGEM_REPORTADA", ascending=False)
                    .head(10)
                )
                grafico_modelos, grafico_zonas = st.columns(2)
                with grafico_modelos:
                    st.subheader("Registros por modelo")
                    st.plotly_chart(
                        px.bar(
                            contratos_por_modelo,
                            x="modelo_sensor",
                            y="REGISTROS",
                            labels={
                                "modelo_sensor": "Modelo classificado",
                                "REGISTROS": "Registros",
                            },
                            color_discrete_sequence=["#83aaff"],
                        ),
                        width="stretch",
                    )
                with grafico_zonas:
                    st.subheader("Zonas principais")
                    if zonas_principais.empty:
                        st.info("Não há descrições de zona nesta seleção.")
                    else:
                        st.plotly_chart(
                            px.bar(
                                zonas_principais.sort_values(
                                    "CONTAGEM_REPORTADA"
                                ),
                                x="CONTAGEM_REPORTADA",
                                y="zona_disparos",
                                orientation="h",
                                labels={
                                    "zona_disparos": "Zona",
                                    "CONTAGEM_REPORTADA": "Contagem informada",
                                },
                                hover_data={"REGISTROS": True},
                                color_discrete_sequence=["#83aaff"],
                            ),
                            width="stretch",
                        )
                st.caption(
                    "A classificação do modelo é estimada pelo texto da zona. "
                    "A contagem por zona usa `triggerCount` quando disponível e "
                    "`messageCount` como alternativa; não representa necessariamente "
                    "o total de disparos de todos os sensores do contrato."
                )

                tabela_sensores = sensores_filtrados.rename(
                    columns={
                        "razao_social": "CLIENTE",
                        "cod_contrato": "CÓDIGO",
                        "num_contrato": "CONTRATO",
                        "data": "DATA",
                        "hora_analise": "HORA DA ANÁLISE",
                        "empresa": "FILIAL",
                        "departamento": "DEPARTAMENTO",
                        "disparos": "CONTAGEM REPORTADA",
                        "message_count": "MENSAGENS API",
                        "zona_disparos": "ZONA PRINCIPAL",
                        "modelo_sensor": "MODELO",
                        "estado": "UF",
                        "department_mapping_confidence": "CONFIANÇA DEPARTAMENTO",
                    }
                )
                colunas_tabela = [
                    "CLIENTE",
                    "CÓDIGO",
                    "CONTRATO",
                    "DATA",
                    "HORA DA ANÁLISE",
                    "FILIAL",
                    "DEPARTAMENTO",
                    "MODELO",
                    "ZONA PRINCIPAL",
                    "CONTAGEM REPORTADA",
                    "MENSAGENS API",
                    "UF",
                    "CONFIANÇA DEPARTAMENTO",
                ]
                st.dataframe(
                    tabela_sensores[colunas_tabela],
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "CLIENTE": st.column_config.TextColumn(
                            "CLIENTE", width="large"
                        ),
                        "CÓDIGO": st.column_config.TextColumn(
                            "CÓDIGO", width="small"
                        ),
                        "CONTRATO": st.column_config.NumberColumn(
                            "CONTRATO", format="%d"
                        ),
                        "DATA": st.column_config.DateColumn(
                            "DATA", format="DD/MM/YYYY"
                        ),
                        "HORA DA ANÁLISE": st.column_config.TextColumn(
                            "HORA DA ANÁLISE", width="small"
                        ),
                        "FILIAL": st.column_config.TextColumn("FILIAL"),
                        "DEPARTAMENTO": st.column_config.TextColumn("DEPARTAMENTO"),
                        "MODELO": st.column_config.TextColumn("MODELO"),
                        "ZONA PRINCIPAL": st.column_config.TextColumn(
                            "ZONA PRINCIPAL", width="large"
                        ),
                        "CONTAGEM REPORTADA": st.column_config.NumberColumn(
                            "CONTAGEM REPORTADA", format="%d"
                        ),
                        "MENSAGENS API": st.column_config.NumberColumn(
                            "MENSAGENS API", format="%d"
                        ),
                        "UF": st.column_config.TextColumn("UF", width="small"),
                        "CONFIANÇA DEPARTAMENTO": st.column_config.TextColumn(
                            "MAPEAMENTO DO DEPARTAMENTO"
                        ),
                    },
                )
                st.download_button(
                    "Baixar relatório filtrado (CSV)",
                    data=tabela_sensores[colunas_tabela].to_csv(
                        index=False
                    ).encode("utf-8-sig"),
                    file_name="relatorio_sensores.csv",
                    mime="text/csv",
                    key="download_relatorio_sensores",
                )
