from dataclasses import dataclass

from .parser import (
    classificar_titulo_inicial,
    extrair_blocos_contrato_parcelas,
    normalizar_contrato,
    normalizar_parcela,
    produto_deve_ser_ignorado,
    produto_eh_cartao,
    produto_eh_chi,
)


@dataclass(frozen=True)
class ProdutoIndexado:
    """Representa uma linha de direto/indireto pronta para matching rápido."""

    produto_raw: str
    ignorar: bool
    eh_cartao: bool
    eh_chi: bool
    blocos_contrato: list[dict[str, object]]


def indexar_produto(produto: object) -> ProdutoIndexado:
    texto = str(produto or "")
    return ProdutoIndexado(
        produto_raw=texto,
        ignorar=produto_deve_ser_ignorado(texto),
        eh_cartao=produto_eh_cartao(texto),
        eh_chi=produto_eh_chi(texto),
        blocos_contrato=extrair_blocos_contrato_parcelas(texto),
    )


def _match_contrato(titulo: object, parcela: object, candidatos: list[ProdutoIndexado]) -> bool:
    contrato_norm = normalizar_contrato(titulo)
    parcela_norm = normalizar_parcela(parcela)
    if not contrato_norm or not parcela_norm:
        return False

    for candidato in candidatos:
        if candidato.ignorar:
            continue
        for bloco in candidato.blocos_contrato:
            parcelas = bloco.get("parcelas", set())
            if bloco.get("contrato_norm") == contrato_norm and parcela_norm in parcelas:
                return True
    return False


def _match_cartao(candidatos: list[ProdutoIndexado]) -> bool:
    return any((not candidato.ignorar) and candidato.eh_cartao for candidato in candidatos)


def _match_chi(candidatos: list[ProdutoIndexado]) -> bool:
    return any((not candidato.ignorar) and candidato.eh_chi for candidato in candidatos)


def linha_inicial_tem_match(row_inicial, candidatos: list[ProdutoIndexado]) -> bool:
    """
    Aplica a regra de matching da linha do inicial contra uma lista de candidatos.

    Observação:
    - a priorização Direto -> Indireto é feita no `processador.py`.
    """
    tipo_titulo = classificar_titulo_inicial(row_inicial["titulo"])
    if tipo_titulo == "ignorar":
        return False
    if tipo_titulo == "contrato":
        return _match_contrato(row_inicial["titulo"], row_inicial["parcela"], candidatos)
    if tipo_titulo == "cartao":
        return _match_cartao(candidatos)
    if tipo_titulo == "chi":
        return _match_chi(candidatos)
    return False

