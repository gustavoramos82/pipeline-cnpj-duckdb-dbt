# Pipeline CNPJ (DuckDB + dbt)

Pipeline de Engenharia de Dados de alta performance, eficiente em termos de memória e orientado a dados abertos da Receita Federal (CNPJ: Empresas, Estabelecimentos e Sócios). Este projeto foi concebido para alimentar rotinas de conciliação financeira com rigor de integridade, idempotência e baixo consumo de recursos.

O objetivo não é trazer a base completo mas um pipeline simplificado para trazer apenas as informações necessárias

---

## 🚀 Principais Melhorias e Arquitetura

1. **Camada Prata Completa (Preservação de Histórico)**:
   - Os dados brutos são convertidos e limpos para Parquet sem exclusões rígidas na origem, garantindo flexibilidade para consultas históricas completas caso necessário.

2. **Arquitetura de Grafo dbt Otimizada**:
   - Remoção de dependências e modelos obsoletos (como qualificações e tabelas acessórias que não agregavam valor à camada analítica final).
   - Limpeza e otimização do fluxo de *staging*, intermediários (*intermediate*) e *marts*, garantindo um ciclo de compilação livre de erros e dependências órfãs.

3. **Filtragem e Enriquecimento na Camada Ouro**:
   - Aplicação de filtros específicos (como o isolamento de empresas e estabelecimentos ativos) diretamente na modelagem final, mantendo a camada Prata intacta para eventuais consultas de auditoria.
   - Correção e mapeamento robusto do relacionamento entre **Estabelecimentos, Empresas (Razão Social) e Sócios**.
   - Garantia de que a tabela final (`socios_ouro`) possui o grão correto de **estabelecimento x vínculo societário**, trazendo o `cnpj_completo` e o `nome_empresa` devidamente preenchidos para cruzamento financeiro.

4. **Desempenho com o Motor DuckDB**:
   - Aproveitamento nativo do motor *out-of-core* e vetorial do DuckDB, garantindo execução fluida mesmo sob limites restritos de memória.

---

## 🛠️ Tecnologias Utilizadas

* **Python**: Orquestração e automação do pipeline (`main.py`).
* **DuckDB**: Motor analítico relacional de alta performance para processamento em streaming e manipulação de Parquet.
* **dbt (dbt-duckdb)**: Transformação de dados, testes de qualidade e documentação modular.
* **Formato Parquet (ZSTD)**: Armazenamento columnar comprimido nas camadas Prata e Ouro.

---

## 📂 Estrutura do Projeto

```text
pipeline-cnpj-duckdb-dbt/
├── data/
│   ├── bronze/          # Dados brutos descompactados (CSV)
│   ├── silver/          # Dados limpos e particionados (Parquet)
│   └── gold/            # Visões consolidadas e filtradas finais para o negócio
├── projeto_dbt_cnpj/
│   ├── models/
│   │   ├── staging/     # stg_empresas, stg_estabelecimentos, stg_socios
│   │   ├── intermediate/# int_socios_empresa
│   │   └── marts/       # socios_ouro (Tabela final com filtros aplicados)
│   └── dbt_project.yml
├── src/
│   └── duckdb_etl.py    # Scripts de extração e conversão
├── main.py              # Orquestrador geral do pipeline
└── README.md
```

---

## ⚙️ Como Executar o Pipeline

### 1. Pré-requisitos
Certifique-se de ter o Python instalado juntamente com as bibliotecas necessárias:
```bash
pip install duckdb dbt-duckdb
```

### 2. Configuração do Ambiente
Coloque os ficheiros CSV brutos da Receita Federal na pasta de dados bronze correspondente ou certifique-se de que o script de extração está a apontar para os diretórios corretos.

### 3. Execução Completa
Execute o script principal de orquestração no terminal para correr o ETL da Prata e compilar os modelos dbt:
```bash
python main.py
```

### 4. Validação na Camada Ouro
Pode consultar diretamente o resultado consolidado e testar os dados (como a consulta de uma empresa específica) utilizando o DuckDB:
```sql
SELECT *
FROM read_parquet('data/gold/socios_ouro.parquet')
WHERE cnpj_completo = 'qualquercnpj';
```
