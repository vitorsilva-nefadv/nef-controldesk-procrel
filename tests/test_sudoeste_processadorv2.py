import io
import unittest

import pandas as pd

from app.sudoeste_processadorv2 import processar_sudoeste_processadorv2


def _to_xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return output.getvalue()


class SudoesteProcessadorV2Tests(unittest.TestCase):
    def test_filtra_consolidado_deixando_apenas_clientes_em_direto_ou_indireto(self):
        """Testa que o processadorv2 filtra o consolidado mantendo apenas os que estão em direto OU indireto"""
        # Consolidado com 4 clientes
        consolidada = pd.DataFrame(
            [
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Cliente A",
                    "CPF/CNPJ": "111.222.333-44",
                    "Titulo": "C43830700-0",
                    "Parcela": 1,
                    "Valor Título": 100.0,
                    "Data": "10/01/2026",
                },
                {
                    "AG": "002",
                    "Conta": "54321",
                    "Associado": "Cliente B",
                    "CPF/CNPJ": "222.333.444-55",
                    "Titulo": "C43830700-1",
                    "Parcela": 1,
                    "Valor Título": 200.0,
                    "Data": "11/01/2026",
                },
                {
                    "AG": "003",
                    "Conta": "99999",
                    "Associado": "Cliente C",
                    "CPF/CNPJ": "333.444.555-66",
                    "Titulo": "C43830700-2",
                    "Parcela": 1,
                    "Valor Título": 300.0,
                    "Data": "12/01/2026",
                },
                {
                    "AG": "004",
                    "Conta": "88888",
                    "Associado": "Cliente D",
                    "CPF/CNPJ": "444.555.666-77",
                    "Titulo": "C43830700-3",
                    "Parcela": 1,
                    "Valor Título": 400.0,
                    "Data": "13/01/2026",
                },
            ]
        )

        # Direta com 2 clientes (A e B)
        direta = pd.DataFrame(
            [
                {
                    "CPF/CNPJ": "111.222.333-44",
                    "Produto": "Contrato Direto A",
                    "DT ACIONAMENTO": "05/01/2026",
                    "Venc. Parcela": "20/01/2026",
                },
                {
                    "CPF/CNPJ": "222.333.444-55",
                    "Produto": "Contrato Direto B",
                    "DT ACIONAMENTO": "06/01/2026",
                    "Venc. Parcela": "21/01/2026",
                },
            ]
        )

        # Indireta com 1 cliente (C)
        indireto = pd.DataFrame(
            [
                {
                    "CPF/CNPJ": "333.444.555-66",
                    "Produto Legado": "Contrato Indireto C",
                    "Dt Ultimo Acionamento": "07/01/2026",
                    "Venc. Parcela": "22/01/2026",
                },
            ]
        )

        # Cliente D não está em nenhum, deve ser descartado

        consolidada_bytes = _to_xlsx_bytes(consolidada)
        direta_bytes = _to_xlsx_bytes(direta)
        indireto_bytes = _to_xlsx_bytes(indireto)

        resultado = processar_sudoeste_processadorv2(consolidada_bytes, direta_bytes, indireto_bytes)

        # Ler resultado
        resultado_df = pd.read_excel(resultado, sheet_name=None)
        direto_result = resultado_df["Direto"]
        indireto_result = resultado_df["Indireto"]

        # Validações
        # Direto deve ter 2 linhas (A e B)
        assert len(direto_result) == 2, f"Esperado 2 linhas em Direto, obtido {len(direto_result)}"
        assert direto_result.iloc[0]["Associado"] == "Cliente A"
        assert direto_result.iloc[1]["Associado"] == "Cliente B"

        # Indireto deve ter 1 linha (C)
        assert len(indireto_result) == 1, f"Esperado 1 linha em Indireto, obtido {len(indireto_result)}"
        assert indireto_result.iloc[0]["Associado"] == "Cliente C"

        # Cliente D não deve estar em nenhum lugar
        clientes_totais = len(direto_result) + len(indireto_result)
        assert clientes_totais == 3, f"Esperado 3 clientes no total (A, B, C), obtido {clientes_totais}"

    def test_descarta_cliente_sem_cpf(self):
        """Testa que clientes sem CPF são descartados"""
        consolidada = pd.DataFrame(
            [
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Cliente Sem CPF",
                    "CPF/CNPJ": None,
                    "Titulo": "C43830700-0",
                    "Parcela": 1,
                    "Valor Título": 100.0,
                    "Data": "10/01/2026",
                },
            ]
        )

        direta = pd.DataFrame(
            [
                {
                    "CPF/CNPJ": "111.222.333-44",
                    "Produto": "Contrato Direto",
                    "DT ACIONAMENTO": "05/01/2026",
                    "Venc. Parcela": "20/01/2026",
                },
            ]
        )

        indireto = pd.DataFrame(
            [
                {
                    "CPF/CNPJ": "222.333.444-55",
                    "Produto Legado": "Contrato Indireto",
                    "Dt Ultimo Acionamento": "07/01/2026",
                    "Venc. Parcela": "22/01/2026",
                },
            ]
        )

        consolidada_bytes = _to_xlsx_bytes(consolidada)
        direta_bytes = _to_xlsx_bytes(direta)
        indireto_bytes = _to_xlsx_bytes(indireto)

        resultado = processar_sudoeste_processadorv2(consolidada_bytes, direta_bytes, indireto_bytes)

        resultado_df = pd.read_excel(resultado, sheet_name=None)
        direto_result = resultado_df["Direto"]
        indireto_result = resultado_df["Indireto"]

        # Ambas abas devem estar vazias
        assert len(direto_result) == 0, f"Esperado 0 linhas em Direto, obtido {len(direto_result)}"
        assert len(indireto_result) == 0, f"Esperado 0 linhas em Indireto, obtido {len(indireto_result)}"

    def test_normaliza_cpf_cnpj_antes_de_compara(self):
        """Testa que CPF/CNPJs são normalizados antes de comparar"""
        consolidada = pd.DataFrame(
            [
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Cliente A",
                    "CPF/CNPJ": "111.222.333-44",  # Com formatação
                    "Titulo": "C43830700-0",
                    "Parcela": 1,
                    "Valor Título": 100.0,
                    "Data": "10/01/2026",
                },
            ]
        )

        direta = pd.DataFrame(
            [
                {
                    "CPF/CNPJ": "11122233344",  # Sem formatação
                    "Produto": "Contrato Direto",
                    "DT ACIONAMENTO": "05/01/2026",
                    "Venc. Parcela": "20/01/2026",
                },
            ]
        )

        indireto = pd.DataFrame(
            [
                {
                    "CPF/CNPJ": "222.333.444-55",
                    "Produto Legado": "Contrato Indireto",
                    "Dt Ultimo Acionamento": "07/01/2026",
                    "Venc. Parcela": "22/01/2026",
                },
            ]
        )

        consolidada_bytes = _to_xlsx_bytes(consolidada)
        direta_bytes = _to_xlsx_bytes(direta)
        indireto_bytes = _to_xlsx_bytes(indireto)

        resultado = processar_sudoeste_processadorv2(consolidada_bytes, direta_bytes, indireto_bytes)

        resultado_df = pd.read_excel(resultado, sheet_name=None)
        direto_result = resultado_df["Direto"]

        # Cliente A deve aparecer em Direto mesmo com formatações diferentes
        assert len(direto_result) == 1, f"Esperado 1 linha em Direto, obtido {len(direto_result)}"
        assert direto_result.iloc[0]["Associado"] == "Cliente A"


if __name__ == "__main__":
    unittest.main()
