from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from pathlib import Path, PurePosixPath

LOGGER = logging.getLogger(__name__)

# Sufixos restritos apenas aos arquivos essenciais para a camada Gold (Empresas, Estabelecimentos e Sócios).
SUFIXOS_CNPJ = (
    "EMPRECSV",
    "ESTABELE",
    "SOCIOCSV",
)

TAMANHO_BLOCO = 1024 * 1024  # 1 MB
PROFUNDIDADE_MAXIMA = 5


def _nome_seguro(nome: str) -> str:
    """Retorna apenas o nome do arquivo, sem caminhos internos do ZIP."""
    return PurePosixPath(nome.replace("\\", "/")).name


def _eh_arquivo_cnpj(nome: str) -> bool:
    """Identifica apenas os arquivos tabulares essenciais para a camada Gold."""
    nome = _nome_seguro(nome).upper()

    if nome.endswith(".CSV"):
        return True

    return any(nome.endswith(sufixo) for sufixo in SUFIXOS_CNPJ)


def _sha256_arquivo(caminho: Path) -> str:
    """Calcula o hash do arquivo em blocos."""
    digest = hashlib.sha256()

    with caminho.open("rb") as arquivo:
        while True:
            bloco = arquivo.read(TAMANHO_BLOCO)
            if not bloco:
                break
            digest.update(bloco)

    return digest.hexdigest()


def _carregar_manifesto(caminho: Path) -> dict:
    """Carrega o manifesto de extração, se ele existir."""
    if not caminho.exists():
        return {"arquivos": {}}

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))

        if not isinstance(dados.get("arquivos"), dict):
            return {"arquivos": {}}

        return dados

    except (OSError, json.JSONDecodeError):
        LOGGER.warning(
            "Manifesto inválido; será reconstruído: %s",
            caminho,
        )
        return {"arquivos": {}}


def _salvar_manifesto(caminho: Path, manifesto: dict) -> None:
    """Salva o manifesto de forma atômica."""
    temporario = caminho.with_name(caminho.name + ".tmp")

    temporario.write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    temporario.replace(caminho)


def _extrair_membro(
    zf: zipfile.ZipFile,
    membro: zipfile.ZipInfo,
    destino: Path,
) -> None:
    """Extrai um membro para um arquivo temporário e depois o substitui."""
    temporario = destino.with_name(destino.name + ".tmp")

    try:
        with zf.open(membro) as origem, temporario.open("wb") as saida:
            shutil.copyfileobj(
                origem,
                saida,
                length=TAMANHO_BLOCO,
            )

        temporario.replace(destino)

    finally:
        temporario.unlink(missing_ok=True)


def _processar_zip(
    caminho_zip: Path,
    pasta_csv: Path,
    pasta_temp: Path,
    manifesto: dict,
    caminho_manifesto: Path,
    prefixo: str = "",
    nivel: int = 0,
) -> int:
    """
    Processa um ZIP, inclusive ZIPs aninhados.

    Arquivos já extraídos e registrados no manifesto são reutilizados.
    ZIPs internos são materializados temporariamente em disco, sem
    carregar o conteúdo completo do pacote na memória.
    """
    if nivel > PROFUNDIDADE_MAXIMA:
        raise ValueError(
            f"Profundidade máxima de ZIPs excedida: {caminho_zip}"
        )

    total_extraidos = 0

    with zipfile.ZipFile(caminho_zip, "r") as zf:
        for indice, membro in enumerate(zf.infolist()):
            if membro.is_dir():
                continue

            nome = _nome_seguro(membro.filename)

            if not nome:
                continue

            if nome.lower().endswith(".zip"):
                # Nome determinístico e exclusivo para cada ZIP interno.
                nome_interno = (
                    f"{nivel}_{indice}_"
                    f"{hashlib.sha256((prefixo + '|' + membro.filename).encode('utf-8')).hexdigest()[:16]}.zip"
                )
                zip_interno = pasta_temp / nome_interno

                try:
                    _extrair_membro(zf, membro, zip_interno)

                    novo_prefixo = "__".join(
                        parte
                        for parte in (prefixo, Path(nome).stem)
                        if parte
                    )

                    total_extraidos += _processar_zip(
                        caminho_zip=zip_interno,
                        pasta_csv=pasta_csv,
                        pasta_temp=pasta_temp,
                        manifesto=manifesto,
                        caminho_manifesto=caminho_manifesto,
                        prefixo=novo_prefixo,
                        nivel=nivel + 1,
                    )

                finally:
                    zip_interno.unlink(missing_ok=True)

                continue

            if not _eh_arquivo_cnpj(nome):
                continue

            nome_saida = "__".join(
                parte for parte in (prefixo, nome) if parte
            )
            destino = pasta_csv / nome_saida

            chave = str(destino.name)
            registro = manifesto["arquivos"].get(chave)

            # Reutiliza o CSV somente se o manifesto indicar que ele
            # veio do mesmo membro, com o mesmo tamanho e CRC.
            mesma_origem = (
                registro is not None
                and registro.get("origem_zip") == caminho_zip.name
                and registro.get("membro") == membro.filename
                and registro.get("tamanho") == membro.file_size
                and registro.get("crc") == membro.CRC
            )

            if (
                destino.exists()
                and destino.stat().st_size == membro.file_size
                and mesma_origem
            ):
                LOGGER.info("Já extraído, ignorando (Retomando de onde parou): %s", nome_saida)
                continue

            _extrair_membro(zf, membro, destino)

            manifesto["arquivos"][chave] = {
                "origem_zip": caminho_zip.name,
                "membro": membro.filename,
                "tamanho": membro.file_size,
                "crc": membro.CRC,
            }

            _salvar_manifesto(caminho_manifesto, manifesto)

            LOGGER.info(
                "Extraído: %s (%s bytes)",
                nome_saida,
                membro.file_size,
            )

            total_extraidos += 1

    return total_extraidos


def preparar_arquivos_bronze(base_dir: Path | str) -> None:
    """
    Prepara os CSVs essenciais na Bronze sem reextrair arquivos já válidos.

    Estrutura:
        data/
          bronze/
            2026-10.zip
            csv/
            manifest_extracao.json
          temp_duckdb/
            nested_zips/

    Os ZIPs originais permanecem preservados.
    """
    base = Path(base_dir).resolve()

    bronze = base / "data" / "bronze"
    pasta_csv = bronze / "csv"
    pasta_temp = base / "data" / "temp_duckdb" / "nested_zips"
    caminho_manifesto = bronze / "manifest_extracao.json"

    bronze.mkdir(parents=True, exist_ok=True)
    pasta_csv.mkdir(parents=True, exist_ok=True)
    pasta_temp.mkdir(parents=True, exist_ok=True)

    manifesto = _carregar_manifesto(caminho_manifesto)

    # Copia CSVs que já estejam diretamente na Bronze para bronze/csv,
    # sem sobrescrever arquivos existentes com o mesmo tamanho.
    for arquivo in bronze.iterdir():
        if (
            arquivo.is_file()
            and arquivo.suffix.lower() == ".csv"
            and not arquivo.name.startswith(".")
        ):
            destino = pasta_csv / arquivo.name

            if not destino.exists():
                shutil.copy2(arquivo, destino)
                LOGGER.info("CSV local copiado para a Bronze: %s", arquivo.name)

    zips = sorted(
        arquivo
        for arquivo in bronze.iterdir()
        if arquivo.is_file()
        and arquivo.suffix.lower() == ".zip"
    )

    if not zips:
        csv_existentes = [
            p for p in pasta_csv.iterdir()
            if p.is_file()
            and not p.name.startswith(".")
            and not p.name.lower().endswith(".tmp")
        ]

        if csv_existentes:
            LOGGER.info(
                "Nenhum ZIP encontrado. Reutilizando %d CSVs existentes.",
                len(csv_existentes),
            )
            return

        raise FileNotFoundError(
            f"Nenhum ZIP ou CSV encontrado em: {bronze}"
        )

    total_extraidos = 0

    for caminho_zip in zips:
        LOGGER.info("Inspecionando ZIP: %s", caminho_zip.name)

        total_extraidos += _processar_zip(
            caminho_zip=caminho_zip,
            pasta_csv=pasta_csv,
            pasta_temp=pasta_temp,
            manifesto=manifesto,
            caminho_manifesto=caminho_manifesto,
            prefixo=caminho_zip.stem,
        )

        _salvar_manifesto(caminho_manifesto, manifesto)

    csv_validos = [
        p for p in pasta_csv.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and not p.name.lower().endswith(".tmp")
    ]

    if not csv_validos:
        raise ValueError(
            "Nenhum CSV essencial foi encontrado ou extraído. "
            "Verifique a estrutura dos ZIPs."
        )

    LOGGER.info(
        "Bronze preparada. CSVs essenciais disponíveis: %d; novos arquivos extraídos: %d.",
        len(csv_validos),
        total_extraidos,
    )
    LOGGER.info("ZIPs originais preservados.")
