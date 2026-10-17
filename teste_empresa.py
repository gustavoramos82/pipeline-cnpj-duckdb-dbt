from pathlib import Path
import duckdb

def verificar_parquet_empresas():
    base_dir = Path(__file__).resolve().parent
    silver_dir = base_dir / "data" / "silver" / "parquet"
    
    # Procura todos os parquets de empresas na prata
    arquivos_empresas = list(silver_dir.glob("empresas_*.parquet"))
    
    if not arquivos_empresas:
        print("Nenhum ficheiro Parquet de empresas encontrado em:", silver_dir)
        return

    print(f"Encontrados {len(arquivos_empresas)} ficheiros de empresas. A pesquisar...")

    con = duckdb.connect()
    try:
        # Usa union_by_name para consultar todos os parquets de uma vez
        caminho_busca = str(silver_dir / "empresas_*.parquet").replace("\\", "/")
        
        query = f"""
            SELECT *
            FROM read_parquet('{caminho_busca}', union_by_name=true)
            WHERE column0 = '33592510'
        """
        
        resultado = con.execute(query.format(caminho=caminho_busca)).fetchall()
        
        if resultado:
            print("\n[SUCESSO] Empresa encontrada na camada Prata!")
            for linha in resultado:
                print(linha)
        else:
            print("\n[AVISO] O CNPJ básico '33592510' NÃO foi encontrado em nenhum ficheiro Parquet de empresas.")
            
    except Exception as e:
        print("\n[ERRO] Ocorreu um erro ao consultar os parquets:", e)
    finally:
        con.close()

if __name__ == "__main__":
    verificar_parquet_empresas()