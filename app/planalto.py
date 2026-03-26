import io
import logging
import re
import unicodedata

import numpy as np
import pandas as pd
from openpyxl.styles import Font, PatternFill

from .logging_utils import configure_logging, log_info

logger = logging.getLogger(__name__)
configure_logging()

OUTPUT_COLUMNS = [
    "AG",
    "Data Pagamento",
    "Conta",
    "Associado",
    "Titulo",
    "Parcela",
    "Valor Título",
    "Tipo Movimento",
    "Ajuste",
    "Histórico",
    "CPF/CNPJ",
    "cpf format",
    "Atraso",
    "%",
    "R$",
    "renegociação",
    "ENTRADA RENEG",
    "BAIXA DE CAPITAL",
]

COLUMN_WIDTHS = {
    "B": 12,
    "C": 12,
    "D": 30,
    "E": 12,
    "F": 7,
    "H": 14,
    "J": 12,
    "K": 18,
}


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _find_column(df: pd.DataFrame, *aliases: str) -> str | None:
    normalized_columns = {_normalize_text(column): column for column in df.columns}

    for alias in aliases:
        key = _normalize_text(alias)
        if key in normalized_columns:
            return normalized_columns[key]

    for alias in aliases:
        key = _normalize_text(alias)
        for normalized_column, original_column in normalized_columns.items():
            if key and key in normalized_column:
                return original_column

    return None


def _require_column(df: pd.DataFrame, *aliases: str) -> str:
    column = _find_column(df, *aliases)
    if column is None:
        raise ValueError(f"Coluna obrigatoria nao encontrada: {aliases[0]}")
    return column


def _converter_cartao(valor: object) -> object:
    valor_formatado = str(valor).strip().upper()
    if valor_formatado.startswith("CAR") or valor_formatado.startswith("MAS"):
        return "cartão"
    return valor


def _converter_data(valor: object):
    if pd.isna(valor):
        return pd.NaT

    if isinstance(valor, pd.Timestamp):
        return valor

    if isinstance(valor, (int, float, np.integer, np.floating)):
        return pd.to_datetime(valor, unit="D", origin="1899-12-30")

    return pd.to_datetime(valor, dayfirst=True, errors="coerce")


def _converter_numero(valor: object) -> float:
    if pd.isna(valor):
        return 0.0

    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return 0.0

        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")

        return float(texto)

    return float(valor)


def _formatar_data_saida(valor: object) -> str | None:
    data = _converter_data(valor)
    if pd.isna(data):
        return None
    return data.strftime("%d/%m/%Y")


def _formatar_cpf(valor: object) -> str | None:
    if pd.isna(valor):
        return None
    return re.sub(r"[.\-/]", "", str(valor))


def _ler_recebimento(recebimento: bytes) -> pd.DataFrame:
    dataframe = pd.read_excel(io.BytesIO(recebimento))
    dataframe = dataframe.dropna(how="all").reset_index(drop=True)

    if dataframe.empty:
        return dataframe

    unnamed_columns = [
        str(column).startswith("Unnamed") or pd.isna(column) for column in dataframe.columns
    ]
    if all(unnamed_columns):
        bruto = pd.read_excel(io.BytesIO(recebimento), header=None)
        bruto = bruto.dropna(how="all").reset_index(drop=True)

        header_index = None
        for idx, row in bruto.iterrows():
            normalized_values = {
                _normalize_text(value) for value in row.tolist() if pd.notna(value)
            }
            if "associado" in normalized_values and (
                "titulo" in normalized_values or "datapagamento" in normalized_values
            ):
                header_index = idx
                break

        if header_index is not None:
            headers = bruto.iloc[header_index].tolist()
            dataframe = bruto.iloc[header_index + 1 :].copy()
            dataframe.columns = headers
            dataframe = dataframe.dropna(how="all").reset_index(drop=True)

    return dataframe


def _processar_recebimento_detalhado(
    df_recebimento: pd.DataFrame, df_pagamento: pd.DataFrame
) -> pd.DataFrame:
    recebimento_associado_col = _require_column(df_recebimento, "nome/razao", "associado")
    recebimento_ag_col = _find_column(df_recebimento, "ag")
    recebimento_cpf_col = _find_column(df_recebimento, "cpf/cnpj")
    recebimento_atraso_col = _find_column(df_recebimento, "atraso")
    recebimento_vencimento_col = _find_column(
        df_recebimento, "vencimento do produto (mais atrasado)", "vencimento"
    )

    pagamento_ag_col = _find_column(df_pagamento, "ag")
    pagamento_data_col = _require_column(df_pagamento, "data")
    pagamento_conta_col = _require_column(df_pagamento, "conta")
    pagamento_associado_col = _require_column(df_pagamento, "associado")
    pagamento_titulo_col = _require_column(df_pagamento, "titulo")
    pagamento_parcela_col = _require_column(df_pagamento, "parcela")
    pagamento_valor_col = _require_column(df_pagamento, "valor titulo")
    pagamento_tipo_col = _find_column(df_pagamento, "tipo movimento")
    pagamento_historico_col = _find_column(df_pagamento, "historico")
    pagamento_cpf_col = _find_column(df_pagamento, "cpf/cnpj")

    merge = pd.merge(
        df_recebimento,
        df_pagamento,
        left_on=recebimento_associado_col,
        right_on=pagamento_associado_col,
        how="inner",
    )

    if merge.empty:
        raise ValueError("Nenhuma linha correspondente foi encontrada entre recebimento e pagamento.")

    merge[pagamento_data_col] = merge[pagamento_data_col].apply(_converter_data)
    merge[pagamento_titulo_col] = merge[pagamento_titulo_col].apply(_converter_cartao)

    registros = []
    for associado, grupo in merge.groupby(pagamento_associado_col, sort=False):
        primeira_linha = grupo.iloc[0]

        parcelas = []
        for parcela in grupo[pagamento_parcela_col].tolist():
            parcela_texto = str(parcela).strip()
            if parcela_texto and parcela_texto not in parcelas:
                parcelas.append(parcela_texto)

        historicos = []
        if pagamento_historico_col:
            for historico in grupo[pagamento_historico_col].tolist():
                if pd.isna(historico):
                    continue
                try:
                    historico_texto = str(int(historico))
                except (TypeError, ValueError):
                    historico_texto = str(historico).strip()
                if historico_texto and historico_texto not in historicos:
                    historicos.append(historico_texto)

        titulos = []
        for titulo in grupo[pagamento_titulo_col].tolist():
            if pd.isna(titulo):
                continue
            titulo_texto = str(titulo).strip()
            if titulo_texto and titulo_texto not in titulos:
                titulos.append(titulo_texto)

        datas_pagamento = [
            data for data in grupo[pagamento_data_col].tolist() if pd.notna(data)
        ]
        data_pagamento = max(datas_pagamento) if datas_pagamento else pd.NaT

        atraso = primeira_linha.get(recebimento_atraso_col) if recebimento_atraso_col else None
        if pd.isna(atraso) or atraso in ("", None):
            vencimento = (
                primeira_linha.get(recebimento_vencimento_col)
                if recebimento_vencimento_col
                else None
            )
            vencimento = _converter_data(vencimento)
            if pd.notna(vencimento) and pd.notna(data_pagamento):
                atraso = (data_pagamento.to_pydatetime() - vencimento.to_pydatetime()).days
            else:
                atraso = None

        cpf = None
        if recebimento_cpf_col:
            cpf = primeira_linha.get(recebimento_cpf_col)
        if (pd.isna(cpf) or cpf in ("", None)) and pagamento_cpf_col:
            cpf = primeira_linha.get(pagamento_cpf_col)

        registros.append(
            {
                "AG": (
                    primeira_linha.get(recebimento_ag_col)
                    if recebimento_ag_col
                    else primeira_linha.get(pagamento_ag_col)
                ),
                "Data Pagamento": _formatar_data_saida(data_pagamento),
                "Conta": primeira_linha.get(pagamento_conta_col),
                "Associado": associado,
                "Titulo": " + ".join(titulos),
                "Parcela": " + ".join(sorted(set(parcelas))),
                "Valor Título": sum(_converter_numero(valor) for valor in grupo[pagamento_valor_col]),
                "Tipo Movimento": (
                    primeira_linha.get(pagamento_tipo_col) if pagamento_tipo_col else None
                ),
                "Ajuste": None,
                "Histórico": "; ".join(sorted(set(historicos))),
                "CPF/CNPJ": cpf,
                "cpf format": _formatar_cpf(cpf),
                "Atraso": atraso,
                "%": None,
                "R$": None,
                "renegociação": None,
                "ENTRADA RENEG": None,
                "BAIXA DE CAPITAL": None,
            }
        )

    return pd.DataFrame(registros, columns=OUTPUT_COLUMNS)


def _processar_recebimento_pre_formatado(
    df_recebimento: pd.DataFrame, df_pagamento: pd.DataFrame
) -> pd.DataFrame:
    pagamento_associado_col = _find_column(df_pagamento, "associado")
    pagamento_tipo_col = _find_column(df_pagamento, "tipo movimento")

    resultado = pd.DataFrame()
    origem_colunas = {
        "AG": _find_column(df_recebimento, "ag"),
        "Data Pagamento": _find_column(df_recebimento, "data pagamento", "data", "data pgto"),
        "Conta": _find_column(df_recebimento, "conta"),
        "Associado": _find_column(df_recebimento, "associado", "nome/razao"),
        "Titulo": _find_column(df_recebimento, "titulo", "produto"),
        "Parcela": _find_column(df_recebimento, "parcela"),
        "Valor Título": _find_column(df_recebimento, "valor titulo", "valor r$"),
        "Tipo Movimento": _find_column(df_recebimento, "tipo movimento"),
        "Ajuste": _find_column(df_recebimento, "ajuste"),
        "Histórico": _find_column(df_recebimento, "historico"),
        "CPF/CNPJ": _find_column(df_recebimento, "cpf/cnpj"),
        "cpf format": _find_column(df_recebimento, "cpf format"),
        "Atraso": _find_column(df_recebimento, "atraso"),
        "%": _find_column(df_recebimento, "%"),
        "R$": _find_column(df_recebimento, "r$"),
        "renegociação": _find_column(df_recebimento, "renegociacao"),
        "ENTRADA RENEG": _find_column(df_recebimento, "entrada reneg"),
        "BAIXA DE CAPITAL": _find_column(df_recebimento, "baixa de capital"),
    }

    for coluna_saida in OUTPUT_COLUMNS:
        coluna_origem = origem_colunas.get(coluna_saida)
        resultado[coluna_saida] = (
            df_recebimento[coluna_origem]
            if coluna_origem
            else pd.Series([None] * len(df_recebimento), index=df_recebimento.index)
        )

    if pagamento_associado_col and pagamento_tipo_col and resultado["Tipo Movimento"].isna().all():
        tipos_por_associado = (
            df_pagamento[[pagamento_associado_col, pagamento_tipo_col]]
            .dropna(subset=[pagamento_associado_col])
            .drop_duplicates(subset=[pagamento_associado_col])
            .set_index(pagamento_associado_col)[pagamento_tipo_col]
        )
        resultado["Tipo Movimento"] = resultado["Associado"].map(tipos_por_associado)

    if "Data Pagamento" in resultado.columns:
        resultado["Data Pagamento"] = resultado["Data Pagamento"].apply(_formatar_data_saida)

    if "cpf format" in resultado.columns:
        resultado["cpf format"] = resultado.apply(
            lambda row: (
                row["cpf format"]
                if pd.notna(row["cpf format"]) and str(row["cpf format"]).strip()
                else _formatar_cpf(row["CPF/CNPJ"])
            ),
            axis=1,
        )

    return resultado[OUTPUT_COLUMNS]


def _exportar_planalto(dataframe: pd.DataFrame) -> io.BytesIO:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="Planilha1", index=False)
        worksheet = writer.sheets["Planilha1"]

        fundo_verde = PatternFill(
            start_color="009900",
            end_color="009900",
            fill_type="solid",
        )
        fonte_branca = Font(color="FFFFFF", bold=True)

        for cell in worksheet[1]:
            cell.fill = fundo_verde
            cell.font = fonte_branca

        for column_letter, width in COLUMN_WIDTHS.items():
            worksheet.column_dimensions[column_letter].width = width

    output.seek(0)
    return output


def processar_planalto(recebimento: bytes, pagamento: bytes) -> io.BytesIO:
    log_info(logger, "Iniciando fluxo planalto")

    df_recebimento = _ler_recebimento(recebimento)
    df_pagamento = pd.read_excel(io.BytesIO(pagamento))

    if df_recebimento.empty:
        raise ValueError("O arquivo de recebimento esta vazio ou nao possui linhas validas.")
    if df_pagamento.empty:
        raise ValueError("O arquivo de pagamento esta vazio ou nao possui linhas validas.")

    if _find_column(df_recebimento, "nome/razao", "vencimento do produto (mais atrasado)"):
        formatado = _processar_recebimento_detalhado(df_recebimento, df_pagamento)
    else:
        formatado = _processar_recebimento_pre_formatado(df_recebimento, df_pagamento)

    return _exportar_planalto(formatado)
