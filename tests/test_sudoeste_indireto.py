import io
import unittest

import pandas as pd

from app.sudoeste_indireto import OUTPUT_COLUMNS_INDIRETO, processar_sudoeste_indireto


def _to_xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return output.getvalue()


class SudoesteIndiretoFlowTests(unittest.TestCase):
    def test_fluxo_sudoeste_indireto_consolida_titulo_e_parcela(self):
        processada = pd.DataFrame(
            [
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "111.222.333-44",
                    "Titulo": "C43830700-0",
                    "Parcela": 14,
                    "Valor Titulo": 100.0,
                    "Historico": 3,
                    "Data": "20/01/2026",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "C43830700-0",
                    "Parcela": 12,
                    "Valor Titulo": 110.0,
                    "Historico": 9,
                    "Data": "21/01/2026",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "C43830700-0",
                    "Parcela": 15,
                    "Valor Titulo": 120.0,
                    "Historico": None,
                    "Data": "22/01/2026",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "C43830700-0",
                    "Parcela": 13,
                    "Valor Titulo": 130.0,
                    "Historico": None,
                    "Data": "23/01/2026",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "C43830927-4",
                    "Parcela": 11,
                    "Valor Titulo": 50.0,
                    "Historico": None,
                    "Data": "24/01/2026",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "C43830927-4",
                    "Parcela": 10,
                    "Valor Titulo": 60.0,
                    "Historico": None,
                    "Data": "25/01/2026",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "MAS",
                    "Parcela": 1,
                    "Valor Titulo": 70.0,
                    "Historico": None,
                    "Data": "26/01/2026",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "CAR",
                    "Parcela": 2,
                    "Valor Titulo": 80.0,
                    "Historico": None,
                    "Data": "27/01/2026",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "CHI",
                    "Parcela": 1,
                    "Valor Titulo": 90.0,
                    "Historico": None,
                    "Data": "28/01/2026",
                },
                {
                    "AG": "002",
                    "Conta": "67890",
                    "Associado": "Bruno Sem Match",
                    "CPF/CNPJ": "22233344455",
                    "Titulo": "C999-0",
                    "Parcela": 1,
                    "Valor Titulo": 10.0,
                    "Historico": 1,
                    "Data": "10/01/2026",
                },
                {
                    "AG": "003",
                    "Conta": "54321",
                    "Associado": "Carlos Cliente",
                    "CPF/CNPJ": "33344455566",
                    "Titulo": "C500-0",
                    "Parcela": 1,
                    "Valor Titulo": 40.0,
                    "Historico": 2,
                    "Data": "15/01/2026",
                },
                {
                    "AG": "003",
                    "Conta": "54321",
                    "Associado": "Carlos Cliente",
                    "CPF/CNPJ": "33344455566",
                    "Titulo": "C500-0",
                    "Parcela": 2,
                    "Valor Titulo": 60.0,
                    "Historico": None,
                    "Data": "16/01/2026",
                },
            ]
        )

        indireto = pd.DataFrame(
            [
                {
                    "UltimoAcionamentoData": "25/01/2026",
                    "ClienteCPFCNPJ": "111.222.333-44",
                    "SICREDI_Produto_Legado": "MAS",
                    "VencimentoMaisAntigo": "18/01/2026",
                },
                {
                    "UltimoAcionamentoData": "17/01/2026",
                    "ClienteCPFCNPJ": "333.444.555-66",
                    "SICREDI_Produto_Legado": "CHI",
                    "VencimentoMaisAntigo": "10/01/2026",
                },
            ]
        )

        saida = pd.read_excel(
            processar_sudoeste_indireto(
                _to_xlsx_bytes(processada),
                _to_xlsx_bytes(indireto),
            )
        )

        self.assertEqual(list(saida.columns), OUTPUT_COLUMNS_INDIRETO)
        self.assertNotIn("Protocolo", saida.columns.tolist())
        self.assertEqual(len(saida), 2)
        self.assertNotIn("Bruno Sem Match", saida["Associado"].tolist())

        ana = saida.loc[saida["Associado"] == "Ana Cliente"].iloc[0]
        self.assertEqual(ana["Titulo"], "C43830700-0 + C43830927-4 + Conta corrente + Cartão")
        self.assertEqual(
            ana["Parcela"],
            "(C43830700-0_12_13_14_15)(C43830927-4_10_11)(conta_1)(cartão_1)",
        )
        self.assertEqual(float(ana["Valor Título"]), 810.0)
        self.assertEqual(int(ana["Histórico"]), 3)
        self.assertEqual(ana["Data"], "20/01/2026")
        self.assertEqual(ana["Dt Ultimo Acionamento"], "25/01/2026")
        self.assertEqual(ana["Venc. Parcela"], "18/01/2026")
        self.assertEqual(int(ana["Atraso"]), 2)
        self.assertEqual(ana["Situação"], "Pagamento OK")
        self.assertTrue(pd.isna(ana["%receita"]))
        self.assertTrue(pd.isna(ana["receita"]))

        carlos = saida.loc[saida["Associado"] == "Carlos Cliente"].iloc[0]
        self.assertEqual(carlos["Titulo"], "C500-0 + Conta corrente")
        self.assertEqual(carlos["Parcela"], "(C500-0_1_2)(conta_1)")
        self.assertEqual(float(carlos["Valor Título"]), 100.0)
        self.assertEqual(carlos["Dt Ultimo Acionamento"], "17/01/2026")
        self.assertEqual(carlos["Venc. Parcela"], "10/01/2026")
        self.assertEqual(int(carlos["Atraso"]), 5)


if __name__ == "__main__":
    unittest.main()
