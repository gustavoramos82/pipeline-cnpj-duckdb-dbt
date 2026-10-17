from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import duckdb

from src.extracao import preparar_arquivos_bronze
from src.duckdb_etl import preparar_prata_parquet

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
DBT_DIR = BASE_DIR / "projeto_dbt_cnpj"
DB_PATH = BASE_DIR / "data" / "cnpj.duckdb"
GOLD_DIR = BASE_DIR / "data" / "gold"
PARQUET_PATH = GOLD_DIR / "socios_ouro.parquet"

def configurar_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"pipeline_{datetime.now():%Y%m%d_%H%M%S}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )

def executar_dbt() -> None:
    """Executa dbt usando o executável correspondente ao ambiente Python atual."""
    env = os.environ.copy()
    env["CNPJ_DB_PATH"] = str(DB_PATH)
    env["CNPJ_PROJECT_DIR"] = str(BASE_DIR)
    
    # Descobre o caminho do executável 'dbt' na mesma pasta onde o python.exe atual está alojado
    python_dir = Path(sys.executable).parent
    dbt_exec = python_dir / ("dbt.exe" if os.name == "nt" else "dbt")
    
    # Se não encontrar no diretório do python, tenta usar o comando global 'dbt'
    if not dbt_exec.exists():
        dbt_exec = "dbt"
    else:
        dbt_exec = str(dbt_exec)

    cmd = [dbt_exec, "build", "--profiles-dir", str(DBT_DIR)]
    logging.info("Executando: %s", " ".join(cmd))
    subprocess.run(cmd, cwd=DBT_DIR, env=env, check=True)

def exportar_parquet() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Banco DuckDB não encontrado: {DB_PATH}")
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        # O modelo dbt cria a tabela main.socios_ouro. COPY grava o produto de entrega.
        destino_sql = str(PARQUET_PATH).replace("\\", "/").replace("'", "''")
        con.execute(f"COPY (SELECT * FROM main.socios_ouro) TO '{destino_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    logging.info("Parquet exportado: %s", PARQUET_PATH)

def run_pipeline() -> int:
    configurar_logging()
    logging.info("Iniciando pipeline CNPJ")
    try:
        for pasta in (
            BASE_DIR / "data" / "bronze",
            BASE_DIR / "data" / "bronze" / "csv",
            BASE_DIR / "data" / "silver" / "parquet",
            GOLD_DIR,
            BASE_DIR / "data" / "temp_duckdb",
        ):
            pasta.mkdir(parents=True, exist_ok=True)

        logging.info("Etapa 1/4: extração segura dos arquivos ZIP")
        preparar_arquivos_bronze(BASE_DIR)

        logging.info("Etapa 2/4: conversão da Bronze para Parquet na Prata com DuckDB")
        preparar_prata_parquet(BASE_DIR)

        logging.info("Etapa 3/4: modelos e testes dbt")
        executar_dbt()

        logging.info("Etapa 4/4: exportação para Parquet")
        exportar_parquet()

        logging.info("Pipeline concluído com sucesso")
        print(f"\nConcluído. Arquivo gerado: {PARQUET_PATH}")
        return 0
    except subprocess.CalledProcessError as exc:
        logging.exception("O dbt falhou com código %s", exc.returncode)
        print(f"\nERRO: dbt falhou (código {exc.returncode}). Consulte a pasta logs/.")
        return int(exc.returncode or 1)
    except Exception:
        logging.exception("Falha no pipeline")
        print("\nERRO: o pipeline não foi concluído. Consulte a pasta logs/.")
        return 1

if __name__ == "__main__":
    raise SystemExit(run_pipeline())
