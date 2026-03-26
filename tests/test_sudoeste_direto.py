import io
import unittest

import pandas as pd

from app.sudoeste_direto import OUTPUT_COLUMNS_DIRETO, processar_sudoeste_direto


def _to_xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return output.getvalue()


class SudoesteDiretoFlowTests(unittest.TestCase):
    def test_fluxo_sudoeste_direto_consolida_match_e_calcula_campos(self):
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
                    "Protocolo": "PROTO-UNICO",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "C43830700-0",
                    "Parcela": 13,
                    "Valor Titulo": 200.0,
                    "Historico": 2,
                    "Data": "11/01/2026",
                    "Protocolo": "PROTO-UNICO",
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
                    "Data": "12/01/2026",
                    "Protocolo": "PROTO-UNICO",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "CAR",
                    "Parcela": 2,
                    "Valor Titulo": 30.0,
                    "Historico": None,
                    "Data": "13/01/2026",
                    "Protocolo": "PROTO-UNICO",
                },
                {
                    "AG": "001",
                    "Conta": "12345",
                    "Associado": "Ana Cliente",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "CHI",
                    "Parcela": 1,
                    "Valor Titulo": 25.0,
                    "Historico": None,
                    "Data": "14/01/2026",
                    "Protocolo": "PROTO-UNICO",
                },
                {
                    "AG": "002",
                    "Conta": "67890",
                    "Associado": "Bruno Sem Match",
                    "CPF/CNPJ": "22233344455",
                    "Titulo": "C999-0",
                    "Parcela": 1,
                    "Valor Titulo": 80.0,
                    "Historico": 9,
                    "Data": "05/01/2026",
                    "Protocolo": "PROTO-SEM-MATCH",
                },
                {
                    "AG": "003",
                    "Conta": "54321",
                    "Associado": "Carlos Cliente",
                    "CPF/CNPJ": "333.444.555-66",
                    "Titulo": "C100-0",
                    "Parcela": 1,
                    "Valor Titulo": 40.0,
                    "Historico": 4,
                    "Data": "08/01/2026",
                    "Protocolo": "PROTO-A",
                },
                {
                    "AG": "003",
                    "Conta": "54321",
                    "Associado": "Carlos Cliente",
                    "CPF/CNPJ": "33344455566",
                    "Titulo": "C101-0",
                    "Parcela": 2,
                    "Valor Titulo": 60.0,
                    "Historico": 7,
                    "Data": "09/01/2026",
                    "Protocolo": "PROTO-B",
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
                },
                {
                    "A": "x",
                    "B": "x",
                    "C": "x",
                    "D": "x",
                    "E": "x",
                    "Documento": "33344455566",
                    "Produto": "Produto Direto C",
                    "DT ACIONAMENTO": "10/01/2026",
                    "Data de Vencimento": "07/01/2026",
                },
            ]
        )

        arquivo_saida = processar_sudoeste_direto(
            _to_xlsx_bytes(processada),
            _to_xlsx_bytes(direta),
        )
        saida = pd.read_excel(arquivo_saida)

        self.assertEqual(list(saida.columns), OUTPUT_COLUMNS_DIRETO)
        self.assertEqual(len(saida), 2)
        self.assertNotIn("Bruno Sem Match", saida["Associado"].tolist())

        ana = saida.loc[saida["Associado"] == "Ana Cliente"].iloc[0]
        self.assertEqual(ana["Titulo"], "Produto Direto A")
        self.assertEqual(ana["Parcela"], "(C43830700-0_12_13) (cartao_1) (conta_1)")
        self.assertEqual(float(ana["Valor Título"]), 405.0)
        self.assertEqual(int(ana["Histórico"]), 1)
        self.assertEqual(ana["Data"], "10/01/2026")
        self.assertEqual(ana["Dt Ultimo Acionamento"], "15/01/2026")
        self.assertEqual(ana["Venc. Parcela"], "08/01/2026")
        self.assertEqual(int(ana["Atraso"]), 2)
        self.assertEqual(ana["Situação"], "Pagamento OK")
        self.assertEqual(ana["Protocolo"], "PROTO-UNICO")
        self.assertTrue(pd.isna(ana["%receita"]))
        self.assertTrue(pd.isna(ana["receita"]))

        carlos = saida.loc[saida["Associado"] == "Carlos Cliente"].iloc[0]
        self.assertEqual(carlos["Titulo"], "Produto Direto C")
        self.assertEqual(carlos["Parcela"], "(C100-0_1) (C101-0_2)")
        self.assertEqual(float(carlos["Valor Título"]), 100.0)
        self.assertEqual(carlos["Data"], "08/01/2026")
        self.assertEqual(carlos["Venc. Parcela"], "07/01/2026")
        self.assertEqual(int(carlos["Atraso"]), 1)
        self.assertTrue(pd.isna(carlos["Protocolo"]))

    def test_regra_data_primeiro_registro_e_protocolo_ambiguo(self):
        processada = pd.DataFrame(
            [
                {
                    "Associado": "Cliente Teste",
                    "CPF/CNPJ": "99988877766",
                    "Titulo": "C200-0",
                    "Parcela": 3,
                    "Valor Titulo": 10.0,
                    "Historico": 8,
                    "Data": "20/02/2026",
                    "Protocolo": "PROTO-1",
                },
                {
                    "Associado": "Cliente Teste",
                    "CPF/CNPJ": "99988877766",
                    "Titulo": "C200-0",
                    "Parcela": 4,
                    "Valor Titulo": 30.0,
                    "Historico": 1,
                    "Data": "10/02/2026",
                    "Protocolo": "PROTO-2",
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
                    "Documento": "999.888.777-66",
                    "Produto": "Produto Teste",
                    "DT ACIONAMENTO": "21/02/2026",
                    "Vencimento": "15/02/2026",
                }
            ]
        )

        saida = pd.read_excel(
            processar_sudoeste_direto(
                _to_xlsx_bytes(processada),
                _to_xlsx_bytes(direta),
            )
        )

        self.assertEqual(len(saida), 1)
        linha = saida.iloc[0]
        self.assertEqual(linha["Data"], "20/02/2026")
        self.assertEqual(int(linha["Atraso"]), 5)
        self.assertTrue(pd.isna(linha["Protocolo"]))


if __name__ == "__main__":
    unittest.main()
