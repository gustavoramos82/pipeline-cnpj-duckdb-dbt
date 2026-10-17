{{ config(materialized='view') }}

with estabelecimentos as (
    select * from {{ ref('stg_estabelecimentos') }}
),

empresas as (
    select * from {{ ref('stg_empresas') }}
),

socios as (
    select * from {{ ref('stg_socios') }}
)

select
    e.cnpj_completo,
    e.cnpj_basico,
    emp.razao_social as nome_empresa,
    s.nome_socio,
    s.cpf_cnpj_socio
from estabelecimentos e
left join empresas emp on e.cnpj_basico = emp.cnpj_basico
left join socios s on e.cnpj_basico = s.cnpj_basico
where s.cpf_cnpj_socio is not null
