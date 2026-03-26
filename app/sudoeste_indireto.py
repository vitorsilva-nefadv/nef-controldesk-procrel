import io
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass

import pandas as pd

from .logging_utils import configure_logging, log_exception, log_info
from .sudoeste import (
    _classify_title,
    _converter_data,
    _find_column,
    _ler_tabela_upload,
    _normalize_cpf_cnpj,
    _normalize_parcela,
    _require_column,
)

configure_logging()
logger = logging.getLogger(__name__)

OUTPUT_COLUMNS_INDIRETO = [
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
]


@dataclass(frozen=True)
class ProcessadaColumns:
    ag: str | None
    conta: str | None
    associado: str
    cpf: str
    titulo: str
    parcela: str
    valor_titulo: str
    historico: str | None
    data: str | None


@dataclass(frozen=True)
class IndiretoColumns:
    ultimo_acionamento: str
    cpf: str
    produto_legado: str
    vencimento_mais_antigo: str


def _resolver_coluna(
    dataframe: pd.DataFrame,
    aliases: tuple[str, ...],
    fallback_index: int | None = None,
) -> str | None:
    coluna = _find_column(dataframe, *aliases) if aliases else None
    if coluna is not None:
        return coluna

    if fallback_index is None:
        return None

    if 0 <= fallback_index < len(dataframe.columns):
        return dataframe.columns[fallback_index]
    return None


def _resolver_coluna_obrigatoria(
    dataframe: pd.DataFrame,
    aliases: tuple[str, ...],
    fallback_index: int | None = None,
    nome_exibicao: str | None = None,
) -> str:
    coluna = _resolver_coluna(dataframe, aliases=aliases, fallback_index=fallback_index)
    if coluna is None:
        if nome_exibicao:
            raise ValueError(f"Coluna obrigatoria nao encontrada: {nome_exibicao}")
        if aliases:
            return _require_column(dataframe, *aliases)
        raise ValueError("Coluna obrigatoria nao encontrada.")
    return coluna


def _preparar_colunas_processada(dataframe: pd.DataFrame) -> ProcessadaColumns:
    return ProcessadaColumns(
        ag=_resolver_coluna(dataframe, ("ag", "agencia", "ag.")),
        conta=_resolver_coluna(dataframe, ("conta",)),
        associado=_resolver_coluna_obrigatoria(dataframe, ("associado", "nome/razao"), nome_exibicao="Associado"),
        cpf=_resolver_coluna_obrigatoria(dataframe, ("cpf/cnpj", "cpf cnpj", "cpf", "cnpj"), nome_exibicao="CPF/CNPJ"),
        titulo=_resolver_coluna_obrigatoria(dataframe, ("titulo", "título"), nome_exibicao="Titulo"),
        parcela=_resolver_coluna_obrigatoria(dataframe, ("parcela", "n parcela"), nome_exibicao="Parcela"),
        valor_titulo=_resolver_coluna_obrigatoria(
            dataframe,
            ("valor titulo", "valor do titulo", "valor r$"),
            nome_exibicao="Valor Titulo",
        ),
        historico=_resolver_coluna(dataframe, ("historico", "histórico")),
        data=_resolver_coluna(dataframe, ("data", "data pagamento", "data pgto")),
    )


def _preparar_colunas_indireto(dataframe: pd.DataFrame) -> IndiretoColumns:
    return IndiretoColumns(
        ultimo_acionamento=_resolver_coluna_obrigatoria(
            dataframe,
            ("ultimoacionamentodata", "ultimo acionamento data", "ultimo acionamento"),
            nome_exibicao="UltimoAcionamentoData",
        ),
        cpf=_resolver_coluna_obrigatoria(
            dataframe,
            ("clientecpfcnpj", "cliente cpf cnpj"),
            nome_exibicao="ClienteCPFCNPJ",
        ),
        produto_legado=_resolver_coluna_obrigatoria(
            dataframe,
            ("sicredi_produto_legado", "sicredi produto legado"),
            nome_exibicao="SICREDI_Produto_Legado",
        ),
        vencimento_mais_antigo=_resolver_coluna_obrigatoria(
            dataframe,
            ("vencimentomaisantigo", "vencimento mais antigo"),
            nome_exibicao="VencimentoMaisAntigo",
        ),
    )


def _valor_preenchido(value: object) -> bool:
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass

    if isinstance(value, str):
        return bool(value.strip())
    return value not in (None, "")


def _normalizar_texto_livre(value: object) -> str | None:
    if not _valor_preenchido(value):
        return None

    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    return str(value).strip() or None


def _converter_valor_titulo(value: object) -> float:
    if not _valor_preenchido(value):
        return 0.0

    if isinstance(value, str):
        texto = value.strip()
        if not texto:
            return 0.0
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        return float(texto)

    return float(value)


def _formatar_data_para_saida(value: object) -> str | None:
    data = _converter_data(value)
    if pd.notna(data):
        return data.strftime("%d/%m/%Y")
    return _normalizar_texto_livre(value)


def _calcular_atraso(data_referencia: object, vencimento: object) -> int | None:
    data_ref = _converter_data(data_referencia)
    data_venc = _converter_data(vencimento)

    if pd.isna(data_ref) or pd.isna(data_venc):
        return None

    diferenca = data_ref.normalize() - data_venc.normalize()
    return int(diferenca.days)


def _classificar_titulo(value: object) -> str:
    classificacao = _classify_title(value)
    if classificacao.kind == "card":
        return "card"
    if classificacao.kind == "chi":
        return "chi"
    if classificacao.kind == "contract":
        return "contract"
    return "other"


def _aplicar_fallback_legado(
    possui_conta: bool,
    possui_cartao: bool,
    produto_legado: object,
) -> tuple[bool, bool]:
    if possui_conta or possui_cartao:
        return possui_conta, possui_cartao

    kind = _classificar_titulo(produto_legado)
    if kind == "chi":
        return True, possui_cartao
    if kind == "card":
        return possui_conta, True
    return possui_conta, possui_cartao


def _consolidar_titulo(grupo: pd.DataFrame, titulo_col: str, produto_legado: object) -> str | None:
    contratos_unicos: OrderedDict[str, None] = OrderedDict()
    possui_conta = False
    possui_cartao = False

    for _, row in grupo.iterrows():
        titulo = _normalizar_texto_livre(row[titulo_col])
        kind = _classificar_titulo(titulo)

        if kind == "chi":
            possui_conta = True
            continue
        if kind == "card":
            possui_cartao = True
            continue
        if kind == "contract" and titulo and titulo not in contratos_unicos:
            contratos_unicos[titulo] = None

    possui_conta, possui_cartao = _aplicar_fallback_legado(possui_conta, possui_cartao, produto_legado)

    partes = list(contratos_unicos.keys())
    if possui_conta:
        partes.append("Conta corrente")
    if possui_cartao:
        partes.append("Cartão")

    if not partes:
        return None
    return " + ".join(partes)


def _parcela_sort_key(parcela: str) -> tuple[int, int | str]:
    if re.fullmatch(r"\d+", parcela):
        return (0, int(parcela))
    return (1, parcela)


def _consolidar_parcela(grupo: pd.DataFrame, titulo_col: str, parcela_col: str, produto_legado: object) -> str | None:
    contratos: OrderedDict[str, list[str]] = OrderedDict()
    possui_conta = False
    possui_cartao = False

    for _, row in grupo.iterrows():
        titulo = _normalizar_texto_livre(row[titulo_col])
        kind = _classificar_titulo(titulo)

        if kind == "chi":
            possui_conta = True
            continue
        if kind == "card":
            possui_cartao = True
            continue
        if kind != "contract" or not titulo:
            continue

        if titulo not in contratos:
            contratos[titulo] = []

        parcela = _normalize_parcela(row[parcela_col])
        if parcela and parcela not in contratos[titulo]:
            contratos[titulo].append(parcela)

    possui_conta, possui_cartao = _aplicar_fallback_legado(possui_conta, possui_cartao, produto_legado)

    partes = []
    for contrato, parcelas in contratos.items():
        parcelas_ordenadas = sorted(parcelas, key=_parcela_sort_key)
        if parcelas_ordenadas:
            partes.append(f"({contrato}_{'_'.join(parcelas_ordenadas)})")
        else:
            partes.append(f"({contrato})")

    if possui_conta:
        partes.append("(conta_1)")
    if possui_cartao:
        partes.append("(cartão_1)")

    if not partes:
        return None
    return "".join(partes)


def _primeiro_preenchido(serie: pd.Series) -> object:
    for value in serie.tolist():
        if _valor_preenchido(value):
            return value
    return None


def _selecionar_linha_indireto_por_cpf(indireto: pd.DataFrame) -> dict[str, pd.Series]:
    lookup: dict[str, pd.Series] = {}
    for cpf, grupo in indireto.groupby("_cpf_norm", sort=False):
        if not cpf:
            continue
        lookup[cpf] = grupo.sort_values("_ordem").iloc[0]
    return lookup


def _processar_sudoeste_indireto_frames(
    processada_excel: bytes,
    indireto_excel: bytes,
) -> pd.DataFrame:
    log_info(logger, "Iniciando processamento de frames", fluxo="sudoeste-indireto")
    processada = _ler_tabela_upload(processada_excel, contexto="sudoeste-indireto/processada")
    indireto = _ler_tabela_upload(indireto_excel, contexto="sudoeste-indireto/indireto")
    log_info(
        logger,
        "Leitura das planilhas concluida",
        fluxo="sudoeste-indireto",
        linhas_processada=len(processada),
        linhas_indireto=len(indireto),
    )

    if processada.empty:
        raise ValueError("A planilha processada esta vazia.")
    if indireto.empty:
        raise ValueError("A planilha indireto esta vazia.")

    cols_processada = _preparar_colunas_processada(processada)
    cols_indireto = _preparar_colunas_indireto(indireto)
    log_info(
        logger,
        "Validacao de colunas obrigatorias concluida",
        fluxo="sudoeste-indireto",
        colunas_processada={
            "associado": cols_processada.associado,
            "cpf": cols_processada.cpf,
            "titulo": cols_processada.titulo,
            "parcela": cols_processada.parcela,
            "valor_titulo": cols_processada.valor_titulo,
        },
        colunas_indireto={
            "ultimo_acionamento": cols_indireto.ultimo_acionamento,
            "cpf": cols_indireto.cpf,
            "produto_legado": cols_indireto.produto_legado,
            "vencimento_mais_antigo": cols_indireto.vencimento_mais_antigo,
        },
    )

    processada = processada.copy()
    indireto = indireto.copy()

    processada["_ordem"] = range(len(processada))
    processada["_cpf_norm"] = processada[cols_processada.cpf].apply(_normalize_cpf_cnpj)

    indireto["_ordem"] = range(len(indireto))
    indireto["_cpf_norm"] = indireto[cols_indireto.cpf].apply(_normalize_cpf_cnpj)

    indireto_lookup = _selecionar_linha_indireto_por_cpf(indireto)

    linhas_saida: list[dict[str, object]] = []
    grupos_total = 0
    grupos_sem_cpf = 0
    grupos_sem_match = 0
    grupos_com_match = 0

    log_info(logger, "Iniciando match por CPF/CNPJ", fluxo="sudoeste-indireto")
    for cpf, grupo in processada.groupby("_cpf_norm", sort=False):
        grupos_total += 1
        if not cpf:
            grupos_sem_cpf += 1
            continue
        linha_indireto = indireto_lookup.get(cpf)
        if linha_indireto is None:
            grupos_sem_match += 1
            continue
        grupos_com_match += 1

        grupo_ordenado = grupo.sort_values("_ordem")
        primeira_linha = grupo_ordenado.iloc[0]
        produto_legado = linha_indireto[cols_indireto.produto_legado]

        data_original = primeira_linha[cols_processada.data] if cols_processada.data else None
        vencimento_original = linha_indireto[cols_indireto.vencimento_mais_antigo]

        linhas_saida.append(
            {
                "AG": primeira_linha[cols_processada.ag] if cols_processada.ag else None,
                "Conta": primeira_linha[cols_processada.conta] if cols_processada.conta else None,
                "Associado": primeira_linha[cols_processada.associado],
                "CPF/CNPJ": _normalizar_texto_livre(_primeiro_preenchido(grupo_ordenado[cols_processada.cpf])),
                "Titulo": _consolidar_titulo(grupo_ordenado, cols_processada.titulo, produto_legado),
                "Parcela": _consolidar_parcela(
                    grupo_ordenado,
                    cols_processada.titulo,
                    cols_processada.parcela,
                    produto_legado,
                ),
                "Valor Título": sum(
                    _converter_valor_titulo(value)
                    for value in grupo_ordenado[cols_processada.valor_titulo]
                ),
                "Histórico": (
                    _primeiro_preenchido(grupo_ordenado[cols_processada.historico])
                    if cols_processada.historico
                    else None
                ),
                "Data": _formatar_data_para_saida(data_original),
                "Atraso": _calcular_atraso(data_original, vencimento_original),
                "%receita": None,
                "receita": None,
                "Dt Ultimo Acionamento": _formatar_data_para_saida(linha_indireto[cols_indireto.ultimo_acionamento]),
                "Situação": "Pagamento OK",
                "Venc. Parcela": _formatar_data_para_saida(vencimento_original),
            }
        )

    saida = pd.DataFrame(linhas_saida, columns=OUTPUT_COLUMNS_INDIRETO)
    log_info(
        logger,
        "Processamento de frames concluido",
        fluxo="sudoeste-indireto",
        grupos_total=grupos_total,
        grupos_com_match=grupos_com_match,
        grupos_sem_match=grupos_sem_match,
        grupos_sem_cpf=grupos_sem_cpf,
        linhas_saida=len(saida),
    )
    return saida


def processar_sudoeste_indireto_frames(
    processada_excel: bytes,
    indireto_excel: bytes,
) -> pd.DataFrame:
    return _processar_sudoeste_indireto_frames(processada_excel, indireto_excel)


def _exportar_sudoeste_indireto(dataframe: pd.DataFrame) -> io.BytesIO:
    log_info(
        logger,
        "Iniciando exportacao de Excel",
        fluxo="sudoeste-indireto",
        linhas=len(dataframe),
        sheet_name="Sudoeste Indireto",
    )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="Sudoeste Indireto", index=False)
    output.seek(0)
    log_info(
        logger,
        "Exportacao de Excel concluida",
        fluxo="sudoeste-indireto",
        tamanho_bytes=len(output.getbuffer()),
    )
    return output


def processar_sudoeste_indireto(
    processada_excel: bytes,
    indireto_excel: bytes,
) -> io.BytesIO:
    log_info(logger, "Iniciando fluxo sudoeste-indireto")
    try:
        output_df = processar_sudoeste_indireto_frames(processada_excel, indireto_excel)
        return _exportar_sudoeste_indireto(output_df)
    except Exception:
        log_exception(logger, "Erro no fluxo sudoeste-indireto")
        raise
