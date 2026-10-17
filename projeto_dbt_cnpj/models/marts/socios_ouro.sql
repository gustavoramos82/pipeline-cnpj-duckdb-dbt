{{ config(materialized='table') }}

with int_socios as (
    select * from {{ ref('int_socios_empresa') }}
)

select
    cnpj_completo,
    cnpj_basico,
    nome_empresa,
    nome_socio,
    cpf_cnpj_socio
from int_socios