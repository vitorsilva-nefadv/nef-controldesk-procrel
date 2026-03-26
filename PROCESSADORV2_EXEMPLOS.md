# ProcessadorV2 - Exemplos de Uso

## Via API HTTP

### usando curl (terminal/PowerShell)

```bash
curl -X POST http://localhost:8000/sudoeste-processadorv2 \
  -F "consolidada=@consolidado.xlsx" \
  -F "direta=@direto.xlsx" \
  -F "indireto=@indireto.xlsx" \
  -o resultado_processadorv2.xlsx
```

### Usando Python requests

```python
import requests

url = "http://localhost:8000/sudoeste-processadorv2"

with open("consolidado.xlsx", "rb") as f_consolidada, \
     open("direto.xlsx", "rb") as f_direta, \
     open("indireto.xlsx", "rb") as f_indireto:
    
    files = {
        "consolidada": f_consolidada,
        "direta": f_direta,
        "indireto": f_indireto,
    }
    
    response = requests.post(url, files=files)
    
    with open("resultado_processadorv2.xlsx", "wb") as f:
        f.write(response.content)

print("Processamento concluído!")
```

## Via Python (importação direta)

### Uso Básico

```python
from app.sudoeste_processadorv2 import processar_sudoeste_processadorv2

# Ler os arquivos Excel
with open("consolidado.xlsx", "rb") as f:
    consolidada = f.read()

with open("direto.xlsx", "rb") as f:
    direta = f.read()

with open("indireto.xlsx", "rb") as f:
    indireto = f.read()

# Processar
resultado = processar_sudoeste_processadorv2(consolidada, direta, indireto)

# Salvar resultado
with open("resultado_processadorv2.xlsx", "wb") as f:
    f.write(resultado.getvalue())

print("Processamento concluído!")
```

### Uso com DataFrames

```python
import pandas as pd
from app.sudoeste_processadorv2 import processar_sudoeste_processadorv2
import io

# Criar DataFrames (exemple)
consolidada_df = pd.DataFrame({
    "AG": ["001", "002"],
    "Conta": ["12345", "54321"],
    "Associado": ["Cliente A", "Cliente B"],
    "CPF/CNPJ": ["111.222.333-44", "222.333.444-55"],
    "Titulo": ["C43830700-0", "C43830700-1"],
    "Parcela": [1, 1],
    "Valor Título": [100.0, 200.0],
    "Data": ["10/01/2026", "11/01/2026"],
})

direta_df = pd.DataFrame({
    "CPF/CNPJ": ["111.222.333-44"],
    "Produto": ["Contrato Direto"],
    "DT ACIONAMENTO": ["05/01/2026"],
    "Venc. Parcela": ["20/01/2026"],
})

indireto_df = pd.DataFrame({
    "CPF/CNPJ": ["222.333.444-55"],
    "Produto Legado": ["Contrato Indireto"],
    "Dt Ultimo Acionamento": ["07/01/2026"],
    "Venc. Parcela": ["22/01/2026"],
})

# Converter para bytes
def df_para_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

consolidada_bytes = df_para_excel_bytes(consolidada_df)
direta_bytes = df_para_excel_bytes(direta_df)
indireto_bytes = df_para_excel_bytes(indireto_df)

# Processar
resultado = processar_sudoeste_processadorv2(consolidada_bytes, direta_bytes, indireto_bytes)

# Ler resultado
resultado_df = pd.read_excel(resultado, sheet_name=None)

print("Clientes em Direto:")
print(resultado_df["Direto"])
print("\nClientes em Indireto:")
print(resultado_df["Indireto"])
```

## Iniciando o Servidor

```bash
# Na raiz do projeto
python main.py

# Ou, se preferir porta diferente:
# python -m uvicorn app.api:app --host 127.0.0.1 --port 8001
```

## Testando o Processador

```bash
# Rodar todos os testes
python -m pytest tests/test_sudoeste_processadorv2.py -v

# Rodar um teste específico
python -m pytest tests/test_sudoeste_processadorv2.py::SudoesteProcessadorV2Tests::test_filtra_consolidado_deixando_apenas_clientes_em_direto_ou_indireto -v
```

## O que o ProcessadorV2 faz

1. ✅ Lê consolidado (clientes que PAGARAM)
2. ✅ Lê direto e indireto
3. ✅ Normaliza todos os CPF/CNPJs (remove formatação)
4. ✅ Para cada cliente no consolidado, verifica:
   - Existe em Direto? → Adiciona na aba "Direto"
   - Não existe em Direto, mas existe em Indireto? → Adiciona na aba "Indireto"
   - Não existe em nenhum? → Descarta
5. ✅ Exporta Excel com os clientes filtrados em 2 abas

## Colunas Reconhecidas

### Consolidada (Obrigatória)
- CPF/CNPJ (pode ser: "CPF/CNPJ", "CPF CNPJ", "CPF", "CNPJ")

### Consolidada (Opcionais - preservadas na saída)
- AG / Agencia
- Conta / Conta Corrente
- Associado / Nome / Razão Social
- Titulo / Título
- Parcela / N Parcela
- Valor Título / Valor do Titulo / Valor R$
- Historico / Histórico
- Data / Data Pagamento

**Qualquer outra coluna na consolidada será preservada após o filtro!**

### Direta e Indireto (Obrigatória)
- CPF/CNPJ (pode ser: "CPF/CNPJ", "CPF CNPJ", "CPF", "CNPJ")

**Nota**: Os dados de Direta e Indireto são usados APENAS para identificar quais CPF/CNPJs devem ser incluídos. Os dados mantidos na saída vêm 100% do consolidado.

## Exemplo Prático

**Consolidado:**
- Cliente A: CPF 111.222.333-44
- Cliente B: CPF 222.333.444-55
- Cliente C: CPF 333.444.555-66
- Cliente D: CPF 444.555.666-77

**Direto:**
- CPF 111.222.333-44 ← Encontrado

**Indireto:**
- CPF 222.333.444-55 ← Encontrado

**Resultado Final:**
- Aba "Direto": Cliente A (com todos seus dados originais)
- Aba "Indireto": Cliente B (com todos seus dados originais)
- Cliente C e D são descartados (não estão em nenhum dos dois)
