{{ config(materialized='view') }}

SELECT
    column0 || column1 || column2 AS cnpj_completo,
    column0 AS cnpj_basico,
    column1 AS cnpj_ordem,
    column2 AS cnpj_dv,
    NULLIF(TRIM(column5), '') AS situacao_cadastral
FROM read_parquet('../data/silver/parquet/estabelecimentos_*.parquet', union_by_name=true)
WHERE NULLIF(TRIM(column0), '') IS NOT NULL
  AND column5 = '02'
