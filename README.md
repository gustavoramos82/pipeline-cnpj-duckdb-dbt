# Pipeline CNPJ — DuckDB + dbt

Pipeline local e portátil para tratar os arquivos públicos de CNPJ da Receita Federal. DuckDB executa a conversão e o processamento local; dbt organiza os modelos e testes.

## Arquitetura

```text
Arquivos ZIP originais da Receita
          ↓
Bronze: data/bronze/ (originais preservados)
          ↓ extração segura
Bronze operacional: data/bronze/csv/
          ↓ transcodificação temporária para UTF-8
DuckDB COPY + Parquet ZSTD
          ↓
Prata: data/silver/parquet/*.parquet
          ↓ modelos dbt + DuckDB
Ouro: data/gold/socios_ouro.parquet + banco data/cnpj.duckdb
```

A Prata usa Parquet como formato persistente. O CSV UTF-8 criado para lidar com arquivos de origem em Latin-1 é temporário e apagado após a conversão bem-sucedida. Os ZIPs e arquivos de origem da Bronze são preservados.

## Execução

1. Coloque os ZIPs oficiais em `data/bronze/`.
2. Execute `uv sync`.
3. Execute `uv run python main.py`.

A saída final é `data/gold/socios_ouro.parquet`; o banco DuckDB fica em `data/cnpj.duckdb`.

## Componentes

- `src/extracao.py`: extrai arquivos tabulares dos ZIPs, inclusive nomes oficiais sem extensão `.csv`.
- `src/duckdb_etl.py`: detecta encoding por amostra, converte em streaming para UTF-8 temporário e usa DuckDB para gerar Parquet com compressão ZSTD. Registra manifesto com tamanho e SHA-256 dos originais.
- `projeto_dbt_cnpj/models/staging/`: staging lê os arquivos Parquet da Prata.
- `models/intermediate/`: relacionamentos.
- `models/marts/`: tabela analítica de saída.

## Importante antes de produção

- A implementação de conversão para Parquet está incluída, mas não foi validada de ponta a ponta com todos os arquivos oficiais atuais da Receita. Faça primeiro um teste com uma amostra real.
- Os arquivos CNPJ oficiais frequentemente não terminam em `.csv`; o extrator reconhece sufixos comuns como `EMPRECSV`, `ESTABELE`, `SOCIOCSV`, `QUALS`, `SIMPLES`, `CNAE`, `MUN` e `NATJU`. A Receita pode alterar nomes ou pacotes; confira os arquivos efetivamente baixados.
- Confirme os índices das colunas com o leiaute oficial vigente. Não preencha componentes ausentes do CNPJ com valores inventados.
- A junção de sócios com estabelecimentos pelo CNPJ básico pode multiplicar linhas quando há vários estabelecimentos e vários sócios. Defina a granularidade da análise antes de usar os resultados.
- Trate esta versão como base de implementação a ser testada, não como pipeline já homologada com a base integral.
