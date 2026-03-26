import io
import logging

import pandas as pd

from .logging_utils import configure_logging, log_exception, log_info
from .sudoeste_direto import processar_sudoeste_direto_frames
from .sudoeste_indireto import processar_sudoeste_indireto_frames

configure_logging()
logger = logging.getLogger(__name__)


def _exportar_sudoeste_consolidado(
    direto_df: pd.DataFrame,
    indireto_df: pd.DataFrame,
) -> io.BytesIO:
    log_info(
        logger,
        "Iniciando exportacao de Excel consolidado",
        fluxo="sudoeste-consolidado",
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
        "Exportacao de Excel consolidado concluida",
        fluxo="sudoeste-consolidado",
        tamanho_bytes=len(output.getbuffer()),
    )
    return output


def processar_sudoeste_consolidado(
    processada_excel: bytes,
    direta_excel: bytes,
    indireto_excel: bytes,
) -> io.BytesIO:
    log_info(logger, "Iniciando fluxo sudoeste-consolidado")
    try:
        log_info(logger, "Iniciando etapa sudoeste-direto no consolidado", fluxo="sudoeste-consolidado")
        direto_df = processar_sudoeste_direto_frames(processada_excel, direta_excel)
        log_info(
            logger,
            "Etapa sudoeste-direto concluida no consolidado",
            fluxo="sudoeste-consolidado",
            linhas_saida=len(direto_df),
        )

        log_info(logger, "Iniciando etapa sudoeste-indireto no consolidado", fluxo="sudoeste-consolidado")
        indireto_df = processar_sudoeste_indireto_frames(processada_excel, indireto_excel)
        log_info(
            logger,
            "Etapa sudoeste-indireto concluida no consolidado",
            fluxo="sudoeste-consolidado",
            linhas_saida=len(indireto_df),
        )
        return _exportar_sudoeste_consolidado(direto_df, indireto_df)
    except Exception:
        log_exception(logger, "Erro no fluxo sudoeste-consolidado")
        raise
