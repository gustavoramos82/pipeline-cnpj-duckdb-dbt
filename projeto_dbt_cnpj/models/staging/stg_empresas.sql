{{ config(materialized='view') }}

SELECT
    LPAD(TRIM(column0), 8, '0') AS cnpj_basico,
    NULLIF(TRIM(column1), '') AS razao_social,
    NULLIF(TRIM(column2), '') AS codigo_natureza_juridica,
    NULLIF(TRIM(column3), '') AS qualificacao_responsavel,
    TRY_CAST(NULLIF(REPLACE(TRIM(column4), ',', '.'), '') AS DECIMAL(18,2)) AS capital_social,
    NULLIF(TRIM(column5), '') AS porte_empresa,
    NULLIF(TRIM(column6), '') AS ente_federativo_responsavel
FROM read_parquet('../data/silver/parquet/empresas_*.parquet', union_by_name=true)
WHERE NULLIF(TRIM(column0), '') IS NOT NULL
