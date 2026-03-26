import io
import logging
from dataclasses import dataclass

import pandas as pd

from .logging_utils import configure_logging, log_exception, log_info
from .sudoeste import _ler_tabela_upload, _normalize_cpf_cnpj, _find_column, _require_column

configure_logging()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsolidadoColumns:
    cpf: str
    contrato: str | None
    conta: str | None
    parcela: str | None


@dataclass(frozen=True)
class DiretaColumns:
    cpf: str


@dataclass(frozen=True)
class IndiretoColumns:
    cpf: str


def _preparar_colunas_consolidado(dataframe: pd.DataFrame) -> ConsolidadoColumns:
    """Extrai os nomes das colunas do consolidado."""
    cpf = _require_column(dataframe, "cpf/cnpj", "cpf cnpj", "cpf", "cnpj")
    contrato = _find_column(dataframe, "titulo", "título", "contrato")
    conta = _find_column(dataframe, "conta", "chi")
    parcela = _find_column(dataframe, "parcela", "n parcela")
    
    return ConsolidadoColumns(
        cpf=cpf,
        contrato=contrato,
        conta=conta,
        parcela=parcela,
    )


def _preparar_colunas_direta(dataframe: pd.DataFrame) -> DiretaColumns:
    """Extrai os nomes das colunas da direta."""
    cpf = _require_column(dataframe, "cpf/cnpj", "cpf cnpj", "cpf", "cnpj")
    return DiretaColumns(cpf=cpf)


def _preparar_colunas_indireto(dataframe: pd.DataFrame) -> IndiretoColumns:
    """Extrai os nomes das colunas do indireto."""
    cpf = _require_column(dataframe, "cpf/cnpj", "cpf cnpj", "cpf", "cnpj")
    return IndiretoColumns(cpf=cpf)


def _criar_chave_busca(
    cpf: str,
    contrato: str | None = None,
    conta: str | None = None,
    parcela: str | None = None,
) -> str:
    """
    Cria uma chave de busca baseada em CPF/CNPJ e opcionalmente contrato/conta/parcela.
    
    Sem valores adicionais, a chave é apenas o CPF normalizado.
    Com valores adicionais, a chave inclui CPF + contrato + conta + parcela.
    """
    partes = [cpf]
    
    if contrato:
        partes.append(str(contrato))
    if conta:
        partes.append(str(conta))
    if parcela:
        partes.append(str(parcela))
    
    return "|".join(partes)


def _construir_lookup_direto(
    direto_df: pd.DataFrame,
    cols_direta: DiretaColumns,
) -> set[str]:
    """
    Constrói um conjunto de CPF/CNPJs normalizados que estão na direta.
    """
    cpfs = set()
    direto_df_copy = direto_df.copy()
    direto_df_copy["_cpf_norm"] = direto_df_copy[cols_direta.cpf].apply(_normalize_cpf_cnpj)
    
    for cpf in direto_df_copy["_cpf_norm"]:
        if cpf:  # ignora CPF vazio
            cpfs.add(cpf)
    
    return cpfs


def _construir_lookup_indireto(
    indireto_df: pd.DataFrame,
    cols_indireto: IndiretoColumns,
) -> set[str]:
    """
    Constrói um conjunto de CPF/CNPJs normalizados que estão na indireta.
    """
    cpfs = set()
    indireto_df_copy = indireto_df.copy()
    indireto_df_copy["_cpf_norm"] = indireto_df_copy[cols_indireto.cpf].apply(_normalize_cpf_cnpj)
    
    for cpf in indireto_df_copy["_cpf_norm"]:
        if cpf:  # ignora CPF vazio
            cpfs.add(cpf)
    
    return cpfs


def _processar_sudoeste_processadorv2_frames(
    consolidada_excel: bytes,
    direta_excel: bytes,
    indireto_excel: bytes,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Processa o consolidado filtrando apenas clientes que estão em direto OU indireto.
    
    Retorna deux DataFrames: (consolidado_filtrado_direto, consolidado_filtrado_indireto)
    """
    log_info(logger, "Iniciando processamento de frames do processadorv2", fluxo="sudoeste-processadorv2")
    
    consolidada = _ler_tabela_upload(consolidada_excel, contexto="sudoeste-processadorv2/consolidada")
    direta = _ler_tabela_upload(direta_excel, contexto="sudoeste-processadorv2/direta")
    indireto = _ler_tabela_upload(indireto_excel, contexto="sudoeste-processadorv2/indireto")
    
    log_info(
        logger,
        "Leitura das planilhas concluida",
        fluxo="sudoeste-processadorv2",
        linhas_consolidada=len(consolidada),
        linhas_direta=len(direta),
        linhas_indireto=len(indireto),
    )

    if consolidada.empty:
        raise ValueError("A planilha consolidada esta vazia.")
    if direta.empty:
        raise ValueError("A planilha direta esta vazia.")
    if indireto.empty:
        raise ValueError("A planilha indireto esta vazia.")

    cols_consolidada = _preparar_colunas_consolidado(consolidada)
    cols_direta = _preparar_colunas_direta(direta)
    cols_indireto = _preparar_colunas_indireto(indireto)
    
    log_info(
        logger,
        "Validacao de colunas obrigatorias concluida",
        fluxo="sudoeste-processadorv2",
        colunas_consolidada={
            "cpf": cols_consolidada.cpf,
            "contrato": cols_consolidada.contrato,
            "conta": cols_consolidada.conta,
            "parcela": cols_consolidada.parcela,
        },
        colunas_direta={"cpf": cols_direta.cpf},
        colunas_indireto={"cpf": cols_indireto.cpf},
    )

    # Construir lookups de CPF/CNPJ normalizados
    cpfs_direta = _construir_lookup_direto(direta, cols_direta)
    cpfs_indireto = _construir_lookup_indireto(indireto, cols_indireto)
    
    log_info(
        logger,
        "Lookups construidos",
        fluxo="sudoeste-processadorv2",
        unica_cpfs_direta=len(cpfs_direta),
        unica_cpfs_indireto=len(cpfs_indireto),
    )

    # Processar consolidado
    consolidada_copy = consolidada.copy()
    consolidada_copy["_cpf_norm"] = consolidada_copy[cols_consolidada.cpf].apply(_normalize_cpf_cnpj)

    # Filtrar consolidado para direto
    consolidada_direto = []
    consolidada_indireto = []
    
    clientes_totais = 0
    clientes_sem_cpf = 0
    clientes_em_direto = 0
    clientes_em_indireto = 0
    clientes_descartados = 0

    log_info(logger, "Iniciando filtro por CPF/CNPJ", fluxo="sudoeste-processadorv2")
    
    for _, linha in consolidada_copy.iterrows():
        clientes_totais += 1
        cpf_norm = linha["_cpf_norm"]
        
        if not cpf_norm:
            clientes_sem_cpf += 1
            log_info(
                logger,
                "Cliente sem CPF/CNPJ",
                fluxo="sudoeste-processadorv2",
                associado=linha.get(cols_consolidada.cpf, "desconhecido"),
            )
            continue
        
        # Remover coluna temporária antes de adicionar à saída
        linha_saida = linha.drop("_cpf_norm")
        
        # Verificar se está em direto
        if cpf_norm in cpfs_direta:
            consolidada_direto.append(linha_saida)
            clientes_em_direto += 1
        # Se não está em direto, verificar se está em indireto
        elif cpf_norm in cpfs_indireto:
            consolidada_indireto.append(linha_saida)
            clientes_em_indireto += 1
        else:
            clientes_descartados += 1
            log_info(
                logger,
                "Cliente nao encontrado em direto nem indireto",
                fluxo="sudoeste-processadorv2",
                cpf_norm=cpf_norm,
            )

    # Converter listas para DataFrames
    saida_direto = pd.DataFrame(consolidada_direto) if consolidada_direto else consolidada.head(0)
    saida_indireto = pd.DataFrame(consolidada_indireto) if consolidada_indireto else consolidada.head(0)
    
    log_info(
        logger,
        "Processamento de frames concluido",
        fluxo="sudoeste-processadorv2",
        clientes_totais=clientes_totais,
        clientes_em_direto=clientes_em_direto,
        clientes_em_indireto=clientes_em_indireto,
        clientes_descartados=clientes_descartados,
        clientes_sem_cpf=clientes_sem_cpf,
        linhas_saida_direto=len(saida_direto),
        linhas_saida_indireto=len(saida_indireto),
    )
    
    return saida_direto, saida_indireto


def _exportar_sudoeste_processadorv2(
    direto_df: pd.DataFrame,
    indireto_df: pd.DataFrame,
) -> io.BytesIO:
    """Exporta os DataFrames filtrados para Excel."""
    log_info(
        logger,
        "Iniciando exportacao de Excel processadorv2",
        fluxo="sudoeste-processadorv2",
        linhas_direto=len(direto_df),
        linhas_indireto=len(indireto_df),
    )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        direto_df.to_excel(writer, sheet_name="Direto", index=False)
        indireto_df.to_excel(writer, sheet_name="Indireto", index=False)
    output.seek(0)
    log_info(
        logger,
        "Exportacao de Excel processadorv2 concluida",
        fluxo="sudoeste-processadorv2",
        tamanho_bytes=len(output.getbuffer()),
    )
    return output


def processar_sudoeste_processadorv2(
    consolidada_excel: bytes,
    direta_excel: bytes,
    indireto_excel: bytes,
) -> io.BytesIO:
    """
    Processa o consolidado mantendo apenas clientes que estao em direto OU indireto.
    
    Args:
        consolidada_excel: Arquivo Excel com clientes consolidados (pagos)
        direta_excel: Arquivo Excel com clientes diretos
        indireto_excel: Arquivo Excel com clientes indiretos
    
    Returns:
        Arquivo Excel com dois abas: Direto e Indireto, contendo os consolidados que foram encontrados
    """
    log_info(logger, "Iniciando fluxo sudoeste-processadorv2")
    try:
        direto_df, indireto_df = _processar_sudoeste_processadorv2_frames(
            consolidada_excel, direta_excel, indireto_excel
        )
        return _exportar_sudoeste_processadorv2(direto_df, indireto_df)
    except Exception:
        log_exception(logger, "Erro no fluxo sudoeste-processadorv2")
        raise
