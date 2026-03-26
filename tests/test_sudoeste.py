import io
import unittest

import pandas as pd

from app.sudoeste import (
    BASE_STATUS_AMBIGUOUS,
    BASE_STATUS_CONFIRMED,
    BASE_STATUS_MISSING,
    DENODO_STATUS_AMBIGUOUS,
    DENODO_STATUS_CONFIRMED,
    DENODO_STATUS_MISSING,
    _classify_title,
    _normalize_contract,
    diagnosticar_sudoeste,
    exportar_diagnostico_sudoeste,
    processar_sudoeste,
    processar_sudoeste_com_diagnostico_e_resumo,
    resumir_execucao_sudoeste,
)


def _to_xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return output.getvalue()


def _cenario_principal() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = pd.DataFrame(
        [
            {
                "AG": "1001",
                "Conta": "9001",
                "ASSOCIADO": "Joao da Silva",
                "CPF": "123.456.789-00",
                "N do Contrato": "C57020042-0",
                "N Parcela": 1,
                "Vencimento": "15/03/2026",
            },
            {
                "AG": "1002",
                "Conta": "9002",
                "ASSOCIADO": "Maria Souza",
                "CPF": "111.222.333-44",
                "N do Contrato": "Cartoes Master",
                "N Parcela": 2,
                "Vencimento": "16/03/2026",
            },
            {
                "AG": None,
                "Conta": None,
                "ASSOCIADO": "Carlos Lima",
                "CPF": "555.666.777-88",
                "N do Contrato": "Inadimplencia Juros Adiantamento",
                "N Parcela": 3,
                "Vencimento": "17/03/2026",
            },
            {
                "AG": "1003",
                "Conta": "9003",
                "ASSOCIADO": "Pedro A",
                "CPF": "222.333.444-55",
                "N do Contrato": "C99999999-0",
                "N Parcela": 1,
                "Vencimento": "18/03/2026",
            },
            {
                "AG": "1004",
                "Conta": "9004",
                "ASSOCIADO": "Pedro B",
                "CPF": "222.333.444-55",
                "N do Contrato": "C99999999-0",
                "N Parcela": 1,
                "Vencimento": "19/03/2026",
            },
        ]
    )
    recebimento = pd.DataFrame(
        [
            {
                "AG": "1001",
                "Conta": "9001",
                "Associado": "Joao da Silva",
                "CPF/CNPJ": "12345678900",
                "Titulo": "C57020042-0",
                "Parcela": 1,
                "Valor Titulo": 100.5,
                "Historico": 1,
                "Data": "10/03/2026",
            },
            {
                "AG": "1002",
                "Conta": "9002",
                "Associado": "Maria Souza",
                "CPF/CNPJ": "11122233344",
                "Titulo": "MAS",
                "Parcela": 2,
                "Valor Titulo": 50.0,
                "Historico": 2,
                "Data": "09/03/2026",
            },
            {
                "AG": None,
                "Conta": None,
                "Associado": "Carlos Lima",
                "CPF/CNPJ": "55566677788",
                "Titulo": "CHI",
                "Parcela": 3,
                "Valor Titulo": 75.0,
                "Historico": 3,
                "Data": "08/03/2026",
            },
            {
                "AG": "1003",
                "Conta": "9003",
                "Associado": "Pedro",
                "CPF/CNPJ": "22233344455",
                "Titulo": "C99999999-0",
                "Parcela": 1,
                "Valor Titulo": 80.0,
                "Historico": 4,
                "Data": "07/03/2026",
            },
            {
                "AG": "1005",
                "Conta": "9005",
                "Associado": "Ana Pereira",
                "CPF/CNPJ": "99900011122",
                "Titulo": "C0001-0",
                "Parcela": 1,
                "Valor Titulo": 25.0,
                "Historico": "",
                "Data": "06/03/2026",
            },
            {
                "AG": "1006",
                "Conta": "9006",
                "Associado": "Linha Ignorada",
                "CPF/CNPJ": "00000000000",
                "Titulo": "C1111-0",
                "Parcela": 1,
                "Valor Titulo": 12.0,
                "Historico": 9,
                "Data": "05/03/2026",
            },
        ]
    )
    denodo = pd.DataFrame(
        [
            {
                "protocolo": "PROTO-1",
                "cpf_cnpj_formatado": "123.456.789-00",
                "solucao_associada": "C57020042-0",
            },
            {
                "protocolo": "PROTO-2",
                "cpf_cnpj_formatado": "111.222.333-44",
                "solucao_associada": "Cartao Visa Empresarial",
            },
            {
                "protocolo": "PROTO-4",
                "cpf_cnpj_formatado": "222.333.444-55",
                "solucao_associada": "C99999999-0",
            },
        ]
    )
    return base, recebimento, denodo


class SudoesteFlowTests(unittest.TestCase):
    def test_normaliza_contrato_alfanumerico(self):
        self.assertEqual(_normalize_contract("C57020042-0"), "C570200420")
        self.assertEqual(_normalize_contract("C46220228-0"), "C462202280")

    def test_classifica_abreviacoes_e_familias(self):
        self.assertEqual(_classify_title("MAS").kind, "card")
        self.assertEqual(_classify_title("CAR").kind, "card")
        self.assertEqual(_classify_title("CHI").kind, "chi")
        self.assertEqual(_classify_title("Cartoes Master").key, "cartao")
        self.assertEqual(_classify_title("C33822210-0").key, "C338222100")

    def test_fluxo_oficial_diagnostico_e_resumo(self):
        base, recebimento, denodo = _cenario_principal()

        resultado, diagnostico, resumo = processar_sudoeste_com_diagnostico_e_resumo(
            _to_xlsx_bytes(base),
            _to_xlsx_bytes(recebimento),
            _to_xlsx_bytes(denodo),
        )
        saida = pd.read_excel(resultado)

        self.assertEqual(
            list(saida.columns),
            [
                "AG",
                "Conta",
                "Associado",
                "CPF/CNPJ",
                "Titulo",
                "Parcela",
                "Valor Título",
                "Histórico",
                "Data",
                "Atraso",
                "%receita",
                "receita",
                "Dt Ultimo Acionamento",
                "Situação",
                "Venc. Parcela",
                "Protocolo",
            ],
        )
        self.assertEqual(len(saida), 5)
        self.assertEqual(saida.loc[0, "Protocolo"], "PROTO-1")
        self.assertEqual(saida.loc[1, "Protocolo"], "PROTO-2")
        self.assertTrue(pd.isna(saida.loc[2, "Protocolo"]))
        self.assertEqual(saida.loc[3, "Protocolo"], "PROTO-4")
        self.assertTrue(pd.isna(saida.loc[4, "Protocolo"]))
        self.assertEqual(saida.loc[0, "Venc. Parcela"], "15/03/2026")
        self.assertTrue(pd.isna(saida.loc[3, "Venc. Parcela"]))
        self.assertTrue(pd.isna(saida.loc[4, "Venc. Parcela"]))

        self.assertEqual(
            list(diagnostico.columns),
            [
                "Linha Recebimento",
                "Associado",
                "CPF/CNPJ",
                "Titulo",
                "Parcela",
                "Tipo Titulo Recebimento",
                "Chave Normalizada Recebimento",
                "CPF Normalizado",
                "Parcela Normalizada",
                "Associado Normalizado",
                "Status Base",
                "Detalhe Base",
                "Linha Base",
                "Chave Base Selecionada",
                "Status Denodo",
                "Detalhe Denodo",
                "Chave Denodo Selecionada",
                "Linhas Denodo",
                "Protocolos Denodo",
                "Protocolo Resultado",
            ],
        )
        self.assertEqual(
            diagnostico["Status Base"].tolist(),
            [BASE_STATUS_CONFIRMED, BASE_STATUS_CONFIRMED, BASE_STATUS_CONFIRMED, BASE_STATUS_AMBIGUOUS, BASE_STATUS_MISSING],
        )
        self.assertEqual(
            diagnostico["Status Denodo"].tolist(),
            [DENODO_STATUS_CONFIRMED, DENODO_STATUS_CONFIRMED, DENODO_STATUS_MISSING, DENODO_STATUS_CONFIRMED, DENODO_STATUS_MISSING],
        )
        self.assertIn("tipo=contract", diagnostico.loc[0, "Chave Base Selecionada"])
        self.assertIn("cpf=12345678900", diagnostico.loc[0, "Chave Denodo Selecionada"])

        resumo_dict = dict(zip(resumo["Indicador"], resumo["Valor"]))
        self.assertEqual(resumo_dict["total de linhas recebimento consideradas"], 5)
        self.assertEqual(resumo_dict["total de linhas ignoradas por historico"], 1)
        self.assertEqual(resumo_dict["total com match base confirmado"], 3)
        self.assertEqual(resumo_dict["total sem match base"], 1)
        self.assertEqual(resumo_dict["total match base ambiguo"], 1)
        self.assertEqual(resumo_dict["total com protocolo confirmado"], 3)
        self.assertEqual(resumo_dict["total sem match denodo"], 2)
        self.assertEqual(resumo_dict["total match denodo ambiguo"], 0)

    def test_denodo_ambiguo_aparece_no_resumo(self):
        base = pd.DataFrame(
            [
                {
                    "ASSOCIADO": "Maria Souza",
                    "CPF": "111.222.333-44",
                    "N do Contrato": "Cartoes Master",
                    "N Parcela": 2,
                }
            ]
        )
        recebimento = pd.DataFrame(
            [
                {
                    "Associado": "Maria Souza",
                    "CPF/CNPJ": "11122233344",
                    "Titulo": "MAS",
                    "Parcela": 2,
                    "Valor Titulo": 50.0,
                    "Historico": 1,
                    "Data": "09/03/2026",
                }
            ]
        )
        denodo = pd.DataFrame(
            [
                {
                    "protocolo": "PROTO-A",
                    "cpf_cnpj_formatado": "111.222.333-44",
                    "solucao_associada": "Cartao Visa Empresarial",
                },
                {
                    "protocolo": "PROTO-B",
                    "cpf_cnpj_formatado": "111.222.333-44",
                    "solucao_associada": "Cartoes Master",
                },
            ]
        )

        saida = pd.read_excel(
            processar_sudoeste(
                _to_xlsx_bytes(base),
                _to_xlsx_bytes(recebimento),
                _to_xlsx_bytes(denodo),
            )
        )
        diagnostico = diagnosticar_sudoeste(
            _to_xlsx_bytes(base),
            _to_xlsx_bytes(recebimento),
            _to_xlsx_bytes(denodo),
        )
        resumo = resumir_execucao_sudoeste(
            _to_xlsx_bytes(base),
            _to_xlsx_bytes(recebimento),
            _to_xlsx_bytes(denodo),
        )

        self.assertTrue(pd.isna(saida.loc[0, "Protocolo"]))
        self.assertEqual(diagnostico.loc[0, "Status Denodo"], DENODO_STATUS_AMBIGUOUS)
        resumo_dict = dict(zip(resumo["Indicador"], resumo["Valor"]))
        self.assertEqual(resumo_dict["total match denodo ambiguo"], 1)
        self.assertEqual(resumo_dict["total com protocolo confirmado"], 0)

    def test_exporta_diagnostico_com_duas_abas(self):
        base, recebimento, denodo = _cenario_principal()
        arquivo = exportar_diagnostico_sudoeste(
            _to_xlsx_bytes(base),
            _to_xlsx_bytes(recebimento),
            _to_xlsx_bytes(denodo),
        )

        xls = pd.ExcelFile(arquivo)
        self.assertEqual(xls.sheet_names, ["Resumo", "Diagnostico"])

        resumo = pd.read_excel(xls, "Resumo")
        diagnostico = pd.read_excel(xls, "Diagnostico")
        self.assertEqual(list(resumo.columns), ["Indicador", "Valor"])
        self.assertIn("Status Base", diagnostico.columns)
        self.assertIn("Chave Denodo Selecionada", diagnostico.columns)


if __name__ == "__main__":
    unittest.main()
