#  Gestão Operacional de Disparos

Painel web para acompanhamento e análise de **disparos de alarme** de uma operação de segurança eletrônica. A aplicação coleta eventos automaticamente a partir de uma API, armazena o histórico em PostgreSQL e disponibiliza dashboards interativos para identificar padrões, **reincidências** por cliente e distribuição por filial.

##  Funcionalidades

- **Coleta automática** de eventos via API, executada por um worker em segundo plano (`coletor-horario`)
- **Dashboard interativo** com gráficos (Plotly) e tabelas (Pandas) filtráveis por empresa, departamento e período
- **Acompanhamento diário** de disparos por filial e por cliente, com comparação de séries no período escolhido
- **Análise por filial** com base na carteira de clientes de cada unidade e de núcleos especiais (Redes, Totens, Smart P, DGP, Manutenção Regional)
- **Detecção de reincidência** por cliente e análise de Pareto para priorização operacional
- **Análises complementares** de distribuição por hora/faixa, recorrência mensal, comparação mensal e sinais de possível mau uso/limitador
- **Taxa por carteira** com as unidades paulistas consolidadas em SP e identificação de empresas sem correspondência
- **Previsões mensais por cliente** com média diária histórica, alerta de reincidência, regressão linear e projeção de fechamento
- **Relatório de sensores** com filtros por filial, departamento e modelo, busca por cliente/contrato, gráficos e exportação CSV
- **Importação de planilhas** (Excel) com controle de arquivos já processados via hash SHA-256, evitando duplicidade
- **Execução 100% containerizada** com Docker Compose (app + worker + banco)

## 🛠️ Tecnologias

| Camada | Tecnologia |
|---|---|
| Interface | [Streamlit](https://streamlit.io/), [Plotly](https://plotly.com/python/) |
| Dados | Pandas, OpenPyXL, SQLAlchemy |
| Banco de dados | PostgreSQL 15 (`psycopg`) |
| Integração com API | HTTPX |
| Infraestrutura | Docker, Docker Compose |
| CI | Woodpecker CI (`.woodpecker.yml`) |

##  Arquitetura

```
┌──────────────┐      ┌─────────────────┐      ┌──────────────────┐
│  API externa │ ───▶ │ coletor-horario │ ───▶ │   PostgreSQL     │
│  (eventos)   │      │  (worker)       │      │ (disparos, ...)  │
└──────────────┘      └─────────────────┘      └────────┬─────────┘
                                                        │
                                               ┌────────▼─────────┐
                                               │ painel-disparos  │
                                               │   (Streamlit)    │
                                               └──────────────────┘
```

O `docker-compose.yml` sobe três serviços:

- **`postgres-db`**: banco PostgreSQL, inicializado com o `init.sql`
- **`painel-disparos`**: aplicação Streamlit (`src/app.py`) na porta `8501`
- **`coletor-horario`**: worker de coleta (`src/collector.py`)
- **`coletor-relatorio-alarmes`**: snapshots horários do relatório de contratos
  (`src/alarm_report_collector.py`)
- **`migrar-analise-legada`**: comando opcional para copiar a tabela `analise`
  do SQLite legado ao PostgreSQL

##  Modelo de dados

| Tabela | Descrição |
|---|---|
| `disparos_eventos` | Eventos de disparo (contrato, cliente, empresa, departamento, data/hora e campos derivados como `ano_mes` e `final_de_semana`) |
| `analise` | Histórico diário importado do banco SQLite legado |
| `alarm_report_snapshots` | Metadados de cada coleta do relatório agregado de contratos |
| `disparos_sensor` | Top zona e contagens aproximadas por contrato e snapshot coletados pela API |
| `disparos_sensor_legado` | Nomes, zonas e contagens de sensores migrados do SQLite legado |
| `vw_disparos_sensor_unificados` | Sensores da API e do SQLite, sem duplicar o mesmo contrato/data |
| `vw_analise_disp_sensor` | View que relaciona o histórico diário com o último snapshot de cada período consultado |
| `carteira_filiais` | Quantidade de clientes por filial/núcleo, usada para calcular proporções |
| `arquivos_processados` | Controle de importações (nome, hash, status, linhas lidas/inseridas, erro) |

O relatório agregado é coletado separadamente a cada hora para os últimos sete
dias (hoje e os sete dias anteriores). Cada execução cria um snapshot próprio;
`disparos_sensor.disparos` usa `topZone.triggerCount` quando disponível e
`messageCount` como fallback, enquanto `message_count` preserva o total da API.
`data` representa a data final do período consultado, não a data real do
disparo; portanto, o cruzamento da view é aproximado. Cada linha contém somente
a zona mais recorrente daquele contrato, não todas as zonas. A coleta segue
`hasNextPage`, descarta contratos repetidos pelo `contractIdErp` e reinicia a
paginação uma vez se a quantidade final não coincidir com a API, evitando
snapshots duplicados ou incompletos. O mapeamento do
departamento 17 para SEMAX é marcado como inferido em
`department_mapping_confidence`. Com o volume da amostra (8.249 contratos), a
coleta horária pode gerar cerca de 198 mil linhas por dia; não há expurgo
automático de snapshots.

A aba **Sensores** combina o snapshot mais recente de cada período, incluindo os
registros históricos de sensores migrados do SQLite, e mostra registros por
modelo, zonas principais e contagens por cliente. A tabela exibe a origem e a
data de cada registro; para os snapshots do endpoint agregado, ela representa o
fim da janela consultada.
Os filtros de período e faixa horária usam `analise.dia` e
`analise.hora_cheia`; por padrão, a aba mostra os últimos sete dias disponíveis
e a faixa completa de 00:00 a 23:00. Os intervalos são inclusivos e podem ser
ajustados, por exemplo, para 1 a 7 de setembro e 02:00 a 16:00. A consulta
retorna somente sensores dos contratos relacionados às análises nesse recorte.
O gráfico diário resume registros de sensores por dia; o gráfico por hora conta
análises associadas, não disparos de sensores. Como o endpoint agrega dados por
dia e não retorna o horário individual nem todas as zonas instaladas, essa
associação é aproximada e não identifica o horário real de disparo de cada
sensor.

## Previsões mensais

A aba **Previsões** compara, por contrato e cliente, os três meses fechados
anteriores com o mês atual até ontem. A média histórica considera o número real
de dias de cada mês; a taxa atual usa `max(1, dia do mês - 1)` e a projeção de
fechamento usa o total de dias do mês corrente. Também são exibidos severidade,
razão de tendência, alerta de reincidência, previsão linear do próximo mês e
comparativo com o último mês fechado.

O filtro **Faixa horária das análises**, disponível na barra lateral, permite
selecionar Madrugada (00:00–05:59), Abertura (06:00–08:59), Comercial
(08:00–17:59), Fechamento (17:00–21:59) e Noite (22:00–23:59). Comercial se
sobrepõe a Abertura entre 08:00 e 08:59 e a Fechamento entre 17:00 e 17:59.
Sem períodos selecionados, são considerados todos os horários. Com mais de um
período, é possível incluir clientes com disparos em qualquer um deles ou
somente clientes com disparos em todos. O filtro afeta o monitoramento, as
previsões e as distribuições por hora/período. Os alertas de mau uso e limitador
continuam considerando todo o histórico, sem o filtro.

O monitoramento por dia e horário considera todo o histórico disponível até
hoje, incluindo os disparos do dia atual, e atualiza essa seção automaticamente
a cada cinco minutos.

## Desempenho do painel

O painel busca no PostgreSQL somente as colunas e o período selecionados. Os
filtros de filial, departamento, data e horário são aplicados na consulta;
monitoramento e acompanhamento consultam seus próprios recortes, enquanto
comparações mensais e alertas históricos são agregados no banco. Resultados de
consultas e cálculos reutilizáveis ficam em cache por 60 segundos. A exportação
Excel da aba de reincidência só é preparada após clicar em **Preparar relatório
Excel**.

Os logs do serviço `painel-disparos` registram `Desempenho DB`, com o tempo de
execução do driver (incluindo a espera pela resposta do PostgreSQL), o tempo
restante de leitura/conversão para DataFrame, quantidade de linhas e tamanho
estimado do DataFrame. Também registram os cálculos de previsão e reincidência
e o tempo total de execução no servidor para renderizar o painel. Esse último
valor não mede o tempo de pintura no navegador.

Como o esquema atual de eventos não possui uma coluna de indicador separada, a
coluna **J (indicador)** corresponde ao total de disparos do mês atual (**I**);
a classificação é Baixa abaixo de 4, Média de 4 a 9 e Alta a partir de 10.

##  Como executar

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) e Docker Compose
- Credenciais de acesso à API de eventos

### Passos

1. Clone o repositório:

   ```bash
   git clone https://github.com/Vinicius-jafe/Gestao_operacional_disparos.git
   cd Gestao_operacional_disparos
   ```

2. Crie o arquivo de variáveis de ambiente a partir do exemplo:

   ```bash
   cp .env.example .env
   ```

3. Preencha o `.env` (veja a tabela abaixo).

4. Suba os serviços:

   ```bash
   docker compose up -d --build
   ```

5. Acesse o painel em **http://localhost:8501**

### Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `EMIVE_JWT_TOKEN` | Token JWT para autenticar na API |
| `EMIVE_REFRESH_TOKEN` | Token de renovação da sessão |
| `EMIVE_API_BASE_URL` | URL base da API |
| `EMIVE_API_PEAK_ENDPOINT` | Endpoint de consulta dos eventos |
| `DEPARTAMENTOS_FILTRO` | Departamentos considerados na coleta |
| `EMIVE_ALARM_REPORT_ENDPOINT` | Endpoint do relatório agregado de contratos |
| `EMIVE_ALARM_REPORT_DEPARTMENTS_IDS` | IDs de departamentos para esse relatório (padrão: 1 a 50) |
| `EMIVE_ALARM_REPORT_PAGE_SIZE` | Itens por página (padrão: 25) |
| `EMIVE_ALARM_REPORT_REQUEST_INTERVAL_SECONDS` | Pausa mínima entre requisições do relatório (padrão: 1 segundo) |
| `EMIVE_ALARM_REPORT_INTERVAL_SECONDS` | Intervalo entre coletas, em segundos (padrão: 3600) |
| `EMIVE_ORIGIN_URL` / `EMIVE_REFERER_URL` | Cabeçalhos `Origin` e `Referer` das requisições |
| `POSTGRES_DB` | Nome do banco (padrão: `disparos_emive`) |
| `POSTGRES_USER` | Usuário do banco (padrão: `admin_emive`) |
| `POSTGRES_PASSWORD` | Senha do banco |
| `DATABASE_URL` | String de conexão usada pela aplicação |

>  **Nunca versione o arquivo `.env`.** Ele contém tokens e senhas e já deve estar listado no `.gitignore`.

Em bancos já inicializados, aplique `init.sql` uma vez antes de iniciar os
coletores. O Docker executa os scripts de inicialização do PostgreSQL somente
quando o volume de dados é criado pela primeira vez. Com o serviço PostgreSQL
ativo, o comando abaixo reaplica o schema e as cargas iniciais idempotentes:

```bash
docker compose exec -T postgres-db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < init.sql
```

Para copiar os 304 mil registros históricos de `analise` do SQLite para o
PostgreSQL, com o schema já aplicado e o `Database.db` disponível no caminho
legado, execute uma vez:

```bash
docker compose --profile migration run --rm migrar-analise-legada
```

A migração lê o SQLite em modo somente leitura, converte `dia` para `DATE`,
processa em lotes e ignora IDs já existentes no PostgreSQL. Ela não apaga nem
altera os registros de origem.

Para copiar também o histórico de nomes e zonas dos sensores da tabela
`disparos_sensor` do mesmo SQLite:

```bash
docker compose --profile migration run --rm migrar-sensores-legados
```

Os registros são mantidos em `disparos_sensor_legado`, sem substituir a tabela
usada pelo coletor da API nem alterar `disparos_eventos`. A aba **Sensores**
combina as duas origens, priorizando a coleta da API quando houver o mesmo
contrato e data. A migração pode ser repetida e atualiza os registros pelo ID
original do SQLite.

### Rodando sem Docker (desenvolvimento)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# aplicação
streamlit run src/app.py

# coletor (em outro terminal)
python -m src.collector

# coleta do relatório agregado (em outro terminal)
python -m src.alarm_report_collector
```

Neste modo, é necessário ter um PostgreSQL acessível e ajustar o `DATABASE_URL` para `localhost`.

##  Estrutura do projeto

```
.
├── src/                  # Código-fonte (app Streamlit e coletor)
├── .env.example          # Modelo de variáveis de ambiente
├── .woodpecker.yml       # Pipeline de CI
├── Dockerfile            # Imagem da aplicação
├── docker-compose.yml    # Orquestração dos serviços
├── init.sql              # Criação das tabelas, índices e carga inicial
└── requirements.txt      # Dependências Python
```

##  Autor

**Vinicius Jafe Andrade Carvalho**
GitHub: [@Vinicius-jafe](https://github.com/Vinicius-jafe)
