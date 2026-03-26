"""
Fluxo Sudoeste Processado V2.

Este pacote implementa um fluxo novo e isolado do legado:
- a saída nasce exclusivamente do `inicial_processado`;
- direto/indireto servem apenas como validação de inclusão.
"""

from .processador import processar_sudoeste_processadov2, processar_sudoeste_processadov2_frames

__all__ = [
    "processar_sudoeste_processadov2",
    "processar_sudoeste_processadov2_frames",
]

