from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import codecs

import duckdb

LOGGER = logging.getLogger(__name__)

# Categorias restritas apenas aos arquivos essenciais para a camada Ouro.
CATEGORIAS = {
    "empresas": ("EMPRECSV", "EMPRESAS"),
    "estabelecimentos": ("ESTABELE", "ESTABELECIMENTOS"),
    "socios": ("SOCIOCSV", "SOCIOS"),
}

# Mapeamento corrigido com o número exato de colunas oficiais da Receita Federal:
# - Empresas: 7 colunas
# - Estabelecimentos: 30 colunas
# - Sócios: 11 colunas
COLUNAS_ESQUEMA = {
    "empresas": {
        f"column{i}": "VARCHAR" for i in range(7)
    },
    "estabelecimentos": {
        f"column{i}": "VARCHAR" for i in range(30)
    },
    "socios": {
        f"column{i}": "VARCHAR" for i in range(11)
    },
}

# Codificação padrão dos arquivos de origem.
# Pode ser sobrescrita pela variável de ambiente CNPJ_ENCODING.
CODIFICACAO_ORIGEM = os.getenv("CNPJ_ENCODING", "cp1252")

TAMANHO_BLOCO = 1024 * 1024  # 1 MB


def _categoria(nome: str) -> str | None:
    """Identifica a categoria a partir do nome do arquivo."""
    upper = Path(nome).name.upper()
    stem = upper[:-4] if upper.endswith(".CSV") else upper

    for categoria, marcadores in CATEGORIAS.items():
        if any(
            stem.endswith(marcador)
            or f"__{marcador}" in stem
            for marcador in marcadores
        ):
            return categoria

    return None


def _sha256(caminho: Path) -> str:
    """Calcula SHA-256 em blocos, sem carregar o arquivo inteiro."""
    digest = hashlib.sha256()

    with caminho.open("rb") as arquivo:
        while True:
            bloco = arquivo.read(TAMANHO_BLOCO)
            if not bloco:
                break
            digest.update(bloco)

    return digest.hexdigest()


def _converter_utf8_stream(origem, destino, encoding_origem='cp1252'):
    # Se o destino já existir, podemos saltar (idempotência)
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        return  # Já convertido!

    decoder = codecs.getincrementaldecoder(encoding_origem)(errors='replace')
    with open(origem, 'rb') as src, open(destino, 'w', encoding='utf-8') as dst:
        while True:
            bloco = src.read(65536)
            if not bloco:
                break
            dst.write(decoder.decode(bloco))
        dst.write(decoder.decode(b'', final=True))


def preparar_prata_parquet(base_dir: Path | str) -> None:
    """
    Converte os CSVs essenciais extraídos para Parquet respeitando rigorosamente o esquema.

    Os ZIPs originais são preservados.
    """
    base = Path(base_dir).resolve()

    origem_dir = base / "data" / "bronze" / "csv"
    destino_dir = base / "data" / "silver" / "parquet"
    temp_dir = base / "data" / "temp_duckdb"
    manifesto_path = destino_dir / "manifest.json"

    if not origem_dir.exists():
        raise FileNotFoundError(
            f"Pasta de origem não encontrada: {origem_dir}"
        )

    destino_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    arquivos = sorted(
        p
        for p in origem_dir.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and not p.name.lower().endswith(".tmp")
        and p.suffix.lower() != ".zip"
    )

    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum arquivo de dados encontrado em {origem_dir}"
        )

    manifesto = {
        "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
        "codificacao_origem": CODIFICACAO_ORIGEM,
        "arquivos": [],
    }

    con = duckdb.connect()
    convertidos = 0

    try:
        # Configurações de otimização de memória do DuckDB
        con.execute("SET memory_limit = '4GB'")
        con.execute("SET threads = 2")
        con.execute("SET preserve_insertion_order = false")

        for origem in arquivos:
            categoria = _categoria(origem.name)

            if categoria is None:
                LOGGER.debug(
                    "Arquivo ignorado (não pertence às categorias essenciais): %s",
                    origem.name,
                )
                continue

            nome_saida = f"{categoria}_{origem.stem}.parquet"
            destino = destino_dir / nome_saida

            # IDEMPOTÊNCIA: Se o Parquet final já existe e tem conteúdo, saltamos para continuar de onde parou!
            if destino.exists() and destino.stat().st_size > 0:
                LOGGER.info("Parquet já existe, ignorando (Retomando de onde parou): %s", nome_saida)
                
                hash_origem = _sha256(origem)
                manifesto["arquivos"].append(
                    {
                        "origem": origem.name,
                        "categoria": categoria,
                        "parquet": nome_saida,
                        "sha256_origem": hash_origem,
                        "tamanho_origem_bytes": origem.stat().st_size,
                        "tamanho_parquet_bytes": destino.stat().st_size,
                        "codificacao": CODIFICACAO_ORIGEM,
                    }
                )
                convertidos += 1
                continue

            hash_origem = _sha256(origem)

            LOGGER.info(
                "Convertendo com esquema estrito: %s (categoria: %s)",
                origem.name,
                categoria,
            )

            fd, temp_csv_nome = tempfile.mkstemp(
                prefix="cnpj_",
                suffix=".csv",
                dir=temp_dir,
            )
            os.close(fd)
            temp_csv = Path(temp_csv_nome)

            temp_parquet = destino.with_name(
                destino.name + ".tmp.parquet"
            )

            try:
                _converter_utf8_stream(
                    origem,
                    temp_csv,
                    CODIFICACAO_ORIGEM,
                )

                caminho_sql = (
                    str(temp_csv.resolve())
                    .replace("\\", "/")
                    .replace("'", "''")
                )
                parquet_sql = (
                    str(temp_parquet.resolve())
                    .replace("\\", "/")
                    .replace("'", "''")
                )

                # Obtém o dicionário de colunas estruturado para esta categoria
                colunas_map = COLUNAS_ESQUEMA.get(categoria)
                
                # Leitura estricta com colunas definidas exatamente de acordo com o arquivo oficial
                con.execute(
                    f"""
                    COPY (
                        SELECT *
                        FROM read_csv(
                            '{caminho_sql}',
                            delim=';',
                            quote='"',
                            escape='"',
                            header=false,
                            columns={colunas_map},
                            strict_mode=true,
                            ignore_errors=false,
                            parallel=false
                        )
                    )
                    TO '{parquet_sql}'
                    (FORMAT PARQUET, COMPRESSION ZSTD)
                    """
                )

                parquet_check = (
                    str(temp_parquet.resolve())
                    .replace("\\", "/")
                    .replace("'", "''")
                )

                quantidade = con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM read_parquet('{parquet_check}')
                    """
                ).fetchone()[0]

                temp_parquet.replace(destino)

                manifesto["arquivos"].append(
                    {
                        "origem": origem.name,
                        "categoria": categoria,
                        "parquet": nome_saida,
                        "sha256_origem": hash_origem,
                        "tamanho_origem_bytes": origem.stat().st_size,
                        "tamanho_parquet_bytes": destino.stat().st_size,
                        "quantidade_registros": quantidade,
                        "codificacao": CODIFICACAO_ORIGEM,
                    }
                )

                convertidos += 1

                LOGGER.info(
                    "Parquet gerado com sucesso: %s | registros: %s",
                    destino.name,
                    quantidade,
                )

            except Exception:
                LOGGER.exception(
                    "Falha estricta na conversão para Parquet: %s",
                    origem.name,
                )
                raise

            finally:
                temp_csv.unlink(missing_ok=True)
                temp_parquet.unlink(missing_ok=True)

        if convertidos == 0:
            raise ValueError(
                "Nenhum arquivo essencial foi convertido. "
                "Confira os nomes e sufixos dos arquivos CNPJ."
            )

        manifesto_temp = manifesto_path.with_name(
            manifesto_path.name + ".tmp"
        )

        manifesto_temp.write_text(
            json.dumps(
                manifesto,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        manifesto_temp.replace(manifesto_path)

        LOGGER.info(
            "Processamento concluído: %s arquivo(s) essenciais tratados com rigor.",
            convertidos,
        )
        LOGGER.info("Manifesto salvo em: %s", manifesto_path)

    finally:
        con.close()

