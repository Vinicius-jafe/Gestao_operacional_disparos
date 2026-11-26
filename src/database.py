import hashlib
import logging
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from sqlalchemy import bindparam, create_engine, event, text
from src.config import CARTEIRA_INICIAL_ESTRUTURADA, DB_URL, PASTA_DADOS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

engine = create_engine(DB_URL, pool_pre_ping=True)


@event.listens_for(engine, "before_cursor_execute")
def _iniciar_medicao_consulta(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("_perf_query_started", []).append(time.perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _finalizar_medicao_consulta(conn, cursor, statement, parameters, context, executemany):
    inicio = conn.info["_perf_query_started"].pop()
    conn.info["_perf_query_seconds"] = (
        conn.info.get("_perf_query_seconds", 0.0) + time.perf_counter() - inicio
    )


COLUNAS_EVENTOS = [
    "id",
    "contrato",
    "numero_contrato",
    "chave_cliente",
    "empresa",
    "razao_social",
    "departamento",
    "hora_evento",
    "dt_hora",
    "data_evento",
    "ano_mes",
    "hora_int",
    "minuto_do_dia",
    "final_de_semana",
]

COLUNAS_OBRIGATORIAS_EXCEL = ["Id", "Contrato", "Numero Contrato", "Hora evento"]
COLUNAS_ACOMPANHAMENTO_DIARIO = [
    "dia",
    "empresa",
    "chave_cliente",
    "razao_social",
    "disparos",
]


def _read_sql(
    consulta,
    conexao,
    *,
    nome: str,
    params: Optional[dict] = None,
) -> pd.DataFrame:
    inicio = time.perf_counter()
    info_conexao = getattr(conexao, "info", {})
    exec_antes = info_conexao.get("_perf_query_seconds", 0.0)
    if params is None:
        dataframe = pd.read_sql(consulta, conexao)
    else:
        dataframe = pd.read_sql(consulta, conexao, params=params)
    total_ms = (time.perf_counter() - inicio) * 1000
    exec_ms = max(
        0.0,
        (info_conexao.get("_perf_query_seconds", exec_antes) - exec_antes) * 1000,
    )
    transferencia_ms = max(0.0, total_ms - exec_ms)
    tamanho_bytes = int(dataframe.memory_usage(index=True, deep=True).sum())
    logger.info(
        "Desempenho DB [%s]: execucao=%.1f ms; fetch+DataFrame=%.1f ms; "
        "total=%.1f ms; linhas=%s; dataframe=%s bytes",
        nome,
        exec_ms,
        transferencia_ms,
        total_ms,
        len(dataframe),
        tamanho_bytes,
    )
    return dataframe


def normalizar_nome_filial(empresa: str, logradouro: str = "") -> str:
    """
    Normaliza a coluna Empresa mapeando diretamente para os nomes oficiais da carteira.
    Elimina dependência excessiva de logradouro/cidade.
    """
    emp = str(empresa or "").strip().upper()
    log = str(logradouro or "").strip().upper()

    # 1. Minas Gerais (Filiais do Interior e Matriz BH)
    if "GOV" in emp or "8322" in emp:
        return "F - GOV VALADARES"
    if "MONTES CLAROS" in emp or "8323" in emp:
        return "F - MONTES CLAROS"
    if "UBERLANDIA" in emp or "UBERLÂNDIA" in emp:
        return "F - UBERLANDIA"
    if "DIVIN" in emp:
        return "F - DIVINOPOLIS"
    if "IPATINGA" in emp:
        return "F - IPATINGA"
    if "UBA" in emp or "UBÁ" in emp or "8319" in emp:
        return "F - UBA"
    if "JUIZ DE FORA" in emp:
        return "F - JUIZ DE FORA"
    if emp in ["EMIVE", "SEMAX", "EMIVE PATRULHA"] or emp.startswith("F -"):
        return "F - BELO HORIZONTE"

    # 2. São Paulo e Sub-regiões
    if "CAMPINAS" in emp:
        return "FILIAL EMIVE CAMPINAS"
    if "TATUAPE" in emp or "TATUAPÉ" in emp or "8317" in emp:
        return "FILIAL EMIVE TATUAPE"
    if "SAO JOSE DOS CAMPOS" in emp or "SÃO JOSÉ DOS CAMPOS" in emp:
        return "FILIAL EMIVE SAO JOSE DOS CAMPOS"
    if "RIBEIRAO PRETO" in emp or "RIBEIRÃO PRETO" in emp:
        return "FILIAL EMIVE RIBEIRAO PRETO"
    if "PPU - SP" in emp or emp == "SP":
        if "BERRINI" in log:
            return "FILIAL EMIVE SP BERRINI"
        if "FARIA LIMA" in log:
            return "FILIAL EMIVE SP FARIA LIMA"
        if "SAO CAETANO" in log or "SÃO CAETANO" in log:
            return "FILIAL EMIVE SAO CAETANO DO SUL"
        return "FILIAL EMIVE SP BERRINI"  # Default para base SP Capital

    # 3. Filiais Nacionais (Mapeamento Direto por Palavra-Chave / Código)
    mapa_filiais = {
        "ARACAJU": "FILIAL EMIVE ARACAJU",
        "B.CAMBORUI": "FILIAL EMIVE BALNEARIO CAMBORIU",
        "BALNEARIO": "FILIAL EMIVE BALNEARIO CAMBORIU",
        "8296": "FILIAL EMIVE BALNEARIO CAMBORIU",
        "BELEM": "FILIAL EMIVE BELEM",
        "BELÉM": "FILIAL EMIVE BELEM",
        "8321": "FILIAL EMIVE BELEM",
        "CAMPINA GRANDE": "FILIAL EMIVE CAMPINA GRANDE",
        "8318": "FILIAL EMIVE CAMPINA GRANDE",
        "CAMPO GRANDE": "FILIAL EMIVE CAMPO GRANDE",
        "8291": "FILIAL EMIVE CAMPO GRANDE",
        "CAMPOS": "FILIAL EMIVE CAMPOS DOS GOYTACAZES",
        "8313": "FILIAL EMIVE CAMPOS DOS GOYTACAZES",
        "CARUARU": "FILIAL EMIVE CARUARU",
        "8310": "FILIAL EMIVE CARUARU",
        "CUIABA": "FILIAL EMIVE CUIABA",
        "CUIABÁ": "FILIAL EMIVE CUIABA",
        "8311": "FILIAL EMIVE CUIABA",
        "CWB": "FILIAL EMIVE CURITIBA",
        "CURITIBA": "FILIAL EMIVE CURITIBA",
        "FLORIANOPOLIS": "FILIAL EMIVE FLORIANOPOLIS",
        "FLORIANÓPOLIS": "FILIAL EMIVE FLORIANOPOLIS",
        "8315": "FILIAL EMIVE FLORIANOPOLIS",
        "FORTALEZA": "FILIAL EMIVE FORTALEZA",
        "PPU - CE": "FILIAL EMIVE FORTALEZA",
        "GOIANIA": "FILIAL EMIVE GOIANIA",
        "GOIÂNIA": "FILIAL EMIVE GOIANIA",
        "PPU - GO": "FILIAL EMIVE GOIANIA",
        "BRASILIA": "FILIAL EMIVE BRASILIA",
        "BRASÍLIA": "FILIAL EMIVE BRASILIA",
        "BSB": "FILIAL EMIVE BRASILIA",
        "JOAO PESSOA": "FILIAL EMIVE JOAO PESSOA",
        "JOÃO PESSOA": "FILIAL EMIVE JOAO PESSOA",
        "JPA": "FILIAL EMIVE JOAO PESSOA",
        "8297": "FILIAL EMIVE JOAO PESSOA",
        "JOINVILLE": "FILIAL EMIVE JOINVILLE",
        "8299": "FILIAL EMIVE JOINVILLE",
        "SNLN": "FILIAL EMIVE LINHARES",
        "LINHARES": "FILIAL EMIVE LINHARES",
        "8295": "FILIAL EMIVE LINHARES",
        "LONDRINA": "FILIAL EMIVE LONDRINA",
        "8316": "FILIAL EMIVE LONDRINA",
        "MCZ": "FILIAL EMIVE MACEIO",
        "MACEIO": "FILIAL EMIVE MACEIO",
        "MACEIÓ": "FILIAL EMIVE MACEIO",
        "8294": "FILIAL EMIVE MACEIO",
        "MAO": "FILIAL EMIVE MANAUS",
        "MANAUS": "FILIAL EMIVE MANAUS",
        "8293": "FILIAL EMIVE MANAUS",
        "NATAL": "FILIAL EMIVE NATAL",
        "8314": "FILIAL EMIVE NATAL",
        "NITEROI": "FILIAL EMIVE NITEROI",
        "NITERÓI": "FILIAL EMIVE NITEROI",
        "8325": "FILIAL EMIVE NITEROI",
        "PETROLINA": "FILIAL EMIVE PETROLINA",
        "8324": "FILIAL EMIVE PETROLINA",
        "PORTO ALEGRE": "FILIAL EMIVE PORTO ALEGRE",
        "PPU - RS": "FILIAL EMIVE PORTO ALEGRE",
        "PORTO VELHO": "FILIAL EMIVE PORTO VELHO",
        "8326": "FILIAL EMIVE PORTO VELHO",
        "RECIFE": "FILIAL EMIVE RECIFE",
        "PPU - PE": "FILIAL EMIVE RECIFE",
        "RIO DE JANEIRO": "FILIAL EMIVE RIO DE JANEIRO",
        "PPU - RJ": "FILIAL EMIVE RIO DE JANEIRO",
        "SSA": "FILIAL EMIVE SALVADOR",
        "SALVADOR": "FILIAL EMIVE SALVADOR",
        "8298": "FILIAL EMIVE SALVADOR",
        "FEIRA DE SANTANA": "FILIAL EMIVE FEIRA DE SANTANA",
        "SAO LUIZ": "FILIAL EMIVE SAO LUIZ",
        "SÃO LUÍS": "FILIAL EMIVE SAO LUIZ",
        "8320": "FILIAL EMIVE SAO LUIZ",
        "TERESINA": "FILIAL EMIVE TERESINA",
        "VITORIA": "FILIAL EMIVE VITORIA",
        "VITÓRIA": "FILIAL EMIVE VITORIA",
        "PPU - ES": "FILIAL EMIVE VITORIA",
    }

    for chave, nome_oficial in mapa_filiais.items():
        if chave in emp:
            return nome_oficial

    return emp

def verificar_integridade_banco() -> None:
    """Valida o schema PostgreSQL externo e carrega a carteira se ela estiver vazia."""
    colunas_esperadas = {
        "disparos_eventos": {
            "id",
            "contrato",
            "numero_contrato",
            "chave_cliente",
            "empresa",
            "razao_social",
            "departamento",
            "hora_evento",
            "dt_hora",
            "data_evento",
            "ano_mes",
            "hora_int",
            "minuto_do_dia",
            "final_de_semana",
        },
        "carteira_filiais": {"filial", "clientes", "tipo"},
        "arquivos_processados": {
            "nome_arquivo",
            "hash_sha256",
            "tamanho_bytes",
            "status",
            "linhas_lidas",
            "linhas_inseridas",
            "mensagem_erro",
            "data_processamento",
        },
        "analise": {
            "id",
            "id_providencia",
            "contrato",
            "numero_contrato",
            "empresa",
            "razao_social",
            "bairro",
            "cidade",
            "hora_evento",
            "departamento",
            "disparos",
            "dia",
            "hora",
            "hora_cheia",
            "dia_semana",
            "periodo",
            "mes",
            "estado",
            "possivel_padrao",
        },
        "alarm_report_snapshots": {
            "id",
            "period_start",
            "period_end",
            "collected_at",
            "page_size",
            "page_count",
            "total_item_count",
        },
        "disparos_sensor": {
            "id",
            "snapshot_id",
            "cod_contrato",
            "empresa",
            "razao_social",
            "num_contrato",
            "departamento",
            "department_id",
            "department_mapping_confidence",
            "disparos",
            "message_count",
            "zona_disparos",
            "data",
            "mes",
            "estado",
            "modelo_sensor",
        },
        "vw_analise_disp_sensor": {
            "id",
            "id_providencia",
            "contrato",
            "numero_contrato",
            "empresa",
            "razao_social",
            "departamento",
            "estado",
            "dia",
            "mes",
            "hora_cheia",
            "dia_semana",
            "periodo",
            "sensores_no_dia",
            "zona_referencia_dia",
            "total_disparos_sensor_dia",
        },
    }
    consulta_colunas = text("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name IN :table_names
    """).bindparams(bindparam("table_names", expanding=True))
    indices_esperados = {"idx_analise_dia_hora"}
    consulta_indices = text("""
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = current_schema()
          AND indexname IN :index_names
    """).bindparams(bindparam("index_names", expanding=True))

    with engine.begin() as conn:
        existentes = conn.execute(
            consulta_colunas,
            {"table_names": list(colunas_esperadas)},
        ).all()
        colunas_encontradas: Dict[str, set] = {}
        for tabela, coluna in existentes:
            colunas_encontradas.setdefault(tabela, set()).add(coluna)

        faltantes = {
            tabela: sorted(colunas - colunas_encontradas.get(tabela, set()))
            for tabela, colunas in colunas_esperadas.items()
            if colunas - colunas_encontradas.get(tabela, set())
        }
        if faltantes:
            detalhes = "; ".join(
                f"{tabela}: {', '.join(colunas)}"
                for tabela, colunas in sorted(faltantes.items())
            )
            raise RuntimeError(
                f"Schema PostgreSQL externo ausente ou incompleto ({detalhes})."
            )

        indices_existentes = {
            nome_indice
            for (nome_indice,) in conn.execute(
                consulta_indices,
                {"index_names": sorted(indices_esperados)},
            ).all()
        }
        indices_faltantes = indices_esperados - indices_existentes
        if indices_faltantes:
            raise RuntimeError(
                "Índices PostgreSQL ausentes ou incompletos "
                f"({', '.join(sorted(indices_faltantes))})."
            )

        total_carteira = conn.execute(text("SELECT COUNT(*) FROM carteira_filiais")).scalar()
        if total_carteira == 0:
            for filial, (qtd, tipo) in CARTEIRA_INICIAL_ESTRUTURADA.items():
                conn.execute(
                    text("""
                        INSERT INTO carteira_filiais (filial, clientes, tipo)
                        VALUES (:filial, :clientes, :tipo)
                        ON CONFLICT (filial) DO NOTHING;
                    """),
                    {"filial": filial, "clientes": qtd, "tipo": tipo}
                )
                
def obter_carteira_df() -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql("SELECT filial, clientes, tipo FROM carteira_filiais ORDER BY filial", conn)


def obter_carteira_filiais_dict() -> Dict[str, int]:
    with engine.connect() as conn:
        df = pd.read_sql("SELECT filial, clientes FROM carteira_filiais WHERE tipo = 'FILIAL' OR tipo = 'SMART'", conn)
    return dict(zip(df["filial"], df["clientes"]))


def salvar_carteira(df_editado: pd.DataFrame) -> None:
    if df_editado.empty or not {"filial", "clientes"}.issubset(df_editado.columns):
        raise ValueError("DataFrame inválido: deve conter as colunas 'filial' e 'clientes'.")

    with engine.begin() as conn:
        for _, row in df_editado.iterrows():
            tipo_val = str(row.get("tipo", "FILIAL")).strip().upper()
            if tipo_val not in ["FILIAL", "ESPECIAL", "SMART", "OUTROS"]:
                tipo_val = "FILIAL"
                
            conn.execute(
                text("""
                    INSERT INTO carteira_filiais (filial, clientes, tipo)
                    VALUES (:filial, :clientes, :tipo)
                    ON CONFLICT (filial) 
                    DO UPDATE SET clientes = EXCLUDED.clientes,
                                  tipo = EXCLUDED.tipo;
                """),
                {
                    "filial": str(row["filial"]).strip(),
                    "clientes": int(row["clientes"]),
                    "tipo": tipo_val
                }
            )


def calcular_hash_arquivo(caminho: Path) -> str:
    hasher = hashlib.sha256()
    with open(caminho, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def registrar_log_arquivo(
    nome: str,
    hash_sha256: str,
    tamanho: int,
    status: str,
    lidas: int = 0,
    inseridas: int = 0,
    erro: Optional[str] = None,
) -> None:
    upsert_log = text("""
        INSERT INTO arquivos_processados (
            nome_arquivo, hash_sha256, tamanho_bytes, status, 
            linhas_lidas, linhas_inseridas, mensagem_erro, data_processamento
        )
        VALUES (:nome, :hash, :tamanho, :status, :lidas, :inseridas, :erro, CURRENT_TIMESTAMP)
        ON CONFLICT (nome_arquivo) DO UPDATE SET
            hash_sha256 = EXCLUDED.hash_sha256,
            tamanho_bytes = EXCLUDED.tamanho_bytes,
            status = EXCLUDED.status,
            linhas_lidas = EXCLUDED.linhas_lidas,
            linhas_inseridas = EXCLUDED.linhas_inseridas,
            mensagem_erro = EXCLUDED.mensagem_erro,
            data_processamento = CURRENT_TIMESTAMP;
    """)
    with engine.begin() as conn:
        conn.execute(
            upsert_log,
            {
                "nome": nome,
                "hash": hash_sha256,
                "tamanho": tamanho,
                "status": status,
                "lidas": lidas,
                "inseridas": inseridas,
                "erro": erro,
            },
        )


def validar_e_tratar_planilha(arquivo: Path) -> pd.DataFrame:
    df = pd.read_excel(arquivo)
    
    faltantes = [c for c in COLUNAS_OBRIGATORIAS_EXCEL if c not in df.columns]
    if faltantes:
        raise ValueError(f"Colunas obrigatórias ausentes: {faltantes}")

    col_razao = "Razão Social" if "Razão Social" in df.columns else "Razao Social"
    col_logradouro = "Logradouro" if "Logradouro" in df.columns else None

    df = df.dropna(subset=["Id"]).copy()
    df["Id"] = pd.to_numeric(df["Id"], errors="coerce").dropna().astype("int64")

    dt_series = pd.to_datetime(df["Hora evento"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    mask_dt_na = dt_series.isna()
    if mask_dt_na.any():
        dt_series[mask_dt_na] = pd.to_datetime(df.loc[mask_dt_na, "Hora evento"], errors="coerce")

    valid_dates_mask = dt_series.notna()
    df = df[valid_dates_mask].copy()
    dt_series = dt_series[valid_dates_mask]

    if df.empty:
        return pd.DataFrame()

    df_temp = pd.DataFrame()
    df_temp["id"] = df["Id"]
    df_temp["contrato"] = df["Contrato"].astype(str).str.strip()
    df_temp["numero_contrato"] = df["Numero Contrato"].astype(str).str.strip()
    df_temp["chave_cliente"] = df_temp["contrato"] + "_" + df_temp["numero_contrato"]
    
    empresa_bruta = df.get("Empresa", pd.Series("NAO INFORMADA", index=df.index)).fillna("NAO INFORMADA").astype(str).str.strip()
    logradouro_bruto = df[col_logradouro].fillna("").astype(str) if col_logradouro else pd.Series("", index=df.index)

    df_temp["empresa"] = [normalizar_nome_filial(e, l) for e, l in zip(empresa_bruta, logradouro_bruto)]
    df_temp["razao_social"] = df[col_razao].fillna("NAO INFORMADA").astype(str).str.strip() if col_razao in df.columns else "NAO INFORMADA"
    
    # Departamento consumido diretamente da coluna sem transformações
    df_temp["departamento"] = df.get("Departamento", pd.Series("Smart Alarm", index=df.index)).fillna("Smart Alarm").astype(str).str.strip()
    df_temp["hora_evento"] = df["Hora evento"].astype(str)
    
    df_temp["dt_hora"] = dt_series
    df_temp["data_evento"] = dt_series.dt.date
    df_temp["ano_mes"] = dt_series.dt.strftime("%Y-%m")
    df_temp["hora_int"] = dt_series.dt.hour.astype(int)
    df_temp["minuto_do_dia"] = (dt_series.dt.hour * 60 + dt_series.dt.minute).astype(int)
    df_temp["final_de_semana"] = (dt_series.dt.weekday >= 5).astype(bool)

    return df_temp.drop_duplicates(subset=["id"])

def sincronizar_planilhas() -> None:
    arquivos = list(PASTA_DADOS.glob("relatorio-peak-service-analitico*.xlsx"))
    if not arquivos:
        return

    with engine.connect() as conn:
        arquivos_processados = set(
            pd.read_sql("SELECT nome_arquivo FROM arquivos_processados WHERE status = 'SUCESSO'", conn)["nome_arquivo"].tolist()
        )

    for arquivo in arquivos:
        if arquivo.name in arquivos_processados:
            continue

        logger.info(f"Iniciando processamento: {arquivo.name}")
        hash_arquivo = calcular_hash_arquivo(arquivo)
        tamanho_bytes = arquivo.stat().st_size

        try:
            df_temp = validar_e_tratar_planilha(arquivo)
            linhas_lidas = len(df_temp)

            if linhas_lidas == 0:
                registrar_log_arquivo(arquivo.name, hash_arquivo, tamanho_bytes, "SUCESSO", 0, 0)
                continue

            with engine.begin() as conn:
                df_temp.to_sql("temp_disparos_carga", conn, if_exists="replace", index=False)
                res = conn.execute(text("""
                    INSERT INTO disparos_eventos (
                        id, contrato, numero_contrato, chave_cliente, empresa,
                        razao_social, departamento, hora_evento, dt_hora,
                        data_evento, ano_mes, hora_int, minuto_do_dia, final_de_semana
                    )
                    SELECT 
                        id, contrato, numero_contrato, chave_cliente, empresa,
                        razao_social, departamento, hora_evento, dt_hora,
                        data_evento, ano_mes, hora_int, minuto_do_dia, final_de_semana::boolean
                    FROM temp_disparos_carga
                    ON CONFLICT (id) DO NOTHING;
                """))
                linhas_inseridas = res.rowcount
                conn.execute(text("DROP TABLE IF EXISTS temp_disparos_carga;"))

            registrar_log_arquivo(arquivo.name, hash_arquivo, tamanho_bytes, "SUCESSO", linhas_lidas, linhas_inseridas)
            logger.info(f"Sucesso: {arquivo.name} ({linhas_inseridas}/{linhas_lidas} novas linhas).")

        except Exception as e:
            logger.error(f"Erro ao processar {arquivo.name}: {e}")
            registrar_log_arquivo(arquivo.name, hash_arquivo, tamanho_bytes, "ERRO", erro=str(e))


def sincronizar_dados_api(dados_json: List[dict]) -> int:
    if not dados_json:
        return 0

    registros = []
    for item in dados_json:
        contrato_obj = item.get("contract") or {}
        depto_obj = contrato_obj.get("department") or {}

        try:
            id_val = int(item.get("id", 0))
        except (ValueError, TypeError):
            continue

        dt_str = item.get("startDate")
        if not dt_str:
            continue

        dt = pd.to_datetime(dt_str, errors="coerce")
        if pd.isna(dt):
            continue

        contrato = str(item.get("alphanumeric") or "").strip()
        num_contrato = str(item.get("contractIdErp") or "").strip()
        
        empresa_bruta = str(contrato_obj.get("branch") or item.get("company") or "NAO INFORMADA").strip()
        logradouro_bruto = str(item.get("address") or item.get("street") or item.get("logradouro") or "").strip()
        empresa_normalizada = normalizar_nome_filial(empresa_bruta, logradouro_bruto)

        razao = str(item.get("socialReason") or "NAO INFORMADA").strip()
        depto = str(depto_obj.get("description") or contrato_obj.get("contractType") or "OUTROS").strip()

        registros.append({
            "id": id_val,
            "contrato": contrato,
            "numero_contrato": num_contrato,
            "chave_cliente": f"{contrato}_{num_contrato}",
            "empresa": empresa_normalizada,
            "razao_social": razao,
            "departamento": depto,
            "hora_evento": dt.strftime("%d/%m/%Y %H:%M:%S"),
            "dt_hora": dt,
            "data_evento": dt.date(),
            "ano_mes": dt.strftime("%Y-%m"),
            "hora_int": int(dt.hour),
            "minuto_do_dia": int(dt.hour * 60 + dt.minute),
            "final_de_semana": bool(dt.weekday() >= 5)
        })

    df_temp = pd.DataFrame(registros).drop_duplicates(subset=["id"])
    linhas_lidas = len(df_temp)
    if linhas_lidas == 0:
        return 0

    with engine.begin() as conn:
        df_temp.to_sql("temp_api_carga", conn, if_exists="replace", index=False)
        res = conn.execute(text("""
            INSERT INTO disparos_eventos (
                id, contrato, numero_contrato, chave_cliente, empresa,
                razao_social, departamento, hora_evento, dt_hora,
                data_evento, ano_mes, hora_int, minuto_do_dia, final_de_semana
            )
            SELECT 
                id, contrato, numero_contrato, chave_cliente, empresa,
                razao_social, departamento, hora_evento, dt_hora,
                data_evento, ano_mes, hora_int, minuto_do_dia, final_de_semana::boolean
            FROM temp_api_carga
            ON CONFLICT (id) DO NOTHING;
        """))
        linhas_inseridas = res.rowcount
        conn.execute(text("DROP TABLE IF EXISTS temp_api_carga;"))

    logger.info(f"API Ingestao: {linhas_lidas} lidos | {linhas_inseridas} novas linhas gravadas.")
    return linhas_inseridas


def salvar_snapshot_relatorio_contratos(
    period_start: date,
    period_end: date,
    page_size: int,
    page_count: int,
    total_item_count: int,
    items: List[dict],
) -> int:
    if period_start > period_end:
        raise ValueError("period_start deve ser anterior ou igual a period_end.")
    if page_size <= 0 or page_count < 0 or total_item_count < 0:
        raise ValueError("Metadados de paginação inválidos.")
    if len(items) != total_item_count:
        raise ValueError(
            "Quantidade de itens recebida não corresponde ao total informado pela API."
        )

    colunas_item = {
        "cod_contrato",
        "empresa",
        "razao_social",
        "num_contrato",
        "departamento",
        "department_id",
        "department_mapping_confidence",
        "disparos",
        "message_count",
        "zona_disparos",
        "data",
        "mes",
        "estado",
    }
    itens_gravacao = []
    contratos_encontrados = set()
    for item in items:
        faltantes = colunas_item.difference(item)
        if faltantes:
            raise ValueError(
                f"Campos ausentes no item do relatório: {sorted(faltantes)}"
            )
        num_contrato = item["num_contrato"]
        if num_contrato in contratos_encontrados:
            raise ValueError(
                f"Contrato repetido na mesma coleta: {num_contrato}"
            )
        contratos_encontrados.add(num_contrato)
        if item["data"] != period_end or item["mes"] != period_end.month:
            raise ValueError(
                "A data e o mês dos itens devem corresponder ao fim do período."
            )
        itens_gravacao.append(dict(item))

    with engine.begin() as conn:
        snapshot_id = conn.execute(
            text("""
                INSERT INTO alarm_report_snapshots (
                    period_start, period_end, page_size, page_count, total_item_count
                )
                VALUES (
                    :period_start, :period_end, :page_size, :page_count,
                    :total_item_count
                )
                RETURNING id
            """),
            {
                "period_start": period_start,
                "period_end": period_end,
                "page_size": page_size,
                "page_count": page_count,
                "total_item_count": total_item_count,
            },
        ).scalar_one()

        if itens_gravacao:
            for item in itens_gravacao:
                item["snapshot_id"] = snapshot_id
            conn.execute(
                text("""
                    INSERT INTO disparos_sensor (
                        snapshot_id, cod_contrato, empresa, razao_social,
                        num_contrato, departamento, department_id,
                        department_mapping_confidence, disparos, message_count,
                        zona_disparos, data, mes, estado
                    )
                    VALUES (
                        :snapshot_id, :cod_contrato, :empresa, :razao_social,
                        :num_contrato, :departamento, :department_id,
                        :department_mapping_confidence, :disparos, :message_count,
                        :zona_disparos, :data, :mes, :estado
                    )
                """),
                itens_gravacao,
            )

    return int(snapshot_id)


def carregar_relatorio_sensores() -> pd.DataFrame:
    consulta = text("""
        WITH snapshots_recentes AS (
            SELECT
                DISTINCT ON (period_start, period_end)
                id,
                period_start,
                period_end,
                collected_at,
                page_size,
                page_count,
                total_item_count
            FROM alarm_report_snapshots
            ORDER BY period_start, period_end, collected_at DESC, id DESC
        )
        SELECT
            s.id AS snapshot_id,
            s.period_start,
            s.period_end,
            s.collected_at,
            s.page_size,
            s.page_count,
            s.total_item_count,
            d.id,
            d.cod_contrato,
            d.empresa,
            d.razao_social,
            d.num_contrato,
            d.departamento,
            d.department_id,
            d.department_mapping_confidence,
            d.disparos,
            d.message_count,
            d.zona_disparos,
            d.data,
            d.mes,
            d.estado,
            d.modelo_sensor
        FROM snapshots_recentes s
        LEFT JOIN disparos_sensor d ON d.snapshot_id = s.id
        ORDER BY d.data, d.razao_social NULLS LAST, d.num_contrato
    """)
    with engine.connect() as conn:
        return _read_sql(consulta, conn, nome="relatorio_sensores")


def carregar_periodos_analise_sensores() -> pd.DataFrame:
    consulta = text("""
        WITH snapshots_recentes AS (
            SELECT DISTINCT ON (period_start, period_end) id
            FROM alarm_report_snapshots
            ORDER BY period_start, period_end, collected_at DESC, id DESC
        )
        SELECT DISTINCT a.dia, a.hora_cheia
        FROM analise a
        WHERE a.hora_cheia BETWEEN 0 AND 23
          AND EXISTS (
              SELECT 1
              FROM snapshots_recentes sr
              JOIN disparos_sensor ds ON ds.snapshot_id = sr.id
              WHERE ds.data = a.dia
                AND ds.num_contrato = CASE
                    WHEN TRIM(COALESCE(a.numero_contrato, '')) ~ '^[0-9]+$'
                    THEN TRIM(a.numero_contrato)::BIGINT
                END
                AND TRIM(ds.cod_contrato) = TRIM(COALESCE(a.contrato, ''))
                AND UPPER(TRIM(COALESCE(ds.departamento, ''))) =
                    UPPER(TRIM(COALESCE(a.departamento, '')))
                AND UPPER(TRIM(COALESCE(ds.estado, ''))) =
                    UPPER(TRIM(COALESCE(a.estado, '')))
                AND ds.modelo_sensor NOT IN ('VAZIO', 'SEM ZONA')
          )
        ORDER BY a.dia, a.hora_cheia
    """)
    with engine.connect() as conn:
        return _read_sql(consulta, conn, nome="periodos_analise_sensores")


def carregar_contratos_analise_sensores(data_analise: date, hora_analise: int) -> pd.DataFrame:
    if not 0 <= hora_analise <= 23:
        raise ValueError("hora_analise deve estar entre 0 e 23.")

    consulta = text("""
        SELECT DISTINCT
            CASE
                WHEN TRIM(COALESCE(numero_contrato, '')) ~ '^[0-9]+$'
                THEN TRIM(numero_contrato)::BIGINT
            END AS num_contrato,
            UPPER(TRIM(COALESCE(departamento, ''))) AS departamento,
            UPPER(TRIM(COALESCE(estado, ''))) AS estado
        FROM vw_analise_disp_sensor
        WHERE dia = :data_analise
          AND hora_cheia = :hora_analise
          AND sensores_no_dia <> 'SEM SENSOR NO DIA'
          AND TRIM(COALESCE(numero_contrato, '')) ~ '^[0-9]+$'
    """)
    with engine.connect() as conn:
        return _read_sql(
            consulta,
            conn,
            nome="contratos_analise_sensores",
            params={"data_analise": data_analise, "hora_analise": hora_analise},
        )


def carregar_intervalo_analise_sensores() -> tuple[Optional[date], Optional[date]]:
    consulta = text("""
        SELECT MIN(dia) AS data_minima, MAX(dia) AS data_maxima
        FROM vw_analise_disp_sensor
        WHERE sensores_no_dia <> 'SEM SENSOR NO DIA'
          AND hora_cheia BETWEEN 0 AND 23
    """)
    with engine.connect() as conn:
        intervalo = _read_sql(
            consulta,
            conn,
            nome="intervalo_analise_sensores",
        )
    if intervalo.empty or pd.isna(intervalo.loc[0, "data_minima"]):
        return None, None
    return (
        pd.Timestamp(intervalo.loc[0, "data_minima"]).date(),
        pd.Timestamp(intervalo.loc[0, "data_maxima"]).date(),
    )


def _validar_intervalo_sensores(
    data_inicio: date,
    data_fim: date,
    hora_inicio: int,
    hora_fim: int,
) -> None:
    if data_inicio > data_fim:
        raise ValueError("data_inicio deve ser anterior ou igual a data_fim.")
    if not 0 <= hora_inicio <= hora_fim <= 23:
        raise ValueError("A faixa horária deve estar entre 0 e 23, em ordem crescente.")


def carregar_relatorio_sensores_periodo(
    data_inicio: date,
    data_fim: date,
    hora_inicio: int,
    hora_fim: int,
) -> pd.DataFrame:
    _validar_intervalo_sensores(data_inicio, data_fim, hora_inicio, hora_fim)
    consulta = text("""
        WITH snapshots_recentes AS (
            SELECT DISTINCT ON (period_start, period_end)
                id,
                period_start,
                period_end,
                collected_at,
                page_size,
                page_count,
                total_item_count
            FROM alarm_report_snapshots
            WHERE period_end BETWEEN :data_inicio AND :data_fim
            ORDER BY period_start, period_end, collected_at DESC, id DESC
        )
        SELECT
            s.id AS snapshot_id,
            s.period_start,
            s.period_end,
            s.collected_at,
            s.page_size,
            s.page_count,
            s.total_item_count,
            d.id,
            d.cod_contrato,
            d.empresa,
            d.razao_social,
            d.num_contrato,
            d.departamento,
            d.department_id,
            d.department_mapping_confidence,
            d.disparos,
            d.message_count,
            d.zona_disparos,
            d.data,
            d.mes,
            d.estado,
            d.modelo_sensor
        FROM snapshots_recentes s
        JOIN disparos_sensor d ON d.snapshot_id = s.id
        WHERE d.data BETWEEN :data_inicio AND :data_fim
          AND EXISTS (
              SELECT 1
              FROM vw_analise_disp_sensor a
              WHERE a.dia BETWEEN :data_inicio AND :data_fim
                AND a.dia = d.data
                AND a.hora_cheia BETWEEN :hora_inicio AND :hora_fim
                AND a.sensores_no_dia <> 'SEM SENSOR NO DIA'
                AND CASE
                    WHEN TRIM(COALESCE(a.numero_contrato, '')) ~ '^[0-9]+$'
                    THEN TRIM(a.numero_contrato)::BIGINT
                END = d.num_contrato
                AND UPPER(TRIM(COALESCE(a.departamento, ''))) =
                    UPPER(TRIM(COALESCE(d.departamento, '')))
                AND UPPER(TRIM(COALESCE(a.estado, ''))) =
                    UPPER(TRIM(COALESCE(d.estado, '')))
          )
        ORDER BY d.data, d.razao_social NULLS LAST, d.num_contrato
    """)
    with engine.connect() as conn:
        return _read_sql(
            consulta,
            conn,
            nome="relatorio_sensores_periodo",
            params={
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "hora_inicio": hora_inicio,
                "hora_fim": hora_fim,
            },
        )


def carregar_distribuicao_horaria_analise_sensores(
    data_inicio: date,
    data_fim: date,
    hora_inicio: int,
    hora_fim: int,
) -> pd.DataFrame:
    _validar_intervalo_sensores(data_inicio, data_fim, hora_inicio, hora_fim)
    consulta = text("""
        SELECT
            hora_cheia AS hora,
            COUNT(DISTINCT id) AS analises
        FROM vw_analise_disp_sensor
        WHERE dia BETWEEN :data_inicio AND :data_fim
          AND hora_cheia BETWEEN :hora_inicio AND :hora_fim
          AND sensores_no_dia <> 'SEM SENSOR NO DIA'
        GROUP BY hora_cheia
        ORDER BY hora_cheia
    """)
    with engine.connect() as conn:
        return _read_sql(
            consulta,
            conn,
            nome="distribuicao_horaria_analise_sensores",
            params={
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "hora_inicio": hora_inicio,
                "hora_fim": hora_fim,
            },
        )


def carregar_opcoes_eventos() -> dict[str, list[str]]:
    with engine.connect() as conn:
        empresas = _read_sql(
            text("""
                SELECT DISTINCT empresa
                FROM disparos_eventos
                WHERE empresa IS NOT NULL
                ORDER BY empresa
            """),
            conn,
            nome="opcoes_empresas",
        )
        departamentos = _read_sql(
            text("""
                SELECT DISTINCT departamento
                FROM disparos_eventos
                WHERE departamento IS NOT NULL
                ORDER BY departamento
            """),
            conn,
            nome="opcoes_departamentos",
        )
    return {
        "empresas": empresas["empresa"].astype(str).tolist(),
        "departamentos": departamentos["departamento"].astype(str).tolist(),
    }


def _filtros_eventos(
    empresas: List[str],
    departamentos: List[str],
) -> tuple[str, dict]:
    if not empresas or not departamentos:
        return "", {}
    return (
        " AND empresa IN :empresas AND departamento IN :departamentos",
        {"empresas": empresas, "departamentos": departamentos},
    )


def carregar_meses_eventos(
    empresas: List[str],
    departamentos: List[str],
) -> list[str]:
    filtro_sql, params = _filtros_eventos(empresas, departamentos)
    if not filtro_sql:
        return []
    consulta = text(f"""
        SELECT DISTINCT ano_mes
        FROM disparos_eventos
        WHERE ano_mes IS NOT NULL{filtro_sql}
        ORDER BY ano_mes DESC
    """).bindparams(
        bindparam("empresas", expanding=True),
        bindparam("departamentos", expanding=True),
    )
    with engine.connect() as conn:
        meses = _read_sql(
            consulta,
            conn,
            nome="meses_eventos",
            params=params,
        )
    return meses["ano_mes"].astype(str).tolist()


def carregar_intervalo_eventos(
    empresas: List[str],
    departamentos: List[str],
    data_limite: Optional[date] = None,
) -> tuple[Optional[date], Optional[date]]:
    filtro_sql, params = _filtros_eventos(empresas, departamentos)
    if not filtro_sql:
        return None, None
    limite_sql = " AND data_evento <= :data_limite" if data_limite else ""
    if data_limite:
        params["data_limite"] = data_limite
    consulta = text(f"""
        SELECT MIN(data_evento) AS data_minima, MAX(data_evento) AS data_maxima
        FROM disparos_eventos
        WHERE data_evento IS NOT NULL{filtro_sql}{limite_sql}
    """).bindparams(
        bindparam("empresas", expanding=True),
        bindparam("departamentos", expanding=True),
    )
    with engine.connect() as conn:
        intervalo = _read_sql(
            consulta,
            conn,
            nome="intervalo_eventos",
            params=params,
        )
    if intervalo.empty or pd.isna(intervalo.loc[0, "data_minima"]):
        return None, None
    return (
        pd.Timestamp(intervalo.loc[0, "data_minima"]).date(),
        pd.Timestamp(intervalo.loc[0, "data_maxima"]).date(),
    )


def carregar_eventos(
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    empresas: Optional[List[str]] = None,
    departamentos: Optional[List[str]] = None,
    *,
    ano_mes: Optional[str] = None,
    minuto_inicio: Optional[int] = None,
    minuto_fim: Optional[int] = None,
) -> pd.DataFrame:
    if data_inicio and data_fim and data_inicio > data_fim:
        return pd.DataFrame(columns=COLUNAS_EVENTOS)
    if not empresas or not departamentos:
        return pd.DataFrame(columns=COLUNAS_EVENTOS)
    if (minuto_inicio is None) != (minuto_fim is None):
        raise ValueError("minuto_inicio e minuto_fim devem ser informados juntos.")
    if minuto_inicio is not None and (
        not 0 <= minuto_inicio <= 1439 or not 0 <= minuto_fim <= 1439
    ):
        raise ValueError("Os minutos devem estar entre 0 e 1439.")

    filtros = []
    params = {
        "empresas": empresas,
        "departamentos": departamentos,
    }
    if data_inicio is not None:
        filtros.append("data_evento >= :inicio")
        params["inicio"] = data_inicio
    if data_fim is not None:
        filtros.append("data_evento <= :fim")
        params["fim"] = data_fim
    if ano_mes is not None:
        filtros.append("ano_mes = :ano_mes")
        params["ano_mes"] = ano_mes
    if minuto_inicio is not None:
        filtros.append("minuto_do_dia BETWEEN :minuto_inicio AND :minuto_fim")
        params["minuto_inicio"] = minuto_inicio
        params["minuto_fim"] = minuto_fim
    filtros.extend(
        [
            "empresa IN :empresas",
            "departamento IN :departamentos",
        ]
    )
    consulta = text(f"""
        SELECT {", ".join(COLUNAS_EVENTOS)}
        FROM disparos_eventos
        WHERE {" AND ".join(filtros)}
    """).bindparams(
        bindparam("empresas", expanding=True),
        bindparam("departamentos", expanding=True),
    )

    with engine.connect() as conn:
        df = _read_sql(
            consulta,
            conn,
            nome="eventos_monitoramento" if minuto_inicio is not None else "eventos",
            params=params,
        )

    if not df.empty:
        df["dt_hora"] = pd.to_datetime(df["dt_hora"])
        df["data_evento"] = pd.to_datetime(df["data_evento"]).dt.date

    return df


def carregar_comparacao_disparos_mensais(
    empresas: List[str],
    departamentos: List[str],
) -> pd.DataFrame:
    filtro_sql, params = _filtros_eventos(empresas, departamentos)
    colunas = [
        "empresa",
        "departamento",
        "numero_contrato",
        "contrato",
        "razao_social",
        "ano_mes",
        "total_disparos",
    ]
    if not filtro_sql:
        return pd.DataFrame(columns=colunas)
    consulta = text(f"""
        SELECT
            empresa,
            departamento,
            numero_contrato,
            contrato,
            razao_social,
            COALESCE(
                TO_CHAR(data_evento, 'YYYY-MM'),
                CASE
                    WHEN ano_mes ~ '^\\d{4}-\\d{2}$' THEN ano_mes
                END
            ) AS ano_mes,
            COUNT(id) AS total_disparos
        FROM disparos_eventos
        WHERE (data_evento IS NOT NULL
               OR ano_mes ~ '^\\d{4}-\\d{2}$'){filtro_sql}
        GROUP BY
            empresa, departamento, numero_contrato, contrato, razao_social,
            COALESCE(
                TO_CHAR(data_evento, 'YYYY-MM'),
                CASE
                    WHEN ano_mes ~ '^\\d{4}-\\d{2}$' THEN ano_mes
                END
            )
        ORDER BY ano_mes, empresa, departamento, numero_contrato
    """).bindparams(
        bindparam("empresas", expanding=True),
        bindparam("departamentos", expanding=True),
    )
    with engine.connect() as conn:
        return _read_sql(
            consulta,
            conn,
            nome="comparacao_disparos_mensais",
            params=params,
        ).loc[:, colunas]


def carregar_alertas_mau_uso() -> pd.DataFrame:
    consulta = text("""
        WITH por_contrato AS (
            SELECT
                numero_contrato,
                COUNT(*) FILTER (
                    WHERE EXTRACT(HOUR FROM dt_hora) BETWEEN 6 AND 9
                       OR EXTRACT(HOUR FROM dt_hora) BETWEEN 18 AND 21
                ) AS disparos_abertura_fechamento,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(
                        EXTRACT(HOUR FROM dt_hora) BETWEEN 6 AND 9
                        OR EXTRACT(HOUR FROM dt_hora) BETWEEN 18 AND 21,
                        FALSE
                    )
                ) AS disparos_outros_periodos
            FROM disparos_eventos
            WHERE numero_contrato IS NOT NULL
              AND BTRIM(numero_contrato) <> ''
            GROUP BY numero_contrato
        )
        SELECT
            numero_contrato AS "NUMERO_CONTRATO",
            disparos_abertura_fechamento AS "DISPAROS_ABERTURA_FECHAMENTO",
            disparos_outros_periodos AS "DISPAROS_OUTROS_PERIODOS"
        FROM por_contrato
        WHERE disparos_abertura_fechamento >= 4
          AND disparos_outros_periodos = 0
        ORDER BY disparos_abertura_fechamento DESC
    """)
    with engine.connect() as conn:
        return _read_sql(consulta, conn, nome="alertas_mau_uso")


def carregar_limitadores() -> pd.DataFrame:
    consulta = text("""
        SELECT
            numero_contrato AS "NUMERO_CONTRATO",
            data_evento AS "DATA_EVENTO",
            EXTRACT(HOUR FROM dt_hora)::INTEGER AS "HORA",
            COUNT(*) AS "OCORRENCIAS"
        FROM disparos_eventos
        WHERE numero_contrato IS NOT NULL
          AND BTRIM(numero_contrato) <> ''
          AND data_evento IS NOT NULL
          AND dt_hora IS NOT NULL
        GROUP BY
            numero_contrato,
            data_evento,
            EXTRACT(HOUR FROM dt_hora)
        HAVING COUNT(*) >= 5
        ORDER BY numero_contrato, data_evento, "HORA"
    """)
    with engine.connect() as conn:
        return _read_sql(consulta, conn, nome="limitadores")


def carregar_acompanhamento_diario(
    data_inicio: date,
    data_fim: date,
    empresas: List[str],
    departamentos: List[str],
) -> pd.DataFrame:
    if data_inicio > data_fim:
        raise ValueError("data_inicio deve ser anterior ou igual a data_fim.")
    if not empresas or not departamentos:
        return pd.DataFrame(columns=COLUNAS_ACOMPANHAMENTO_DIARIO)

    consulta = text("""
        SELECT
            data_evento AS dia,
            empresa,
            chave_cliente,
            MAX(razao_social) AS razao_social,
            COUNT(id) AS disparos
        FROM disparos_eventos
        WHERE data_evento BETWEEN :inicio AND :fim
          AND empresa IN :empresas
          AND departamento IN :departamentos
        GROUP BY data_evento, empresa, chave_cliente
    """).bindparams(
        bindparam("empresas", expanding=True),
        bindparam("departamentos", expanding=True),
    )

    with engine.connect() as conn:
        df = _read_sql(
            consulta,
            conn,
            nome="acompanhamento_diario",
            params={
                "inicio": data_inicio,
                "fim": data_fim,
                "empresas": empresas,
                "departamentos": departamentos,
            },
        )

    if not df.empty:
        df["dia"] = pd.to_datetime(df["dia"]).dt.date
        df["disparos"] = df["disparos"].astype(int)
    return df.loc[:, COLUNAS_ACOMPANHAMENTO_DIARIO]
