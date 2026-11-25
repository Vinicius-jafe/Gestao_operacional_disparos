# Instrucoes do projeto

## Visao geral

Este repositorio contem um painel operacional em Streamlit para analisar disparos de alarme.

- `src/app.py`: interface Streamlit, filtros, abas, graficos e cache das consultas.
- `src/database.py`: acesso ao PostgreSQL, importacao de Excel, sincronizacao da API e normalizacao de filiais.
- `src/metrics.py`: funcoes puras de agregacao, recorrencia, taxas, limitador e mau uso.
- `src/prediction.py`: calculo das previsoes mensais e projecoes.
- `src/presentation.py`: transformacoes usadas para apresentar contratos e clientes.
- `src/collector.py`: worker que consulta a API periodicamente e grava os eventos.
- `src/auth.py`: autenticacao e renovacao do token da API externa.
- `src/config.py`: configuracoes por ambiente, banco e carteira inicial.
- `tests/unit/`: testes pytest; `tests/conftest.py` contem fixtures compartilhadas.
- `init.sql`: schema PostgreSQL, indices e carga inicial da carteira.

## Executando e validando

- Use Python 3.11, conforme a imagem Docker e o pipeline.
- Instale as dependencias de desenvolvimento com `pip install -r requirements.txt -r requirements-dev.txt`.
- Execute toda a suite com `python -m pytest`.
- Para validar apenas um arquivo: `python -m pytest tests/unit/test_<area>.py`.
- Para testar sintaxe: `python -m py_compile src/app.py src/*.py`.
- Para subir a aplicacao com Docker: `docker compose up -d --build`.
- Interface local: `streamlit run src/app.py`.
- Coletor local: `python -m src.collector`.
- Cobertura esta configurada no `pytest.ini` e inclui HTML em `htmlcov/`.

Nao inicie ou derrube containers como parte de mudancas apenas de codigo. Antes de testar integracao real, confirme que existe um PostgreSQL acessivel e um `.env` valido.

## Arquitetura e convencoes

- Preserve a separacao em camadas: UI em `app.py`, SQL/acesso a dados em `database.py`, calculos em `metrics.py`/`prediction.py` e formatacao em `presentation.py`.
- Mantenha calculos testaveis como funcoes puras que recebam e devolvam `pandas.DataFrame`, exceto onde o acesso ao banco seja realmente necessario.
- Use nomes de coluna ja adotados pelo projeto. SQL e DataFrames usam principalmente `chave_cliente`, `numero_contrato`, `data_evento`, `dt_hora`, `ano_mes`, `empresa`, `departamento`, `razao_social` e `id`.
- Deduplique eventos por `id` antes de agregacoes que possam contar o mesmo registro mais de uma vez.
- Preserve filtros por `chave_cliente`/periodo nas previsoes e nao misture o filtro de horarios com indicadores que devam considerar todo o historico, como mau uso e limitador.
- Use timezone/fuso de Brasil (`America/Sao_Paulo`) nas configuracoes containerizadas. Para datas, respeite `date.today()`/datas de referencia de teste em vez de depender do horario atual quando o calculo puder ser deterministico.
- Use SQLAlchemy e consultas parametrizadas com `text(...)`; nao concatene dados do usuario em SQL.
- Ao alterar o schema, atualize `init.sql`, `verificar_integridade_banco()` e os testes relevantes em conjunto.
- Ao alterar a carteira ou sua normalizacao, mantenha os nomes oficiais e os tipos `FILIAL`, `ESPECIAL`, `SMART` e `OUTROS` coerentes com `config.py` e `database.py`.
- Nao exponha ou registre tokens JWT, refresh tokens ou senhas. Nao modifique `.env` nem registre credenciais em codigo ou fixtures.

## Streamlit e interface

- Prefira componentes existentes de Streamlit e Plotly; preserve o tema escuro e os estilos definidos em `src/app.py`.
- Parametrize funcoes cacheadas por todos os filtros relevantes, usando tipos hashable como tuplas nos decorators `@st.cache_data`.
- Use `st.stop()` ou uma mensagem clara para estados de banco indisponivel; nao silencie erros de integridade.
- Use rotulos em portugues e mantenha coerencia nos nomes das abas, metricas e classificacoes exibidas.
- Mude a UI apenas apos entender o fluxo completo da aba correspondente em `src/app.py`.

## Testes

- Adicione ou atualize testes para qualquer mudanca de comportamento em `tests/unit/`.
- Reutilize fixtures de `tests/conftest.py`.
- Cobertura deve incluir entradas vazias, tipos incorretos, colunas obrigatorias ausentes e casos limite ja previstos pela regra.
- Use DataFrames pequenos e explicitamente definidos em testes; passe datas de referencia a funcoes que aceitam essa opcionalidade.
- Execute o teste focado primeiro e depois `python -m pytest`.
- Não trate cobertura HTML gerada (`htmlcov/`) ou caches (`.pytest_cache/`) como arquivos de codigo.

## Mudancas seguras

- Faça mudancas cirurgicas e preserve o comportamento existente quando nao houver requisicao de mudanca.
- Não edite banco, planilhas de dados, backup ou arquivos em `BD DISPAROS/` como parte da implementacao, salvo pedido explicito.
- Não adicione dependencias sem necessidade. Se adicionar, atualize `requirements.txt` ou `requirements-dev.txt` e valide a importacao.
- Ao encontrar um arquivo sujo ou alteracoes nao relacionadas, preserve-as e limite o diff aos arquivos necessarios.
