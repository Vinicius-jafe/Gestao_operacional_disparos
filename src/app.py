import calendar
from datetime import date, time, timedelta
import io

import pandas as pd
import plotly.express as px
import streamlit as st

from src.database import (
    carregar_eventos,
    normalizar_nome_filial,
    obter_carteira_df,
    obter_carteira_filiais_dict,
    salvar_carteira,
    sincronizar_planilhas,
    verificar_integridade_banco,
)
from src.metrics import (
    calcular_distribuicao_horaria,
    calcular_distribuicao_periodos,
    calcular_metricas_filiais,
    calcular_recorrencia_complementar,
    calcular_taxa_por_carteira,
    comparar_disparos_mensais,
    detectar_limitador,
    detectar_possivel_mau_uso,
    processar_reincidencia_clientes,
)
from src.presentation import incluir_cod_contrato


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

tab_visao, tab_pareto, tab_plantao = st.tabs(
    ["Visão geral de filiais", "Reincidência e Pareto", "Monitoramento"]
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
    st.subheader("Monitoramento por dia e horário")

    datas_eventos = sorted(
        pd.to_datetime(df_filtrado["data_evento"], errors="coerce")
        .dropna()
        .dt.date.unique()
    )

    if not datas_eventos:
        st.info("Não há datas de eventos disponíveis para os filtros selecionados.")
    else:
        data_padrao = hoje if hoje in datas_eventos else datas_eventos[-1]
        coluna_data, coluna_inicio, coluna_fim = st.columns(3)
        with coluna_data:
            data_selecionada = st.date_input(
                "Dia dos eventos",
                value=data_padrao,
                min_value=datas_eventos[0],
                max_value=datas_eventos[-1],
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
                df_filtrado["data_evento"], errors="coerce"
            ).dt.date
            minutos_do_dia = pd.to_numeric(
                df_filtrado["minuto_do_dia"], errors="coerce"
            )
            df_faixa = df_filtrado[
                (datas_normalizadas == data_selecionada)
                & minutos_do_dia.between(
                    minutos_inicio, minutos_fim, inclusive="both"
                )
            ].copy()

            st.caption(
                f"{data_selecionada.strftime('%d/%m/%Y')} · "
                f"{horario_inicio.strftime('%H:%M')}–{horario_fim.strftime('%H:%M')}"
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

    with st.expander("Análises operacionais complementares", expanded=False):
        st.caption(
            "Distribuição por hora usa o período selecionado. Mau uso e limitador "
            "consideram todo o histórico e não incluem filtro temporal."
        )
        if df_fechamento.empty:
            st.info("Não há eventos no período selecionado.")
        else:
            eventos_sem_horario = pd.to_datetime(
                df_fechamento["dt_hora"], errors="coerce"
            ).isna().sum()
            distribuicao_horaria = calcular_distribuicao_horaria(df_fechamento)
            distribuicao_periodos = calcular_distribuicao_periodos(df_fechamento)
            if eventos_sem_horario:
                st.caption(
                    f"{eventos_sem_horario} evento(s) sem data/hora foram excluídos "
                    "da distribuição."
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
                        category_orders={"PERIODO": list(distribuicao_periodos["PERIODO"])},
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
