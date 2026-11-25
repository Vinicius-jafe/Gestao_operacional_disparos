import hashlib
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from sqlalchemy import bindparam, create_engine, text
from src.config import CARTEIRA_INICIAL_ESTRUTURADA, DB_URL, PASTA_DADOS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

engine = create_engine(DB_URL, pool_pre_ping=True)

COLUNAS_OBRIGATORIAS_EXCEL = ["Id", "Contrato", "Numero Contrato", "Hora evento"]
COLUNAS_ACOMPANHAMENTO_DIARIO = [
    "dia",
    "empresa",
    "chave_cliente",
    "razao_social",
    "disparos",
]

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
        return pd.read_sql(consulta, conn)


def carregar_periodos_analise_sensores() -> pd.DataFrame:
    consulta = text("""
        SELECT DISTINCT dia, hora_cheia
        FROM vw_analise_disp_sensor
        WHERE sensores_no_dia <> 'SEM SENSOR NO DIA'
          AND hora_cheia BETWEEN 0 AND 23
        ORDER BY dia, hora_cheia
    """)
    with engine.connect() as conn:
        return pd.read_sql(consulta, conn)


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
        return pd.read_sql(
            consulta,
            conn,
            params={"data_analise": data_analise, "hora_analise": hora_analise},
        )


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
        df = pd.read_sql(
            consulta,
            conn,
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
