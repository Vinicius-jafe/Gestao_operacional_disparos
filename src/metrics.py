import pandas as pd

def calcular_metricas_filiais(
    df_filtrado: pd.DataFrame, 
    filiais_selecionadas: list, 
    dict_carteiras: dict, 
    dias_decorridos: int, 
    dias_totais_mes: int, 
    modo_historico: bool
) -> pd.DataFrame:
    linhas = []

    contagem = df_filtrado.groupby("empresa")["id"].count().to_dict()
    
    for filial in filiais_selecionadas:
        clientes = dict_carteiras.get(filial, 0)
        disparos = contagem.get(filial, 0)
        
        # Define o multiplicador de teto baseado no tipo/nome
        if "REDES" in filial.upper():
            fator_teto = 3.54999
        elif "TOTEN" in filial.upper():
            fator_teto = 10.0
        elif "SMART P" in filial.upper():
            fator_teto = 11.0
        elif "DGP" in filial.upper() or "EPA" in filial.upper() or "BH" in filial.upper():
            fator_teto = 2.0
        elif "ARAUJO" in filial.upper():
            fator_teto = 6.89
        else:
            fator_teto = 1.5499  # Padrão Smart Alarm
        
        if modo_historico:
            media_dia = disparos / dias_decorridos if dias_decorridos > 0 else 0.0
            prev_fechamento = disparos
            taxa_atual = round(disparos / clientes, 2) if clientes > 0 else 0.0
            taxa_prev = taxa_atual
        else:
            media_dia = disparos / dias_decorridos if dias_decorridos > 0 else 0.0
            prev_fechamento = int(round(media_dia * dias_totais_mes))
            taxa_atual = round(disparos / clientes, 2) if clientes > 0 else 0.0
            taxa_prev = round((disparos / clientes) / dias_decorridos * dias_totais_mes, 2) if (clientes > 0 and dias_decorridos > 0) else 0.0
            
        teto = int(round(clientes * fator_teto))
        saldo = prev_fechamento - teto  # Fórmula exata do Excel: =PREVISAO - TETO
        
        linhas.append({
            "FILIAIS": filial,
            "CLIENTES": clientes,
            "DISPAROS": disparos,
            "MEDIA": round(media_dia, 1),
            "PREVISAO": prev_fechamento,
            "TETO": teto,
            "SALDO": saldo,
            "TAXA ATUAL": taxa_atual,
            "TAXA PREV": taxa_prev,
            "STATUS": "Dentro da Meta" if taxa_prev <= round(fator_teto, 1) else "Fora da Meta"
        })
        
    df_res = pd.DataFrame(linhas)
    if not df_res.empty:
        df_res = df_res.sort_values(by="TAXA PREV", ascending=False)
    return df_res


def processar_reincidencia_clientes(df: pd.DataFrame, df_tratativas: pd.DataFrame = None) -> pd.DataFrame:
    """
    Agrupa exclusivamente pela CHAVE_CLIENTE (contrato + central ERP já unificados).
    Calcula a Curva de Pareto 80/20 e vincula a tratativa única do mês.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "CHAVE_CLIENTE", "RAZAO_SOCIAL", "EMPRESA", "DEPARTAMENTO",
            "TOTAL_DISPAROS", "DIAS_DISTINTOS", "CRITICIDADE_PARETO", "STATUS_TRATATIVA",
            "RESPONSAVEL", "OBSERVACAO", "DATA_ATUALIZACAO"
        ])

    # Agrupamento estrito pela chave única
    grp = df.groupby("chave_cliente", as_index=False).agg(
        RAZAO_SOCIAL=("razao_social", "first"),
        EMPRESA=("empresa", "first"),
        DEPARTAMENTO=("departamento", "first"),
        TOTAL_DISPAROS=("id", "count"),
        DIAS_DISTINTOS=("data_evento", "nunique")
    )

    # Ordena por volume decrescente para cálculo exato da Curva 80/20 de Pareto
    grp = grp.sort_values(by="TOTAL_DISPAROS", ascending=False).reset_index(drop=True)
    
    total_acumulado = grp["TOTAL_DISPAROS"].sum()
    if total_acumulado > 0:
        grp["soma_acumulada"] = grp["TOTAL_DISPAROS"].cumsum()
        grp["pct_acumulado"] = grp["soma_acumulada"] / total_acumulado
        grp["CRITICIDADE_PARETO"] = grp["pct_acumulado"].apply(
            lambda x: "🟥 Crítico" if x <= 0.80 else "Regular"
        )
        grp.drop(columns=["soma_acumulada", "pct_acumulado"], inplace=True)
    else:
        grp["CRITICIDADE_PARETO"] = "Regular"

    # Merge direto com a tabela tratativas_reincidencia pela chave única
    if df_tratativas is not None and not df_tratativas.empty:
        df_trat_dedup = df_tratativas.drop_duplicates(subset=["chave_cliente"])
        grp = grp.merge(df_trat_dedup, on="chave_cliente", how="left")
    else:
        grp["status"] = "Pendente / Triagem"
        grp["responsavel"] = ""
        grp["observacao"] = ""
        grp["data_atualizacao"] = None

    grp.rename(columns={
        "chave_cliente": "CHAVE_CLIENTE",
        "status": "STATUS_TRATATIVA",
        "responsavel": "RESPONSAVEL",
        "observacao": "OBSERVACAO",
        "data_atualizacao": "DATA_ATUALIZACAO"
    }, inplace=True)

    grp["STATUS_TRATATIVA"] = grp["STATUS_TRATATIVA"].fillna("Pendente / Triagem")
    grp["RESPONSAVEL"] = grp["RESPONSAVEL"].fillna("")
    grp["OBSERVACAO"] = grp["OBSERVACAO"].fillna("")

    return grp
