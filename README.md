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

##  Modelo de dados

| Tabela | Descrição |
|---|---|
| `disparos_eventos` | Eventos de disparo (contrato, cliente, empresa, departamento, data/hora e campos derivados como `ano_mes` e `final_de_semana`) |
| `carteira_filiais` | Quantidade de clientes por filial/núcleo, usada para calcular proporções |
| `arquivos_processados` | Controle de importações (nome, hash, status, linhas lidas/inseridas, erro) |

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
