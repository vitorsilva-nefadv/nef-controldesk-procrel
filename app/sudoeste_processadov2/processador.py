import io
import logging
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from app.logging_utils import configure_logging, log_info
from app.sudoeste import _find_column, _ler_tabela_upload

from .matching import ProdutoIndexado, indexar_produto, linha_inicial_tem_match
from .parser import normalizar_cpf_cnpj, normalizar_parcela

configure_logging()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColunasInicial:
    cpf: str
    titulo: str
    parcela: str
    valor_titulo: str


@dataclass(frozen=True)
class ColunasDiretoIndireto:
    cpf: str
    produto: str


def _resolver_coluna_obrigatoria(dataframe: pd.DataFrame, aliases: tuple[str, ...], nome_exibicao: str) -> str:
    coluna = _find_column(dataframe, *aliases)
    if coluna is None:
        raise ValueError(f"Coluna obrigatoria nao encontrada: {nome_exibicao}")
    return coluna


def _preparar_colunas_inicial(dataframe: pd.DataFrame) -> ColunasInicial:
    return ColunasInicial(
        cpf=_resolver_coluna_obrigatoria(
            dataframe,
            ("cpf/cnpj", "cpf cnpj", "cpf", "cnpj"),
            "CPF/CNPJ",
        ),
        titulo=_resolver_coluna_obrigatoria(dataframe, ("titulo", "título"), "Titulo"),
        parcela=_resolver_coluna_obrigatoria(dataframe, ("parcela", "n parcela"), "Parcela"),
        valor_titulo=_resolver_coluna_obrigatoria(
            dataframe,
            ("valor título", "valor titulo", "valor do titulo", "valor r$"),
            "Valor Titulo",
        ),
    )


def _preparar_colunas_direto(dataframe: pd.DataFrame) -> ColunasDiretoIndireto:
    return ColunasDiretoIndireto(
        cpf=_resolver_coluna_obrigatoria(
            dataframe,
            ("cpf/cnpj", "cpf cnpj", "cpf", "cnpj", "documento"),
            "CPF/CNPJ",
        ),
        produto=_resolver_coluna_obrigatoria(
            dataframe,
            ("produto", "sicredi_produto_legado", "sicredi produto legado"),
            "Produto",
        ),
    )


def _preparar_colunas_indireto(dataframe: pd.DataFrame) -> ColunasDiretoIndireto:
    return ColunasDiretoIndireto(
        cpf=_resolver_coluna_obrigatoria(
            dataframe,
            ("clientecpfcnpj", "cliente cpf cnpj", "cpf/cnpj", "cpf cnpj"),
            "ClienteCPFCNPJ",
        ),
        produto=_resolver_coluna_obrigatoria(
            dataframe,
            ("sicredi_produto_legado", "sicredi produto legado", "produto"),
            "SICREDI_Produto_Legado",
        ),
    )


def _indexar_por_cpf(dataframe: pd.DataFrame, cpf_col: str, produto_col: str) -> dict[str, list[ProdutoIndexado]]:
    index: dict[str, list[ProdutoIndexado]] = defaultdict(list)
    for _, row in dataframe.iterrows():
        cpf_norm = normalizar_cpf_cnpj(row[cpf_col])
        if not cpf_norm:
            continue
        index[cpf_norm].append(indexar_produto(row[produto_col]))
    return index


def processar_sudoeste_processadov2_frames(
    inicial_processado_excel: bytes,
    direto_excel: bytes,
    indireto_excel: bytes,
    *,
    debug_mismatch: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Filtra o inicial processado em duas saidas independentes.

    Regras:
    - saida_direto: apenas linhas do inicial com match no Direto;
    - saida_indireto: apenas linhas do inicial com match no Indireto;
    - ambas preservam colunas e ordem do inicial.
    """
    log_info(logger, "Iniciando processamento de frames", fluxo="sudoeste-processado-v2")

    inicial = _ler_tabela_upload(inicial_processado_excel, contexto="sudoeste-processado-v2/inicial-processado")
    direto = _ler_tabela_upload(direto_excel, contexto="sudoeste-processado-v2/direto")
    indireto = _ler_tabela_upload(indireto_excel, contexto="sudoeste-processado-v2/indireto")

    if inicial.empty:
        raise ValueError("A planilha inicial processado esta vazia.")
    if direto.empty:
        raise ValueError("A planilha direto esta vazia.")
    if indireto.empty:
        raise ValueError("A planilha indireto esta vazia.")

    col_inicial = _preparar_colunas_inicial(inicial)
    col_direto = _preparar_colunas_direto(direto)
    col_indireto = _preparar_colunas_indireto(indireto)

    log_info(
        logger,
        "Colunas obrigatorias validadas",
        fluxo="sudoeste-processado-v2",
        colunas_inicial={
            "cpf": col_inicial.cpf,
            "titulo": col_inicial.titulo,
            "parcela": col_inicial.parcela,
            "valor_titulo": col_inicial.valor_titulo,
        },
        colunas_direto={"cpf": col_direto.cpf, "produto": col_direto.produto},
        colunas_indireto={"cpf": col_indireto.cpf, "produto": col_indireto.produto},
    )

    index_direto = _indexar_por_cpf(direto, col_direto.cpf, col_direto.produto)
    index_indireto = _indexar_por_cpf(indireto, col_indireto.cpf, col_indireto.produto)

    manter_indices_direto: list[int] = []
    manter_indices_indireto: list[int] = []
    validadas_direto = 0
    validadas_indireto = 0

    for indice, row in inicial.iterrows():
        cpf_norm = normalizar_cpf_cnpj(row[col_inicial.cpf])
        row_match = {
            "cpf": cpf_norm,
            "titulo": row[col_inicial.titulo],
            "parcela": normalizar_parcela(row[col_inicial.parcela]),
        }
        candidatos_direto = index_direto.get(cpf_norm, [])
        candidatos_indireto = index_indireto.get(cpf_norm, [])

        match_direto = linha_inicial_tem_match(row_match, candidatos_direto)
        match_indireto = linha_inicial_tem_match(row_match, candidatos_indireto)

        if match_direto:
            manter_indices_direto.append(indice)
            validadas_direto += 1
        if match_indireto:
            manter_indices_indireto.append(indice)
            validadas_indireto += 1

        if debug_mismatch and not match_direto and not match_indireto:
            logger.debug(
                "Linha do inicial sem match | cpf=%s titulo=%s parcela=%s",
                row_match["cpf"],
                row_match["titulo"],
                row_match["parcela"],
            )

    saida_direto = inicial.iloc[manter_indices_direto].copy().reset_index(drop=True)
    saida_indireto = inicial.iloc[manter_indices_indireto].copy().reset_index(drop=True)

    total_linhas = len(inicial)
    linhas_sem_match = total_linhas - len(set(manter_indices_direto).union(set(manter_indices_indireto)))

    log_info(
        logger,
        "Processamento concluido",
        fluxo="sudoeste-processado-v2",
        linhas_inicial=total_linhas,
        linhas_saida_direto=len(saida_direto),
        linhas_saida_indireto=len(saida_indireto),
        linhas_sem_match=linhas_sem_match,
        validadas_direto=validadas_direto,
        validadas_indireto=validadas_indireto,
    )
    return saida_direto, saida_indireto


def processar_sudoeste_processadov2(
    inicial_processado_excel: bytes,
    direto_excel: bytes,
    indireto_excel: bytes,
    *,
    debug_mismatch: bool = False,
) -> io.BytesIO:
    """Executa o fluxo V2 e devolve um unico Excel com duas abas."""
    dataframe_direto, dataframe_indireto = processar_sudoeste_processadov2_frames(
        inicial_processado_excel,
        direto_excel,
        indireto_excel,
        debug_mismatch=debug_mismatch,
    )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe_direto.to_excel(writer, sheet_name="Direto", index=False)
        dataframe_indireto.to_excel(writer, sheet_name="Indireto", index=False)
    output.seek(0)
    return output
