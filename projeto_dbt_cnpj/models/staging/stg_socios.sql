{{ config(materialized='view') }}

SELECT
    LPAD(TRIM(column0), 8, '0') AS cnpj_basico,
    NULLIF(TRIM(column1), '') AS identificador_socio,
    NULLIF(TRIM(column2), '') AS nome_socio,
    NULLIF(TRIM(column3), '') AS cpf_cnpj_socio,
    NULLIF(TRIM(column4), '') AS codigo_qualificacao_socio,
    NULLIF(TRIM(column5), '') AS data_entrada_sociedade,
    NULLIF(TRIM(column6), '') AS codigo_pais,
    NULLIF(TRIM(column7), '') AS representante_legal,
    NULLIF(TRIM(column8), '') AS nome_representante,
    NULLIF(TRIM(column9), '') AS codigo_qualificacao_representante,
    NULLIF(TRIM(column10), '') AS faixa_etaria
FROM read_parquet('../data/silver/parquet/socios_*.parquet', union_by_name=true)
WHERE NULLIF(TRIM(column0), '') IS NOT NULL
