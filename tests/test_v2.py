import pandas as pd

def processar_sudoeste_processado_v2(caminho_arquivo: str) -> pd.DataFrame:
    return pd.read_excel(caminho_arquivo)

print(processar_sudoeste_processado_v2(
    'excel_teste/sudoeste_direto_processado.xlsx'
))