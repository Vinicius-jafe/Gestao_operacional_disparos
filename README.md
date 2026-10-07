#  Gestão Operacional de Disparos

Painel web para acompanhamento e análise de **disparos de alarme** de uma operação de segurança eletrônica. A aplicação coleta eventos automaticamente a partir de uma API, armazena o histórico em PostgreSQL e disponibiliza dashboards interativos para identificar padrões, **reincidências** por cliente e distribuição por filial, e registrar as tratativas da equipe.

##  Funcionalidades

- **Coleta automática** de eventos via API, executada por um worker em segundo plano (`coletor-horario`)
- **Dashboard interativo** com gráficos (Plotly) e tabelas (Pandas) filtráveis por empresa, departamento e período
- **Análise por filial** com base na carteira de clientes de cada unidade e de núcleos especiais (Redes, Totens, Smart P, DGP, Manutenção Regional)
- **Detecção de reincidência** por cliente/mês, com workflow de **tratativas** (status, responsável e observação)
- **Importação de planilhas** (Excel) com controle de arquivos já processados via hash SHA-256, evitando duplicidade
- **Execução 100% containerizada** com Docker Compose (app + worker + banco)

## 🛠️ Tecnologias

| Camada | Tecnologia |
|---|---|
| Interface | [Streamlit](https://streamlit.io/), [Plotly](https://plotly.com/python/) |
| Dados | Pandas, OpenPyXL, SQLAlchemy |
| Banco de dados | PostgreSQL 15 (`psycopg2`) |
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

##  Modelo de dados

| Tabela | Descrição |
|---|---|
| `disparos_eventos` | Eventos de disparo (contrato, cliente, empresa, departamento, data/hora e campos derivados como `ano_mes` e `final_de_semana`) |
| `carteira_filiais` | Quantidade de clientes por filial/núcleo, usada para calcular proporções |
| `arquivos_processados` | Controle de importações (nome, hash, status, linhas lidas/inseridas, erro) |
| `tratativas_reincidencia` | Histórico de tratativas por cliente e mês (status, responsável, observação) |

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
| `EMIVE_ORIGIN_URL` / `EMIVE_REFERER_URL` | Cabeçalhos `Origin` e `Referer` das requisições |
| `POSTGRES_DB` | Nome do banco (padrão: `disparos_emive`) |
| `POSTGRES_USER` | Usuário do banco (padrão: `admin_emive`) |
| `POSTGRES_PASSWORD` | Senha do banco |
| `DATABASE_URL` | String de conexão usada pela aplicação |

>  **Nunca versione o arquivo `.env`.** Ele contém tokens e senhas e já deve estar listado no `.gitignore`.

### Rodando sem Docker (desenvolvimento)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# aplicação
streamlit run src/app.py

# coletor (em outro terminal)
python -m src.collector
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
