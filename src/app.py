import calendar
from datetime import date, datetime, timedelta
import io
import pandas as pd
import plotly.express as px
import streamlit as st

from src.database import (
    verificar_integridade_banco,
    sincronizar_planilhas,
    carregar_eventos,
    obter_carteira_df,
    obter_carteira_filiais_dict,
    salvar_carteira,
    carregar_tratativas,
    salvar_tratativa
)
from src.metrics import calcular_metricas_filiais, processar_reincidencia_clientes

st.set_page_config(page_title="Gestão de Disparos Emive", layout="wide")

# ================= CARGA E INTEGRIDADE =================
try:
    verificar_integridade_banco()
    sincronizar_planilhas()
except Exception as e:
    st.error(f"❌ Erro ao conectar ou inicializar o banco de dados: {e}")
    st.stop()

@st.cache_data(ttl=60)
def obter_dados_painel():
    return carregar_eventos(), obter_carteira_df(), obter_carteira_filiais_dict()

df, df_carteira, dict_carteiras = obter_dados_painel()

if df is None or df.empty:
    st.warning(" Banco de dados conectado, mas sem eventos gravados.")
    if st.button(" Sincronizar Novamente"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

# ================= DEFINIÇÕES DE TEMPORALIDADE =================
hoje = date.today()
ontem = hoje - timedelta(days=1)
mes_atual_str = hoje.strftime("%Y-%m")

# ================= BARRA LATERAL (CONFIGURAÇÕES GLOBAIS) =================
st.sidebar.header(" Modo de Operação")

modo_visao = st.sidebar.radio(
    "Selecione a Visão Desejada:",
    [
        " Fechamento Consolidado (D-1 & Metas)", 
        " Plantão Hora a Hora (Hoje / Tempo Real)"
    ],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.header(" Filtros Gerais")

if st.sidebar.button(" Atualizar Dados do Banco"):
    st.cache_data.clear()
    st.rerun()

todas_filiais_disponiveis = sorted(df["empresa"].dropna().unique().tolist())
filiais_carteira = df_carteira[df_carteira["tipo"] == "FILIAL"]["filial"].tolist() if not df_carteira.empty else []
todas_opcoes_filiais = sorted(list(set(todas_filiais_disponiveis + filiais_carteira)))

filiais_selecionadas = st.sidebar.multiselect(
    "Filtrar Filiais:", 
    options=todas_opcoes_filiais, 
    default=todas_opcoes_filiais
)

todos_deptos = sorted(df["departamento"].dropna().unique().tolist())
deptos_selecionados = st.sidebar.multiselect(
    "Filtrar Departamentos:", 
    options=todos_deptos, 
    default=todos_deptos
)

with st.sidebar.expander(" Ajustar Base da Carteira"):
    df_editado = st.data_editor(df_carteira, num_rows="dynamic", width="stretch")
    if st.button("Salvar Carteira"):
        salvar_carteira(df_editado)
        st.cache_data.clear()
        st.success("Carteira atualizada com sucesso.")
        st.rerun()

# Filtragem Global dos Dados Base
df_filtrado_global = df[
    (df["empresa"].isin(filiais_selecionadas)) &
    (df["departamento"].isin(deptos_selecionados))
].copy()

if df_filtrado_global.empty:
    st.info(" Nenhum registro encontrado para a combinação de filtros selecionada.")
    st.stop()


# ==============================================================================
# MODO 1: VISÃO DE FECHAMENTO CONSOLIDADO (D-1 E METAS)
# ==============================================================================
if modo_visao == " Fechamento Consolidado (D-1 & Metas)":
    
    st.title(" Gestão de Metas e Fechamento Consolidado (D-1)")
    
    col_sel_mes, col_info_periodo = st.columns([2, 3])
    
    meses_disponiveis = sorted(df_filtrado_global["ano_mes"].dropna().unique().tolist(), reverse=True)
    opcoes_competencia = ["Todos os Meses (Visao Historica)"] + meses_disponiveis
    
    mes_selecionado = col_sel_mes.selectbox(
        "Competência (Mês/Ano):", 
        opcoes_competencia, 
        index=1 if len(opcoes_competencia) > 1 else 0
    )

    if mes_selecionado == "Todos os Meses (Visao Historica)":
        df_fechamento = df_filtrado_global[df_filtrado_global["data_evento"] <= ontem].copy()
        modo_historico = True
        dias_decorridos = max(df_fechamento["data_evento"].nunique(), 1)
        dias_totais_mes = dias_decorridos
        texto_periodo = f"Consolidado Histórico Geral (até {ontem.strftime('%d/%m/%Y')})"
    else:
        df_mes = df_filtrado_global[df_filtrado_global["ano_mes"] == mes_selecionado].copy()
        ano_sel, mes_sel = map(int, mes_selecionado.split("-"))
        dias_totais_mes = calendar.monthrange(ano_sel, mes_sel)[1]
        
        if mes_selecionado == mes_atual_str:
            # Mês em andamento: usa estritamente até ontem (D-1)
            df_fechamento = df_mes[df_mes["data_evento"] <= ontem].copy()
            modo_historico = False
            dias_decorridos = max(ontem.day, 1) if hoje.month == mes_sel else dias_totais_mes
            texto_periodo = f"Mês em Andamento ({mes_selecionado}) - Dias Fechados: Dia 1 até Dia {dias_decorridos} de {dias_totais_mes}"
        else:
            # Mês anterior completamente fechado
            df_fechamento = df_mes.copy()
            modo_historico = False
            dias_decorridos = dias_totais_mes
            texto_periodo = f"Mês Fechado ({mes_selecionado}) - Total de {dias_totais_mes} dias"

    col_info_periodo.info(f" **Período de Análise:** {texto_periodo}")

    # Segmentação Smart vs Outros
    df_smart_fechamento = df_fechamento[df_fechamento["departamento"].str.upper().str.contains("SMART", na=False)]
    df_outros_fechamento = df_fechamento[~df_fechamento["departamento"].str.upper().str.contains("SMART", na=False)]

    base_clientes_smart = sum(dict_carteiras.get(f, 0) for f in filiais_selecionadas if f in filiais_carteira)
    total_disparos_smart = len(df_smart_fechamento)
    total_disparos_geral = len(df_fechamento)

    media_smart_dia = total_disparos_smart / dias_decorridos if dias_decorridos > 0 else 0.0
    taxa_smart_real = round(total_disparos_smart / base_clientes_smart, 2) if base_clientes_smart > 0 else 0.0
    taxa_smart_prev = round((media_smart_dia * dias_totais_mes) / base_clientes_smart, 2) if base_clientes_smart > 0 else 0.0

    # Cards Principais
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Base Clientes SMART", f"{base_clientes_smart:,}")
    c2.metric("Disparos SMART (D-1)", f"{total_disparos_smart:,}")
    c3.metric("Total Geral (Com Cabeado)", f"{total_disparos_geral:,}")
    c4.metric("Taxa Real SMART", f"{taxa_smart_real:.2f}")
    c5.metric(
        "Taxa Prevista SMART",
        f"{taxa_smart_prev:.2f}",
        delta=f"{round(taxa_smart_prev - 1.55, 2)} vs Meta 1.55" if not modo_historico else None,
        delta_color="inverse"
    )

    st.markdown("---")

    # Sub-abas da visão de Fechamento
    tab_filiais, tab_tratativas = st.tabs([
        " Metas & Projeções por Filial", 
        " Central de Tratativas & Pareto (Top 80%)"
    ])

    with tab_filiais:
        st.subheader("Tabela de Metas e Saldos por Filial (Smart Alarm)")
        tabela_filiais_calc = calcular_metricas_filiais(
            df_smart_fechamento, filiais_selecionadas, dict_carteiras, 
            dias_decorridos, dias_totais_mes, modo_historico
        )
        st.dataframe(tabela_filiais_calc, width="stretch")

    with tab_tratativas:
        mes_consulta = mes_selecionado if mes_selecionado != "Todos os Meses (Visao Historica)" else mes_atual_str
        df_tratativas = carregar_tratativas(mes_consulta)

        clientes_smart = processar_reincidencia_clientes(df_smart_fechamento, df_tratativas)
        clientes_outros = processar_reincidencia_clientes(df_outros_fechamento, df_tratativas)
        clientes_geral = processar_reincidencia_clientes(df_fechamento, df_tratativas)

        with st.expander(" Registrar / Atualizar Tratativa de Cliente", expanded=False):
            opcoes_clientes = clientes_geral.apply(
                lambda r: f"{r['CHAVE_CLIENTE']} | {r['RAZAO_SOCIAL']} ({r['TOTAL_DISPAROS']} disp) - [{r['CRITICIDADE_PARETO']}]", axis=1
            ).tolist() if not clientes_geral.empty else []

            if opcoes_clientes:
                col_c1, col_c2 = st.columns([2, 1])
                cliente_sel_str = col_c1.selectbox("Selecione o Cliente:", opcoes_clientes)
                chave_selecionada = cliente_sel_str.split(" | ")[0].strip()

                dados_cliente = clientes_geral[clientes_geral["CHAVE_CLIENTE"] == chave_selecionada].iloc[0]

                col_f1, col_f2, col_f3 = st.columns(3)
                lista_status = [
                    "Pendente / Triagem",
                    "Contato com Cliente Realizado",
                    "Ordem de Serviço (OS) de Manutenção Aberta",
                    "Mau Uso Orientado",
                    "Concluído / Resolvido"
                ]
                status_atual = dados_cliente["STATUS_TRATATIVA"] if dados_cliente["STATUS_TRATATIVA"] in lista_status else "Pendente / Triagem"
                idx_status = lista_status.index(status_atual)

                novo_status = col_f1.selectbox("Status Operacional:", lista_status, index=idx_status)
                responsavel_val = col_f2.text_input("Operador / Responsável:", value=dados_cliente["RESPONSAVEL"] or "")
                obs_val = col_f3.text_area("Anotação / Nº da OS / Motivo:", value=dados_cliente["OBSERVACAO"] or "", height=80)

                if st.button(" Gravar Tratativa", type="primary"):
                    salvar_tratativa(
                        chave_cliente=chave_selecionada,
                        ano_mes=mes_consulta,
                        status=novo_status,
                        responsavel=responsavel_val.strip(),
                        observacao=obs_val.strip()
                    )
                    st.cache_data.clear()
                    st.success(f"Tratativa de {chave_selecionada} salva!")
                    st.rerun()

        def renderizar_tabela_e_exportacao(dataframe, nome_aba):
            st.dataframe(dataframe, width="stretch")
            if not dataframe.empty:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    dataframe.to_excel(writer, index=False, sheet_name=nome_aba[:31])
                st.download_button(
                    label=f" Baixar Relatório {nome_aba} (Excel)",
                    data=buffer.getvalue(),
                    file_name=f"relatorio_{nome_aba.lower()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"btn_dl_{nome_aba}"
                )

        subtab_smart, subtab_outros, subtab_geral = st.tabs([
            f"Smart Alarm ({len(clientes_smart)})",
            f"Convencional / Outros ({len(clientes_outros)})",
            f"Todos os Clientes ({len(clientes_geral)})"
        ])

        with subtab_smart:
            renderizar_tabela_e_exportacao(clientes_smart, "Smart_Alarm")

        with subtab_outros:
            renderizar_tabela_e_exportacao(clientes_outros, "Outros_Contratos")

        with subtab_geral:
            renderizar_tabela_e_exportacao(clientes_geral, "Geral")


# ==============================================================================
# MODO 2: PLANTÃO HORA A HORA (HOJE / TEMPO REAL)
# ==============================================================================
else:
    st.title(" Monitoramento de Plantão Hora a Hora (Hoje)")
    
    # Filtra estritamente a data atual (D-0)
    df_hoje = df_filtrado_global[df_filtrado_global["data_evento"] == hoje].copy()

    if df_hoje.empty:
        st.warning(f" Nenhum evento registrado no banco para a data de hoje ({hoje.strftime('%d/%m/%Y')}).")
        st.info("Assim que o coletor horário da API rodar ou uma nova planilha for inserida, os dados aparecerão aqui em tempo real.")
    else:
        disp_hoje_total = len(df_hoje)
        disp_hoje_smart = len(df_hoje[df_hoje["departamento"].str.upper().str.contains("SMART", na=False)])
        contratos_hoje = df_hoje["chave_cliente"].nunique()
        ultima_hora = df_hoje["hora_int"].max()

        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Total de Disparos Hoje", f"{disp_hoje_total:,}")
        h2.metric("Disparos Smart Alarm Hoje", f"{disp_hoje_smart:,}")
        h3.metric("Contratos com Disparo Hoje", f"{contratos_hoje:,}")
        h4.metric("Última Hora com Registro", f"{ultima_hora:02d}:00")

        st.markdown("---")

        col_g_esq, col_g_dir = st.columns([3, 2])

        with col_g_esq:
            st.subheader("Curva de Disparos de Hoje (Clique na barra para detalhar)")
            disp_hora_hoje = df_hoje.groupby("hora_int")["id"].count().reset_index()
            disp_hora_hoje.rename(columns={"id": "total_disparos"}, inplace=True)

            fig_hoje = px.bar(
                disp_hora_hoje,
                x="hora_int",
                y="total_disparos",
                labels={"hora_int": "Hora do Dia (0-23h)", "total_disparos": "Disparos"},
                color="total_disparos",
                color_continuous_scale="Reds",
                text="total_disparos"
            )
            fig_hoje.update_layout(
                xaxis=dict(tickmode="linear", tick0=0, dtick=1),
                clickmode="event+select",
                dragmode="select",
                margin=dict(l=10, r=10, t=30, b=10)
            )
            fig_hoje.update_traces(textposition="outside")

            evento_hora_hoje = st.plotly_chart(
                fig_hoje, 
                width="stretch", 
                on_select="rerun", 
                selection_mode="points",
                key="grafico_hoje_interativo"
            )

        with col_g_dir:
            st.subheader("Distribuição por Departamento (Hoje)")
            disp_depto_hoje = df_hoje.groupby("departamento")["id"].count().reset_index()
            fig_pie_hoje = px.pie(disp_depto_hoje, names="departamento", values="id", hole=0.4)
            fig_pie_hoje.update_layout(margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_pie_hoje, width="stretch")

        st.markdown("---")

        # Captura do clique ou seleção manual da hora
        hora_clicada_hoje = None
        if evento_hora_hoje and "selection" in evento_hora_hoje and "points" in evento_hora_hoje["selection"]:
            pontos = evento_hora_hoje["selection"]["points"]
            if pontos:
                hora_clicada_hoje = pontos[0].get("x")

        with st.container():
            if hora_clicada_hoje is not None:
                h_filtro = int(hora_clicada_hoje)
                st.info(f" **Detalhamento da hora clicada:** Faixa das **{h_filtro:02d}:00 até {h_filtro:02d}:59** de Hoje")
            else:
                horas_disponiveis = sorted(df_hoje["hora_int"].dropna().unique().astype(int).tolist())
                opcoes_h = ["Todas as Horas de Hoje"] + [f"{h:02d}:00" for h in horas_disponiveis]
                h_manual = st.selectbox("Ou selecione uma hora específica de hoje para detalhar:", opcoes_h, index=0)
                h_filtro = int(h_manual.split(":")[0]) if h_manual != "Todas as Horas de Hoje" else None

            if h_filtro is not None:
                df_detalhe_hoje = df_hoje[df_hoje["hora_int"] == h_filtro]
            else:
                df_detalhe_hoje = df_hoje.copy()

            clientes_ranking_hoje = df_detalhe_hoje.groupby("chave_cliente", as_index=False).agg(
                RAZAO_SOCIAL=("razao_social", "first"),
                EMPRESA=("empresa", "first"),
                DEPARTAMENTO=("departamento", "first"),
                DISPAROS_NO_PERIODO=("id", "count"),
                PRIMEIRO_DISPARO=("hora_evento", "min"),
                ULTIMO_DISPARO=("hora_evento", "max")
            ).sort_values(by="DISPAROS_NO_PERIODO", ascending=False).reset_index(drop=True)

            txt_titulo = f"às **{h_filtro:02d}h**" if h_filtro is not None else "no **acumulado do dia de hoje**"
            st.subheader(f" Ranking de Clientes com Disparos {txt_titulo} ({len(clientes_ranking_hoje)} contratos)")
            st.dataframe(clientes_ranking_hoje, width="stretch")