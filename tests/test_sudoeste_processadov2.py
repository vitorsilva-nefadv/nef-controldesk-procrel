import io
import unittest

import pandas as pd

from app.sudoeste_processadov2.matching import indexar_produto, linha_inicial_tem_match
from app.sudoeste_processadov2.parser import (
    classificar_titulo_inicial,
    extrair_blocos_contrato_parcelas,
    normalizar_cpf_cnpj,
    produto_deve_ser_ignorado,
    produto_eh_cartao,
    produto_eh_chi,
)
from app.sudoeste_processadov2.processador import (
    processar_sudoeste_processadov2,
    processar_sudoeste_processadov2_frames,
)


def _to_xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return output.getvalue()


class SudoesteProcessadoV2ParserTests(unittest.TestCase):
    def test_normalizar_cpf_cnpj_remove_tudo_que_nao_for_numero(self):
        self.assertEqual(normalizar_cpf_cnpj("111.222.333-44"), "11122233344")
        self.assertEqual(normalizar_cpf_cnpj("12.345.678/0001-90"), "12345678000190")

    def test_classificar_titulo_inicial(self):
        self.assertEqual(classificar_titulo_inicial("C43830080-3"), "contrato")
        self.assertEqual(classificar_titulo_inicial("MAS"), "cartao")
        self.assertEqual(classificar_titulo_inicial("CAR"), "cartao")
        self.assertEqual(classificar_titulo_inicial("CHI"), "chi")
        self.assertEqual(classificar_titulo_inicial("OUTRO"), "ignorar")

    def test_produto_cartao(self):
        self.assertTrue(produto_eh_cartao("cartao + conta corrente"))
        self.assertTrue(produto_eh_cartao("MAS"))
        self.assertFalse(produto_eh_cartao("capital de giro"))

    def test_produto_chi(self):
        self.assertTrue(produto_eh_chi("chi"))
        self.assertTrue(produto_eh_chi("inadimplencia"))
        self.assertTrue(produto_eh_chi("cheque especial"))
        self.assertTrue(produto_eh_chi("conta corrente"))
        self.assertFalse(produto_eh_chi("capital de giro"))

    def test_parser_blocos_contrato_parcelas_caso_1(self):
        blocos = extrair_blocos_contrato_parcelas(
            "C466302629_15_16_17_18_19_20_21 + cartao + conta corrente"
        )
        self.assertEqual(len(blocos), 1)
        self.assertEqual(blocos[0]["contrato_norm"], "C466302629")
        self.assertEqual(blocos[0]["parcelas"], {"15", "16", "17", "18", "19", "20", "21"})

    def test_parser_blocos_contrato_parcelas_caso_2(self):
        blocos = extrair_blocos_contrato_parcelas(
            "C138304510_34+35+36+37 + C438310906_2+3+4+5+6 + Conta corrente"
        )
        self.assertEqual(len(blocos), 2)
        self.assertEqual(blocos[0]["contrato_norm"], "C138304510")
        self.assertEqual(blocos[0]["parcelas"], {"34", "35", "36", "37"})
        self.assertEqual(blocos[1]["contrato_norm"], "C438310906")
        self.assertEqual(blocos[1]["parcelas"], {"2", "3", "4", "5", "6"})

    def test_parser_blocos_contrato_parcelas_caso_3(self):
        blocos = extrair_blocos_contrato_parcelas("C48930384-2_12_13_14_15_16+conta corrente")
        self.assertEqual(len(blocos), 1)
        self.assertEqual(blocos[0]["contrato_norm"], "C489303842")
        self.assertEqual(blocos[0]["parcelas"], {"12", "13", "14", "15", "16"})

    def test_parser_blocos_contrato_parcelas_caso_4(self):
        blocos = extrair_blocos_contrato_parcelas("cartao + conta corrente + C488309499_10_11_12_13_14_15")
        self.assertEqual(len(blocos), 1)
        self.assertEqual(blocos[0]["contrato_norm"], "C488309499")
        self.assertEqual(blocos[0]["parcelas"], {"10", "11", "12", "13", "14", "15"})

    def test_ignora_capital_de_giro(self):
        self.assertTrue(produto_deve_ser_ignorado("capital de giro"))
        self.assertFalse(produto_deve_ser_ignorado("inadimplencia"))


class SudoesteProcessadoV2MatchingTests(unittest.TestCase):
    def test_match_contrato(self):
        row = {"cpf": "11122233344", "titulo": "C48930384-2", "parcela": "14"}
        candidatos = [indexar_produto("C48930384-2_12_13_14_15_16+conta corrente")]
        self.assertTrue(linha_inicial_tem_match(row, candidatos))

    def test_match_cartao(self):
        row = {"cpf": "11122233344", "titulo": "MAS", "parcela": "1"}
        candidatos = [indexar_produto("cartao + conta corrente")]
        self.assertTrue(linha_inicial_tem_match(row, candidatos))

    def test_match_chi(self):
        row = {"cpf": "11122233344", "titulo": "CHI", "parcela": "1"}
        candidatos = [indexar_produto("inadimplencia")]
        self.assertTrue(linha_inicial_tem_match(row, candidatos))

    def test_nao_match_quando_so_capital_de_giro(self):
        row = {"cpf": "11122233344", "titulo": "CHI", "parcela": "1"}
        candidatos = [indexar_produto("capital de giro")]
        self.assertFalse(linha_inicial_tem_match(row, candidatos))


class SudoesteProcessadoV2FlowTests(unittest.TestCase):
    def test_filtra_inicial_preservando_colunas_em_duas_saidas(self):
        inicial = pd.DataFrame(
            [
                {"CPF/CNPJ": "111.222.333-44", "Titulo": "C48930384-2", "Parcela": 14, "Valor Titulo": 100, "Extra": "A"},
                {"CPF/CNPJ": "11122233344", "Titulo": "MAS", "Parcela": 1, "Valor Titulo": 200, "Extra": "B"},
                {"CPF/CNPJ": "55566677788", "Titulo": "CHI", "Parcela": 1, "Valor Titulo": 300, "Extra": "C"},
                {"CPF/CNPJ": "99900011122", "Titulo": "C00000000-1", "Parcela": 99, "Valor Titulo": 400, "Extra": "D"},
            ]
        )
        direto = pd.DataFrame(
            [
                {"CPF/CNPJ": "11122233344", "Produto": "C48930384-2_12_13_14_15_16"},
                {"CPF/CNPJ": "11122233344", "Produto": "cartao"},
                {"CPF/CNPJ": "55566677788", "Produto": "capital de giro"},
            ]
        )
        indireto = pd.DataFrame(
            [
                {"ClienteCPFCNPJ": "555.666.777-88", "SICREDI_Produto_Legado": "conta corrente"},
            ]
        )

        saida_direto, saida_indireto = processar_sudoeste_processadov2_frames(
            _to_xlsx_bytes(inicial),
            _to_xlsx_bytes(direto),
            _to_xlsx_bytes(indireto),
        )

        self.assertEqual(list(saida_direto.columns), list(inicial.columns))
        self.assertEqual(list(saida_indireto.columns), list(inicial.columns))
        self.assertEqual(saida_direto["Extra"].tolist(), ["A", "B"])
        self.assertEqual(saida_indireto["Extra"].tolist(), ["C"])

    def test_gera_um_excel_com_duas_abas(self):
        inicial = pd.DataFrame(
            [
                {"CPF/CNPJ": "111.222.333-44", "Titulo": "MAS", "Parcela": 1, "Valor Titulo": 100, "Extra": "A"},
                {"CPF/CNPJ": "222.333.444-55", "Titulo": "CHI", "Parcela": 1, "Valor Titulo": 200, "Extra": "B"},
            ]
        )
        direto = pd.DataFrame([{"CPF/CNPJ": "11122233344", "Produto": "cartao"}])
        indireto = pd.DataFrame([{"ClienteCPFCNPJ": "22233344455", "SICREDI_Produto_Legado": "conta corrente"}])

        resultado_excel = processar_sudoeste_processadov2(
            _to_xlsx_bytes(inicial),
            _to_xlsx_bytes(direto),
            _to_xlsx_bytes(indireto),
        )

        xls = pd.ExcelFile(resultado_excel)
        self.assertEqual(xls.sheet_names, ["Direto", "Indireto"])
        direto_df = pd.read_excel(xls, "Direto")
        indireto_df = pd.read_excel(xls, "Indireto")

        self.assertEqual(direto_df["Extra"].tolist(), ["A"])
        self.assertEqual(indireto_df["Extra"].tolist(), ["B"])


if __name__ == "__main__":
    unittest.main()
