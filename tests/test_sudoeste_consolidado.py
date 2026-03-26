import io
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from app.sudoeste_consolidado import processar_sudoeste_consolidado
from app.sudoeste_direto import processar_sudoeste_direto
from app.sudoeste_indireto import processar_sudoeste_indireto


def _to_xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return output.getvalue()


class SudoesteConsolidadoFlowTests(unittest.TestCase):
    def test_gera_duas_abas_com_resultados_iguais_aos_fluxos_existentes(self):
        processada = pd.DataFrame(
            [
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "111.222.333-44",
                    "Titulo": "C43830700-0",
                    "Parcela": 12,
                    "Valor Titulo": 100.0,
                    "Historico": 1,
                    "Data": "10/01/2026",
                    "Protocolo": "PROTO-1",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "MAS",
                    "Parcela": 1,
                    "Valor Titulo": 50.0,
                    "Historico": None,
                    "Data": "11/01/2026",
                    "Protocolo": "PROTO-1",
                },
            ]
        )

        direta = pd.DataFrame(
            [
                {
                    "A": "x",
                    "B": "x",
                    "C": "x",
                    "D": "x",
                    "E": "x",
                    "Documento": "11122233344",
                    "Produto": "Produto Direto A",
                    "DT ACIONAMENTO": "15/01/2026",
                    "Data de Vencimento": "08/01/2026",
                }
            ]
        )

        indireto = pd.DataFrame(
            [
                {
                    "UltimoAcionamentoData": "16/01/2026",
                    "ClienteCPFCNPJ": "111.222.333-44",
                    "SICREDI_Produto_Legado": "MAS",
                    "VencimentoMaisAntigo": "09/01/2026",
                }
            ]
        )

        processada_bytes = _to_xlsx_bytes(processada)
        direta_bytes = _to_xlsx_bytes(direta)
        indireto_bytes = _to_xlsx_bytes(indireto)

        arquivo_consolidado = processar_sudoeste_consolidado(
            processada_bytes,
            direta_bytes,
            indireto_bytes,
        )
        esperado_direto = pd.read_excel(processar_sudoeste_direto(processada_bytes, direta_bytes))
        esperado_indireto = pd.read_excel(processar_sudoeste_indireto(processada_bytes, indireto_bytes))

        xls = pd.ExcelFile(arquivo_consolidado)
        self.assertEqual(xls.sheet_names, ["Direto", "Indireto"])

        aba_direto = pd.read_excel(xls, "Direto")
        aba_indireto = pd.read_excel(xls, "Indireto")

        assert_frame_equal(aba_direto, esperado_direto, check_dtype=False)
        assert_frame_equal(aba_indireto, esperado_indireto, check_dtype=False)

        self.assertIn("Protocolo", aba_direto.columns.tolist())
        self.assertNotIn("Protocolo", aba_indireto.columns.tolist())


if __name__ == "__main__":
    unittest.main()
