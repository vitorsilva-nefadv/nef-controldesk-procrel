import io
import logging
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

OUTPUT_COLUMNS_DIRETO = [
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
    protocolo: str | None


@dataclass(frozen=True)
class DiretaColumns:
    cpf: str
    produto: str
    dt_acionamento: str
    vencimento: str


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
        cpf=_resolver_coluna_obrigatoria(
            dataframe,
            ("cpf/cnpj", "cpf cnpj", "cpf", "cnpj"),
            fallback_index=3,
            nome_exibicao="CPF/CNPJ (coluna D)",
        ),
        titulo=_resolver_coluna_obrigatoria(dataframe, ("titulo", "título"), nome_exibicao="Titulo"),
        parcela=_resolver_coluna_obrigatoria(dataframe, ("parcela", "n parcela"), nome_exibicao="Parcela"),
        valor_titulo=_resolver_coluna_obrigatoria(
            dataframe,
            ("valor titulo", "valor do titulo", "valor r$"),
            nome_exibicao="Valor Titulo",
        ),
        historico=_resolver_coluna(dataframe, ("historico", "histórico")),
        data=_resolver_coluna(dataframe, ("data", "data pagamento", "data pgto")),
        protocolo=_resolver_coluna(dataframe, ("protocolo",)),
    )


def _preparar_colunas_direta(dataframe: pd.DataFrame) -> DiretaColumns:
    return DiretaColumns(
        cpf=_resolver_coluna_obrigatoria(
            dataframe,
            ("cpf/cnpj", "cpf cnpj", "cpf", "cnpj"),
            fallback_index=5,
            nome_exibicao="CPF/CNPJ (coluna F)",
        ),
        produto=_resolver_coluna_obrigatoria(dataframe, ("produto",), nome_exibicao="Produto"),
        dt_acionamento=_resolver_coluna_obrigatoria(
            dataframe,
            ("dt acionamento", "data acionamento", "dt. acionamento"),
            nome_exibicao="DT ACIONAMENTO",
        ),
        vencimento=_resolver_coluna_obrigatoria(
            dataframe,
            ("venc. parcela", "venc parcela", "vencimento", "data vencimento", "dt vencimento"),
            nome_exibicao="Vencimento",
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


def _classificar_titulo_processada(value: object) -> str:
    classificacao = _classify_title(value)
    if classificacao.kind == "card":
        return "card"
    if classificacao.kind == "chi":
        return "chi"
    return "contract"


def _consolidar_parcela(grupo: pd.DataFrame, titulo_col: str, parcela_col: str) -> str | None:
    contratos: OrderedDict[str, list[str]] = OrderedDict()
    possui_cartao = False
    possui_conta = False

    for _, row in grupo.iterrows():
        titulo = _normalizar_texto_livre(row[titulo_col])
        classificacao = _classificar_titulo_processada(titulo)

        if classificacao == "card":
            possui_cartao = True
            continue
        if classificacao == "chi":
            possui_conta = True
            continue
        if not titulo:
            continue

        if titulo not in contratos:
            contratos[titulo] = []

        parcela = _normalize_parcela(row[parcela_col])
        if parcela and parcela not in contratos[titulo]:
            contratos[titulo].append(parcela)

    grupos = []
    for contrato, parcelas in contratos.items():
        if parcelas:
            grupos.append(f"({contrato}_{'_'.join(parcelas)})")
        else:
            grupos.append(f"({contrato})")

    if possui_cartao:
        grupos.append("(cartao_1)")
    if possui_conta:
        grupos.append("(conta_1)")

    if not grupos:
        return None
    return " ".join(grupos)


def _primeiro_preenchido(serie: pd.Series) -> object:
    for value in serie.tolist():
        if _valor_preenchido(value):
            return value
    return None


def _consolidar_protocolo(serie: pd.Series) -> str | None:
    unicos: list[str] = []
    for value in serie.tolist():
        texto = _normalizar_texto_livre(value)
        if not texto:
            continue
        if texto not in unicos:
            unicos.append(texto)

    if not unicos:
        return None
    if len(unicos) == 1:
        return unicos[0]
    return None


def _selecionar_linha_direta_por_cpf(direta: pd.DataFrame) -> dict[str, pd.Series]:
    lookup: dict[str, pd.Series] = {}
    for cpf, grupo in direta.groupby("_cpf_norm", sort=False):
        if not cpf:
            continue
        lookup[cpf] = grupo.sort_values("_ordem").iloc[0]
    return lookup


def _processar_sudoeste_direto_frames(
    processada_excel: bytes,
    direta_excel: bytes,
) -> pd.DataFrame:
    log_info(logger, "Iniciando processamento de frames", fluxo="sudoeste-direto")
    processada = _ler_tabela_upload(processada_excel, contexto="sudoeste-direto/processada")
    direta = _ler_tabela_upload(direta_excel, contexto="sudoeste-direto/direta")
    log_info(
        logger,
        "Leitura das planilhas concluida",
        fluxo="sudoeste-direto",
        linhas_processada=len(processada),
        linhas_direta=len(direta),
    )

    if processada.empty:
        raise ValueError("A planilha processada esta vazia.")
    if direta.empty:
        raise ValueError("A planilha direta esta vazia.")

    cols_processada = _preparar_colunas_processada(processada)
    cols_direta = _preparar_colunas_direta(direta)
    log_info(
        logger,
        "Validacao de colunas obrigatorias concluida",
        fluxo="sudoeste-direto",
        colunas_processada={
            "associado": cols_processada.associado,
            "cpf": cols_processada.cpf,
            "titulo": cols_processada.titulo,
            "parcela": cols_processada.parcela,
            "valor_titulo": cols_processada.valor_titulo,
        },
        colunas_direta={
            "cpf": cols_direta.cpf,
            "produto": cols_direta.produto,
            "dt_acionamento": cols_direta.dt_acionamento,
            "vencimento": cols_direta.vencimento,
        },
    )

    processada = processada.copy()
    direta = direta.copy()

    processada["_ordem"] = range(len(processada))
    processada["_cpf_norm"] = processada[cols_processada.cpf].apply(_normalize_cpf_cnpj)

    direta["_ordem"] = range(len(direta))
    direta["_cpf_norm"] = direta[cols_direta.cpf].apply(_normalize_cpf_cnpj)

    direta_lookup = _selecionar_linha_direta_por_cpf(direta)

    linhas_saida: list[dict[str, object]] = []
    grupos_total = 0
    grupos_sem_cpf = 0
    grupos_sem_match = 0
    grupos_com_match = 0

    log_info(logger, "Iniciando match por CPF/CNPJ", fluxo="sudoeste-direto")
    for cpf, grupo in processada.groupby("_cpf_norm", sort=False):
        grupos_total += 1
        if not cpf:
            grupos_sem_cpf += 1
            continue
        linha_direta = direta_lookup.get(cpf)
        if linha_direta is None:
            grupos_sem_match += 1
            continue
        grupos_com_match += 1

        grupo_ordenado = grupo.sort_values("_ordem")
        primeira_linha = grupo_ordenado.iloc[0]

        data_consolidada_original = (
            primeira_linha[cols_processada.data] if cols_processada.data else None
        )
        data_consolidada = _formatar_data_para_saida(data_consolidada_original)
        vencimento_original = linha_direta[cols_direta.vencimento]
        vencimento_saida = _formatar_data_para_saida(vencimento_original)

        ag = primeira_linha[cols_processada.ag] if cols_processada.ag else None
        conta = primeira_linha[cols_processada.conta] if cols_processada.conta else None
        associado = primeira_linha[cols_processada.associado]
        cpf_saida = _normalizar_texto_livre(_primeiro_preenchido(grupo_ordenado[cols_processada.cpf]))
        historico = (
            _primeiro_preenchido(grupo_ordenado[cols_processada.historico])
            if cols_processada.historico
            else None
        )
        protocolo = (
            _consolidar_protocolo(grupo_ordenado[cols_processada.protocolo])
            if cols_processada.protocolo
            else None
        )

        linhas_saida.append(
            {
                "AG": ag,
                "Conta": conta,
                "Associado": associado,
                "CPF/CNPJ": cpf_saida,
                "Titulo": linha_direta[cols_direta.produto],
                "Parcela": _consolidar_parcela(grupo_ordenado, cols_processada.titulo, cols_processada.parcela),
                "Valor Título": sum(
                    _converter_valor_titulo(value)
                    for value in grupo_ordenado[cols_processada.valor_titulo]
                ),
                "Histórico": historico,
                "Data": data_consolidada,
                "Atraso": _calcular_atraso(data_consolidada_original, vencimento_original),
                "%receita": None,
                "receita": None,
                "Dt Ultimo Acionamento": _formatar_data_para_saida(linha_direta[cols_direta.dt_acionamento]),
                "Situação": "Pagamento OK",
                "Venc. Parcela": vencimento_saida,
                "Protocolo": protocolo,
            }
        )

    saida = pd.DataFrame(linhas_saida, columns=OUTPUT_COLUMNS_DIRETO)
    log_info(
        logger,
        "Processamento de frames concluido",
        fluxo="sudoeste-direto",
        grupos_total=grupos_total,
        grupos_com_match=grupos_com_match,
        grupos_sem_match=grupos_sem_match,
        grupos_sem_cpf=grupos_sem_cpf,
        linhas_saida=len(saida),
    )
    return saida


def processar_sudoeste_direto_frames(
    processada_excel: bytes,
    direta_excel: bytes,
) -> pd.DataFrame:
    return _processar_sudoeste_direto_frames(processada_excel, direta_excel)


def _exportar_sudoeste_direto(dataframe: pd.DataFrame) -> io.BytesIO:
    log_info(
        logger,
        "Iniciando exportacao de Excel",
        fluxo="sudoeste-direto",
        linhas=len(dataframe),
        sheet_name="Sudoeste Direto",
    )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="Sudoeste Direto", index=False)
    output.seek(0)
    log_info(
        logger,
        "Exportacao de Excel concluida",
        fluxo="sudoeste-direto",
        tamanho_bytes=len(output.getbuffer()),
    )
    return output


def processar_sudoeste_direto(
    processada_excel: bytes,
    direta_excel: bytes,
) -> io.BytesIO:
    log_info(logger, "Iniciando fluxo sudoeste-direto")
    try:
        output_df = processar_sudoeste_direto_frames(processada_excel, direta_excel)
        return _exportar_sudoeste_direto(output_df)
    except Exception:
        log_exception(logger, "Erro no fluxo sudoeste-direto")
        raise
