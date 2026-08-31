import hashlib
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from sqlalchemy import create_engine, text
from src.config import CARTEIRA_INICIAL_ESTRUTURADA, DB_URL, PASTA_DADOS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

engine = create_engine(DB_URL, pool_pre_ping=True)

TABELAS_OBRIGATORIAS = ["arquivos_processados", "carteira_filiais", "disparos_eventos", "tratativas_reincidencia"]
COLUNAS_OBRIGATORIAS_EXCEL = ["Id", "Contrato", "Numero Contrato", "Hora evento"]

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
    """Verifica se o schema existe no PostgreSQL."""
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public';
            """)
            tabelas_existentes = {row[0] for row in conn.execute(query).fetchall()}
            
            faltantes = [t for t in TABELAS_OBRIGATORIAS if t not in tabelas_existentes]
            if faltantes:
                raise RuntimeError(
                    f"CRITICO: Schema incompleto no PostgreSQL. Tabelas ausentes: {faltantes}."
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
                conn.commit()
    except Exception as e:
        raise SystemExit(f"Erro irrecuperavel ao conectar com o banco de dados: {e}")


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


def carregar_eventos(data_inicio: Optional[date] = None, data_fim: Optional[date] = None) -> pd.DataFrame:
    query = "SELECT * FROM disparos_eventos"
    params = {}

    if data_inicio and data_fim:
        query += " WHERE data_evento BETWEEN :inicio AND :fim"
        params = {"inicio": data_inicio, "fim": data_fim}
    elif data_inicio:
        query += " WHERE data_evento >= :inicio"
        params = {"inicio": data_inicio}

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params)

    if not df.empty:
        df["dt_hora"] = pd.to_datetime(df["dt_hora"])
        df["data_evento"] = pd.to_datetime(df["data_evento"]).dt.date

    return df


def carregar_tratativas(ano_mes: str) -> pd.DataFrame:
    """Busca as tratativas salvas no PostgreSQL para a competência."""
    query = text("""
        SELECT chave_cliente, status, responsavel, observacao, data_atualizacao
        FROM tratativas_reincidencia
        WHERE ano_mes = :ano_mes
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"ano_mes": ano_mes})


def salvar_tratativa(
    chave_cliente: str,
    ano_mes: str,
    status: str,
    responsavel: str,
    observacao: str
) -> None:
    """Executa Upsert da tratativa mantendo auditoria por cliente/mês."""
    query = text("""
        INSERT INTO tratativas_reincidencia (
            chave_cliente, ano_mes, status, responsavel, observacao, data_atualizacao
        )
        VALUES (:chave, :ano_mes, :status, :responsavel, :observacao, CURRENT_TIMESTAMP)
        ON CONFLICT (chave_cliente, ano_mes) DO UPDATE SET
            status = EXCLUDED.status,
            responsavel = EXCLUDED.responsavel,
            observacao = EXCLUDED.observacao,
            data_atualizacao = CURRENT_TIMESTAMP;
    """)
    with engine.begin() as conn:
        conn.execute(query, {
            "chave": chave_cliente,
            "ano_mes": ano_mes,
            "status": status,
            "responsavel": responsavel,
            "observacao": observacao
        })