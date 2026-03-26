import io
import logging
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .logging_utils import configure_logging, log_exception, log_info

configure_logging()
logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
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

DIAGNOSTIC_COLUMNS = [
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
]

SUMMARY_COLUMNS = ["Indicador", "Valor"]

BASE_STATUS_CONFIRMED = "match base confirmado"
BASE_STATUS_MISSING = "sem match na base"
BASE_STATUS_AMBIGUOUS = "match ambiguo na base"
DENODO_STATUS_CONFIRMED = "match denodo confirmado"
DENODO_STATUS_MISSING = "sem match na denodo"
DENODO_STATUS_AMBIGUOUS = "match denodo ambiguo"

CARD_TITLES = {
    "cartoesmaster",
    "cartaovisaempresarial",
    "atrasocartaovisa",
}
CHI_TITLES = {
    "inadimplenciachequeespecial",
    "inadimplenciajurosadiantamento",
}
CARD_ABBREVIATIONS = {"mas", "car"}
CHI_ABBREVIATIONS = {"chi"}


@dataclass(frozen=True)
class TitleClassification:
    kind: str
    key: str


@dataclass(frozen=True)
class CandidatePool:
    title_candidates: tuple[int, ...]
    support_candidates: tuple[int, ...]
    candidate_indexes: tuple[int, ...]


@dataclass(frozen=True)
class RecebimentoStats:
    total_entrada: int
    total_consideradas: int
    total_ignoradas_historico: int


@dataclass
class BaseMatchDecision:
    status: str
    detail: str
    matched_row: pd.Series | None = None
    matched_index: int | None = None
    matched_key: str | None = None
    candidate_indexes: tuple[int, ...] = ()
    scored_candidates: tuple[tuple[int, int], ...] = ()


@dataclass
class DenodoLookupEntry:
    status: str
    protocolo: str | None
    protocolos: tuple[str, ...]
    source_rows: tuple[int, ...]


@dataclass
class DenodoMatchDecision:
    status: str
    detail: str
    protocolo: str | None = None
    lookup_key: str | None = None
    protocolos: tuple[str, ...] = ()
    source_rows: tuple[int, ...] = ()


def _strip_accents(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass

    text = unicodedata.normalize("NFKD", str(value))
    return text.encode("ascii", "ignore").decode("ascii")


def _normalize_text(value: object) -> str:
    text = _strip_accents(value).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _normalize_cpf_cnpj(value: object) -> str:
    return re.sub(r"\D+", "", _strip_accents(value))


def _normalize_contract(value: object) -> str:
    text = _strip_accents(value).upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def _normalize_parcela(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass

    if isinstance(value, (int, np.integer)):
        return str(int(value))

    if isinstance(value, (float, np.floating)):
        if float(value).is_integer():
            return str(int(value))
        return _normalize_text(value)

    text = str(value).strip()
    if not text:
        return ""

    if re.fullmatch(r"\d+(?:[.,]0+)?", text):
        return str(int(float(text.replace(",", "."))))

    return _normalize_text(text)


def _is_contract_token(normalized_contract: str) -> bool:
    if not normalized_contract:
        return False
    if normalized_contract in {"CHI", "MAS", "CAR"}:
        return False
    return any(char.isdigit() for char in normalized_contract)


def _classify_title(value: object) -> TitleClassification:
    raw_text = _normalize_text(value)
    contract = _normalize_contract(value)

    if raw_text in CARD_TITLES or raw_text in CARD_ABBREVIATIONS:
        return TitleClassification(kind="card", key="cartao")

    if raw_text in CHI_TITLES or raw_text in CHI_ABBREVIATIONS:
        return TitleClassification(kind="chi", key="chi")

    if _is_contract_token(contract):
        return TitleClassification(kind="contract", key=contract)

    return TitleClassification(kind="text", key=raw_text)


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


def _ler_tabela_upload(arquivo: bytes, *, contexto: str = "upload") -> pd.DataFrame:
    log_info(
        logger,
        "Iniciando leitura de planilha",
        contexto=contexto,
        tamanho_bytes=len(arquivo),
    )
    assinatura = arquivo[:4]
    if assinatura.startswith(b"PK") or assinatura == b"\xd0\xcf\x11\xe0":
        dataframe = pd.read_excel(io.BytesIO(arquivo))
        log_info(
            logger,
            "Leitura de planilha concluida",
            contexto=contexto,
            formato="xlsx",
            linhas=len(dataframe),
            colunas=len(dataframe.columns),
        )
        return dataframe

    for encoding in ("utf-8-sig", "latin1"):
        try:
            dataframe = pd.read_csv(io.BytesIO(arquivo), sep=";", encoding=encoding)
            log_info(
                logger,
                "Leitura de planilha concluida",
                contexto=contexto,
                formato="csv",
                encoding=encoding,
                linhas=len(dataframe),
                colunas=len(dataframe.columns),
            )
            return dataframe
        except Exception:  # pragma: no cover
            continue

    try:
        dataframe = pd.read_excel(io.BytesIO(arquivo))
        log_info(
            logger,
            "Leitura de planilha concluida",
            contexto=contexto,
            formato="xlsx-fallback",
            linhas=len(dataframe),
            colunas=len(dataframe.columns),
        )
        return dataframe
    except Exception as exc:
        log_exception(
            logger,
            "Falha ao interpretar arquivo de upload",
            contexto=contexto,
        )
        raise ValueError("Arquivo enviado nao esta em um formato CSV/XLSX valido.") from exc


def _converter_data(valor: object):
    try:
        if pd.isna(valor):
            return pd.NaT
    except TypeError:
        pass

    if isinstance(valor, pd.Timestamp):
        return valor

    if isinstance(valor, (int, float, np.integer, np.floating)):
        return pd.to_datetime(valor, unit="D", origin="1899-12-30")

    return pd.to_datetime(valor, dayfirst=True, errors="coerce")


def _formatar_data_saida(valor: object) -> str | None:
    data = _converter_data(valor)
    if pd.isna(data):
        return None
    return data.strftime("%d/%m/%Y")


def _formatar_vencimento_saida(valor: object) -> str | None:
    data = _converter_data(valor)
    if pd.notna(data):
        return data.strftime("%d/%m/%Y")

    try:
        if pd.isna(valor):
            return None
    except TypeError:
        pass

    texto = str(valor).strip()
    return texto or None


def _coalesce(*values: object) -> object:
    for value in values:
        try:
            if pd.isna(value):
                continue
        except TypeError:
            pass
        if isinstance(value, str) and not value.strip():
            continue
        if value in ("", None):
            continue
        return value
    return None


def _stringify_indices(indices: tuple[int, ...], dataframe: pd.DataFrame) -> str | None:
    if not indices:
        return None
    return ", ".join(str(int(dataframe.iloc[idx]["_source_row"])) for idx in indices)


def _stringify_values(values: tuple[object, ...]) -> str | None:
    if not values:
        return None
    return ", ".join(str(value) for value in values)


def _format_match_key(kind: str, key: str) -> str | None:
    if not key:
        return None
    return f"tipo={kind}; chave={key}"


def _format_denodo_lookup_key(cpf: str, kind: str, key: str) -> str | None:
    if not cpf or not key:
        return None
    return f"cpf={cpf}; tipo={kind}; chave={key}"


def _prepare_base(df_base: pd.DataFrame) -> pd.DataFrame:
    associado_col = _require_column(df_base, "associado", "nome/razao", "nome razao")
    cpf_col = _require_column(df_base, "cpf", "cpf/cnpj", "cpf cnpj")
    contrato_col = _require_column(
        df_base,
        "n do contrato",
        "no do contrato",
        "numero do contrato",
        "n contrato",
        "contrato",
        "titulo",
    )
    parcela_col = _require_column(df_base, "n parcela", "no parcela", "numero parcela", "parcela")

    base = df_base.copy()
    base["_source_row"] = base.index + 2
    base["_associado_col"] = associado_col
    base["_cpf_col"] = cpf_col
    base["_contrato_col"] = contrato_col
    base["_parcela_col"] = parcela_col
    base["_ag_col"] = _find_column(base, "ag", "agencia", "ag.")
    base["_conta_col"] = _find_column(base, "conta")
    base["_vencimento_col"] = _find_column(base, "vencimento", "venc. parcela", "venc parcela")
    base["_associado_norm"] = base[associado_col].apply(_normalize_text)
    base["_cpf_norm"] = base[cpf_col].apply(_normalize_cpf_cnpj)
    base["_parcela_norm"] = base[parcela_col].apply(_normalize_parcela)
    base["_title_class"] = base[contrato_col].apply(_classify_title)
    base["_title_kind"] = base["_title_class"].map(lambda item: item.kind)
    base["_title_key"] = base["_title_class"].map(lambda item: item.key)

    dedupe_columns = [
        "_cpf_norm",
        "_title_kind",
        "_title_key",
        "_parcela_norm",
        "_associado_norm",
    ]
    base_preparada = base.drop_duplicates(subset=dedupe_columns).reset_index(drop=True)
    log_info(
        logger,
        "Base preparada e validada",
        fluxo="sudoeste-inicial",
        linhas_entrada=len(df_base),
        linhas_pos_deduplicacao=len(base_preparada),
        colunas_obrigatorias={
            "associado": associado_col,
            "cpf": cpf_col,
            "contrato": contrato_col,
            "parcela": parcela_col,
        },
    )
    return base_preparada


def _prepare_recebimento(df_recebimento: pd.DataFrame) -> tuple[pd.DataFrame, RecebimentoStats]:
    associado_col = _require_column(df_recebimento, "associado", "nome/razao", "nome razao")
    titulo_col = _require_column(df_recebimento, "titulo", "title")
    parcela_col = _require_column(df_recebimento, "parcela", "n parcela")
    valor_col = _require_column(df_recebimento, "valor titulo", "valor do titulo")
    historico_col = _require_column(df_recebimento, "historico")
    data_col = _require_column(df_recebimento, "data", "data pagamento", "data pgto")

    recebimento = df_recebimento.copy()
    cpf_col = _find_column(recebimento, "cpf", "cpf/cnpj", "cpf cnpj")
    recebimento["_source_row"] = recebimento.index + 2
    recebimento["_associado_col"] = associado_col
    recebimento["_titulo_col"] = titulo_col
    recebimento["_parcela_col"] = parcela_col
    recebimento["_valor_col"] = valor_col
    recebimento["_historico_col"] = historico_col
    recebimento["_data_col"] = data_col
    recebimento["_cpf_col"] = cpf_col
    recebimento["_ag_col"] = _find_column(recebimento, "ag", "agencia", "ag.")
    recebimento["_conta_col"] = _find_column(recebimento, "conta")

    total_entrada = len(recebimento)
    historico_numerico = pd.to_numeric(recebimento[historico_col], errors="coerce")
    filtro_historico = historico_numerico.isin([1, 2, 3, 4]) | historico_numerico.isna()
    total_consideradas = int(filtro_historico.sum())
    total_ignoradas_historico = int((~filtro_historico).sum())

    recebimento = recebimento[filtro_historico].copy()
    if recebimento.empty:
        raise ValueError("Nenhuma linha valida encontrada no recebimento apos filtrar Historico.")

    recebimento["_ordem"] = range(len(recebimento))
    recebimento["_historico_saida"] = historico_numerico.loc[recebimento.index].apply(
        lambda value: int(value) if pd.notna(value) else None
    )
    recebimento["_data_pagamento"] = recebimento[data_col].apply(_converter_data)
    recebimento["_associado_norm"] = recebimento[associado_col].apply(_normalize_text)
    recebimento["_cpf_norm"] = (
        recebimento[cpf_col].apply(_normalize_cpf_cnpj)
        if cpf_col
        else ""
    )
    recebimento["_parcela_norm"] = recebimento[parcela_col].apply(_normalize_parcela)
    recebimento["_title_class"] = recebimento[titulo_col].apply(_classify_title)
    recebimento["_title_kind"] = recebimento["_title_class"].map(lambda item: item.kind)
    recebimento["_title_key"] = recebimento["_title_class"].map(lambda item: item.key)

    stats = RecebimentoStats(
        total_entrada=total_entrada,
        total_consideradas=total_consideradas,
        total_ignoradas_historico=total_ignoradas_historico,
    )
    recebimento_preparado = recebimento.reset_index(drop=True)
    log_info(
        logger,
        "Recebimento preparado e validado",
        fluxo="sudoeste-inicial",
        linhas_entrada=total_entrada,
        linhas_consideradas=total_consideradas,
        linhas_ignoradas_historico=total_ignoradas_historico,
        colunas_obrigatorias={
            "associado": associado_col,
            "titulo": titulo_col,
            "parcela": parcela_col,
            "valor_titulo": valor_col,
            "historico": historico_col,
            "data": data_col,
        },
        coluna_cpf=cpf_col,
    )
    return recebimento_preparado, stats


def _prepare_denodo(df_denodo: pd.DataFrame) -> pd.DataFrame:
    protocolo_col = _require_column(df_denodo, "protocolo")
    cpf_col = _require_column(df_denodo, "cpf_cnpj_formatado", "cpf cnpj formatado", "cpf/cnpj formatado")
    solucao_col = _require_column(df_denodo, "solucao_associada", "solucao associada")

    denodo = df_denodo.copy()
    denodo["_source_row"] = denodo.index + 2
    denodo["_protocolo_col"] = protocolo_col
    denodo["_cpf_col"] = cpf_col
    denodo["_solucao_col"] = solucao_col
    denodo["_cpf_norm"] = denodo[cpf_col].apply(_normalize_cpf_cnpj)
    denodo["_title_class"] = denodo[solucao_col].apply(_classify_title)
    denodo["_title_kind"] = denodo["_title_class"].map(lambda item: item.kind)
    denodo["_title_key"] = denodo["_title_class"].map(lambda item: item.key)
    log_info(
        logger,
        "Denodo preparado e validado",
        fluxo="sudoeste-inicial",
        linhas=len(denodo),
        colunas_obrigatorias={
            "protocolo": protocolo_col,
            "cpf": cpf_col,
            "solucao_associada": solucao_col,
        },
    )
    return denodo


def _build_base_indexes(base: pd.DataFrame) -> dict[str, dict[object, list[int]]]:
    by_cpf: dict[str, list[int]] = defaultdict(list)
    by_associado: dict[str, list[int]] = defaultdict(list)
    by_title: dict[tuple[str, str], list[int]] = defaultdict(list)

    for idx, row in base.iterrows():
        if row["_cpf_norm"]:
            by_cpf[row["_cpf_norm"]].append(idx)
        if row["_associado_norm"]:
            by_associado[row["_associado_norm"]].append(idx)
        if row["_title_key"]:
            by_title[(row["_title_kind"], row["_title_key"])].append(idx)

    return {"by_cpf": by_cpf, "by_associado": by_associado, "by_title": by_title}


def _build_candidate_pool(
    recebimento_row: pd.Series,
    indexes: dict[str, dict[object, list[int]]],
) -> CandidatePool:
    kind = recebimento_row["_title_kind"]
    key = recebimento_row["_title_key"]
    cpf = recebimento_row["_cpf_norm"]
    associado = recebimento_row["_associado_norm"]

    title_candidates = set(indexes["by_title"].get((kind, key), [])) if key else set()
    support_candidates = set()

    if cpf:
        support_candidates.update(indexes["by_cpf"].get(cpf, []))
    if associado:
        support_candidates.update(indexes["by_associado"].get(associado, []))

    if kind in {"contract", "card", "chi", "text"}:
        if title_candidates and support_candidates:
            intersection = title_candidates & support_candidates
            candidate_indexes = intersection if intersection else title_candidates
        else:
            candidate_indexes = title_candidates
    else:
        candidate_indexes = support_candidates

    return CandidatePool(
        title_candidates=tuple(sorted(title_candidates)),
        support_candidates=tuple(sorted(support_candidates)),
        candidate_indexes=tuple(sorted(candidate_indexes)),
    )


def _score_base_match(recebimento_row: pd.Series, base_row: pd.Series) -> int | None:
    same_cpf = bool(recebimento_row["_cpf_norm"]) and recebimento_row["_cpf_norm"] == base_row["_cpf_norm"]
    same_associado = bool(recebimento_row["_associado_norm"]) and recebimento_row["_associado_norm"] == base_row["_associado_norm"]
    same_parcela = (
        bool(recebimento_row["_parcela_norm"])
        and bool(base_row["_parcela_norm"])
        and recebimento_row["_parcela_norm"] == base_row["_parcela_norm"]
    )
    parcela_conflict = (
        bool(recebimento_row["_parcela_norm"])
        and bool(base_row["_parcela_norm"])
        and recebimento_row["_parcela_norm"] != base_row["_parcela_norm"]
    )
    same_kind = recebimento_row["_title_kind"] == base_row["_title_kind"]
    same_key = recebimento_row["_title_key"] == base_row["_title_key"]

    if not same_kind or not same_key:
        return None

    kind = recebimento_row["_title_kind"]
    if kind == "contract":
        if not (same_cpf or same_associado) or parcela_conflict:
            return None
        score = 100
        if same_cpf:
            score += 40
        if same_parcela:
            score += 25
        if same_associado:
            score += 10
        return score

    if kind in {"card", "chi"}:
        if not (same_cpf or same_associado) or parcela_conflict:
            return None
        score = 80
        if same_cpf:
            score += 30
        if same_parcela:
            score += 20
        if same_associado:
            score += 10
        return score

    matched_supports = sum([same_cpf, same_associado, same_parcela])
    if matched_supports < 2:
        return None

    score = 40
    if same_cpf:
        score += 25
    if same_associado:
        score += 15
    if same_parcela:
        score += 10
    return score


def _describe_base_missing(recebimento_row: pd.Series, pool: CandidatePool) -> str:
    if not pool.title_candidates:
        return (
            "nenhuma linha da base para "
            f"tipo={recebimento_row['_title_kind']} chave={recebimento_row['_title_key'] or '<vazia>'}"
        )
    if not pool.support_candidates:
        return "candidatos por titulo existem, mas nao houve apoio seguro por CPF ou associado"
    return "candidatos encontrados na base, mas todos foram reprovados pela regra de seguranca"


def _find_best_base_match(
    recebimento_row: pd.Series,
    base: pd.DataFrame,
    indexes: dict[str, dict[object, list[int]]],
) -> BaseMatchDecision:
    pool = _build_candidate_pool(recebimento_row, indexes)
    if not pool.candidate_indexes:
        return BaseMatchDecision(
            status=BASE_STATUS_MISSING,
            detail=_describe_base_missing(recebimento_row, pool),
            candidate_indexes=pool.candidate_indexes,
        )

    scored_candidates: list[tuple[int, int]] = []
    for idx in pool.candidate_indexes:
        score = _score_base_match(recebimento_row, base.iloc[idx])
        if score is not None:
            scored_candidates.append((score, idx))

    if not scored_candidates:
        return BaseMatchDecision(
            status=BASE_STATUS_MISSING,
            detail=_describe_base_missing(recebimento_row, pool),
            candidate_indexes=pool.candidate_indexes,
        )

    scored_candidates.sort(reverse=True)
    best_score, best_idx = scored_candidates[0]
    tied_candidates = tuple(idx for score, idx in scored_candidates if score == best_score)

    if len(tied_candidates) > 1:
        return BaseMatchDecision(
            status=BASE_STATUS_AMBIGUOUS,
            detail=f"empate entre linhas da base com score {best_score}: {_stringify_indices(tied_candidates, base)}",
            candidate_indexes=pool.candidate_indexes,
            scored_candidates=tuple(scored_candidates),
        )

    matched_row = base.iloc[best_idx]
    return BaseMatchDecision(
        status=BASE_STATUS_CONFIRMED,
        detail=f"linha {int(matched_row['_source_row'])} da base confirmada com score {best_score}",
        matched_row=matched_row,
        matched_index=best_idx,
        matched_key=_format_match_key(matched_row["_title_kind"], matched_row["_title_key"]),
        candidate_indexes=pool.candidate_indexes,
        scored_candidates=tuple(scored_candidates),
    )


def _build_denodo_lookup(denodo: pd.DataFrame) -> dict[tuple[str, str, str], DenodoLookupEntry]:
    grouped: dict[tuple[str, str, str], dict[str, list[object]]] = defaultdict(lambda: {"protocolos": [], "source_rows": []})

    for _, row in denodo.iterrows():
        cpf = row["_cpf_norm"]
        kind = row["_title_kind"]
        key = row["_title_key"]
        protocolo = str(row[row["_protocolo_col"]]).strip()
        if not cpf or not key or not protocolo:
            continue

        match_key = (cpf, kind, key)
        grouped[match_key]["protocolos"].append(protocolo)
        grouped[match_key]["source_rows"].append(int(row["_source_row"]))

    lookup: dict[tuple[str, str, str], DenodoLookupEntry] = {}
    for match_key, values in grouped.items():
        protocolos = tuple(sorted(set(values["protocolos"])))
        source_rows = tuple(sorted(set(int(row) for row in values["source_rows"])))
        if len(protocolos) == 1:
            lookup[match_key] = DenodoLookupEntry(
                status=DENODO_STATUS_CONFIRMED,
                protocolo=protocolos[0],
                protocolos=protocolos,
                source_rows=source_rows,
            )
        else:
            lookup[match_key] = DenodoLookupEntry(
                status=DENODO_STATUS_AMBIGUOUS,
                protocolo=None,
                protocolos=protocolos,
                source_rows=source_rows,
            )
    return lookup


def _find_denodo_match(
    recebimento_row: pd.Series,
    base_decision: BaseMatchDecision,
    lookup: dict[tuple[str, str, str], DenodoLookupEntry],
) -> DenodoMatchDecision:
    cpf = recebimento_row["_cpf_norm"]
    if not cpf and base_decision.matched_row is not None:
        cpf = base_decision.matched_row["_cpf_norm"]

    if base_decision.matched_row is not None:
        kind = base_decision.matched_row["_title_kind"]
        key = base_decision.matched_row["_title_key"]
    else:
        kind = recebimento_row["_title_kind"]
        key = recebimento_row["_title_key"]

    lookup_key_str = _format_denodo_lookup_key(cpf, kind, key)
    if not cpf:
        return DenodoMatchDecision(
            status=DENODO_STATUS_MISSING,
            detail="CPF/CNPJ ausente para consultar a denodo",
            lookup_key=lookup_key_str,
        )
    if not key:
        return DenodoMatchDecision(
            status=DENODO_STATUS_MISSING,
            detail="chave de titulo/contrato ausente para consultar a denodo",
            lookup_key=lookup_key_str,
        )

    lookup_key = (cpf, kind, key)
    entry = lookup.get(lookup_key)
    if entry is None:
        return DenodoMatchDecision(
            status=DENODO_STATUS_MISSING,
            detail=f"nenhum registro na denodo para tipo={kind} chave={key}",
            lookup_key=lookup_key_str,
        )

    if entry.status == DENODO_STATUS_AMBIGUOUS:
        return DenodoMatchDecision(
            status=DENODO_STATUS_AMBIGUOUS,
            detail=f"multiplos protocolos na denodo para a mesma chave: {_stringify_values(entry.protocolos)}",
            lookup_key=lookup_key_str,
            protocolos=entry.protocolos,
            source_rows=entry.source_rows,
        )

    return DenodoMatchDecision(
        status=DENODO_STATUS_CONFIRMED,
        detail=f"protocolo {entry.protocolo} confirmado na(s) linha(s) {_stringify_values(entry.source_rows)}",
        protocolo=entry.protocolo,
        lookup_key=lookup_key_str,
        protocolos=entry.protocolos,
        source_rows=entry.source_rows,
    )


def _build_output_row(
    recebimento_row: pd.Series,
    base_decision: BaseMatchDecision,
    denodo_decision: DenodoMatchDecision,
) -> dict[str, object]:
    base_row = base_decision.matched_row

    recebimento_ag = recebimento_row[recebimento_row["_ag_col"]] if recebimento_row["_ag_col"] else None
    recebimento_conta = recebimento_row[recebimento_row["_conta_col"]] if recebimento_row["_conta_col"] else None
    recebimento_cpf = recebimento_row[recebimento_row["_cpf_col"]] if recebimento_row["_cpf_col"] else None

    base_ag = base_row[base_row["_ag_col"]] if base_row is not None and base_row["_ag_col"] else None
    base_conta = base_row[base_row["_conta_col"]] if base_row is not None and base_row["_conta_col"] else None
    base_associado = base_row[base_row["_associado_col"]] if base_row is not None else None
    base_cpf = base_row[base_row["_cpf_col"]] if base_row is not None else None
    base_titulo = base_row[base_row["_contrato_col"]] if base_row is not None else None
    base_vencimento = (
        base_row[base_row["_vencimento_col"]]
        if base_row is not None and base_row["_vencimento_col"]
        else None
    )

    return {
        "AG": _coalesce(recebimento_ag, base_ag),
        "Conta": _coalesce(recebimento_conta, base_conta),
        "Associado": _coalesce(recebimento_row[recebimento_row["_associado_col"]], base_associado),
        "CPF/CNPJ": _coalesce(recebimento_cpf, base_cpf),
        "Titulo": _coalesce(recebimento_row[recebimento_row["_titulo_col"]], base_titulo),
        "Parcela": recebimento_row[recebimento_row["_parcela_col"]],
        "Valor Título": recebimento_row[recebimento_row["_valor_col"]],
        "Histórico": recebimento_row["_historico_saida"],
        "Data": _formatar_data_saida(recebimento_row["_data_pagamento"]),
        "Atraso": None,
        "%receita": None,
        "receita": None,
        "Dt Ultimo Acionamento": None,
        "Situação": None,
        "Venc. Parcela": _formatar_vencimento_saida(base_vencimento),
        "Protocolo": denodo_decision.protocolo,
    }


def _build_diagnostic_row(
    recebimento_row: pd.Series,
    base_decision: BaseMatchDecision,
    denodo_decision: DenodoMatchDecision,
) -> dict[str, object]:
    recebimento_cpf = recebimento_row[recebimento_row["_cpf_col"]] if recebimento_row["_cpf_col"] else None
    base_line = int(base_decision.matched_row["_source_row"]) if base_decision.matched_row is not None else None

    return {
        "Linha Recebimento": int(recebimento_row["_source_row"]),
        "Associado": recebimento_row[recebimento_row["_associado_col"]],
        "CPF/CNPJ": recebimento_cpf,
        "Titulo": recebimento_row[recebimento_row["_titulo_col"]],
        "Parcela": recebimento_row[recebimento_row["_parcela_col"]],
        "Tipo Titulo Recebimento": recebimento_row["_title_kind"],
        "Chave Normalizada Recebimento": recebimento_row["_title_key"],
        "CPF Normalizado": recebimento_row["_cpf_norm"] or None,
        "Parcela Normalizada": recebimento_row["_parcela_norm"] or None,
        "Associado Normalizado": recebimento_row["_associado_norm"] or None,
        "Status Base": base_decision.status,
        "Detalhe Base": base_decision.detail,
        "Linha Base": base_line,
        "Chave Base Selecionada": base_decision.matched_key,
        "Status Denodo": denodo_decision.status,
        "Detalhe Denodo": denodo_decision.detail,
        "Chave Denodo Selecionada": denodo_decision.lookup_key,
        "Linhas Denodo": _stringify_values(denodo_decision.source_rows),
        "Protocolos Denodo": _stringify_values(denodo_decision.protocolos),
        "Protocolo Resultado": denodo_decision.protocolo,
    }


def _gerar_resumo_execucao(
    diagnostico_df: pd.DataFrame,
    recebimento_stats: RecebimentoStats,
) -> pd.DataFrame:
    resumo_rows = [
        {"Indicador": "total de linhas recebimento consideradas", "Valor": int(recebimento_stats.total_consideradas)},
        {"Indicador": "total de linhas ignoradas por historico", "Valor": int(recebimento_stats.total_ignoradas_historico)},
        {"Indicador": "total com match base confirmado", "Valor": int((diagnostico_df["Status Base"] == BASE_STATUS_CONFIRMED).sum())},
        {"Indicador": "total sem match base", "Valor": int((diagnostico_df["Status Base"] == BASE_STATUS_MISSING).sum())},
        {"Indicador": "total match base ambiguo", "Valor": int((diagnostico_df["Status Base"] == BASE_STATUS_AMBIGUOUS).sum())},
        {"Indicador": "total com protocolo confirmado", "Valor": int((diagnostico_df["Status Denodo"] == DENODO_STATUS_CONFIRMED).sum())},
        {"Indicador": "total sem match denodo", "Valor": int((diagnostico_df["Status Denodo"] == DENODO_STATUS_MISSING).sum())},
        {"Indicador": "total match denodo ambiguo", "Valor": int((diagnostico_df["Status Denodo"] == DENODO_STATUS_AMBIGUOUS).sum())},
    ]
    return pd.DataFrame(resumo_rows, columns=SUMMARY_COLUMNS)


def _exportar_excel(dataframe: pd.DataFrame, sheet_name: str) -> io.BytesIO:
    log_info(
        logger,
        "Iniciando exportacao de Excel",
        fluxo="sudoeste-inicial",
        sheet_name=sheet_name,
        linhas=len(dataframe),
    )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    log_info(
        logger,
        "Exportacao de Excel concluida",
        fluxo="sudoeste-inicial",
        sheet_name=sheet_name,
        tamanho_bytes=len(output.getbuffer()),
    )
    return output


def _exportar_diagnostico_com_resumo(diagnostico_df: pd.DataFrame, resumo_df: pd.DataFrame) -> io.BytesIO:
    log_info(
        logger,
        "Iniciando exportacao de diagnostico com resumo",
        fluxo="sudoeste-inicial",
        linhas_diagnostico=len(diagnostico_df),
        linhas_resumo=len(resumo_df),
    )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        resumo_df.to_excel(writer, sheet_name="Resumo", index=False)
        diagnostico_df.to_excel(writer, sheet_name="Diagnostico", index=False)
    output.seek(0)
    log_info(
        logger,
        "Exportacao de diagnostico com resumo concluida",
        fluxo="sudoeste-inicial",
        tamanho_bytes=len(output.getbuffer()),
    )
    return output


def _processar_sudoeste_frames(
    base_excel: bytes,
    recebimento_excel: bytes,
    denodo_excel: bytes,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    log_info(logger, "Iniciando processamento de frames", fluxo="sudoeste-inicial")
    try:
        df_base = _ler_tabela_upload(base_excel, contexto="sudoeste-inicial/base")
        df_recebimento = _ler_tabela_upload(recebimento_excel, contexto="sudoeste-inicial/recebimento")
        df_denodo = _ler_tabela_upload(denodo_excel, contexto="sudoeste-inicial/denodo")

        log_info(
            logger,
            "Leitura das planilhas concluida",
            fluxo="sudoeste-inicial",
            linhas_base=len(df_base),
            linhas_recebimento=len(df_recebimento),
            linhas_denodo=len(df_denodo),
        )

        base = _prepare_base(df_base)
        recebimento, recebimento_stats = _prepare_recebimento(df_recebimento)
        denodo = _prepare_denodo(df_denodo)

        base_indexes = _build_base_indexes(base)
        denodo_lookup = _build_denodo_lookup(denodo)

        output_rows = []
        diagnostic_rows = []

        log_info(
            logger,
            "Iniciando etapa de match",
            fluxo="sudoeste-inicial",
            linhas_recebimento_consideradas=len(recebimento),
        )
        for _, recebimento_row in recebimento.sort_values("_ordem").iterrows():
            base_decision = _find_best_base_match(recebimento_row, base, base_indexes)
            denodo_decision = _find_denodo_match(recebimento_row, base_decision, denodo_lookup)
            output_rows.append(_build_output_row(recebimento_row, base_decision, denodo_decision))
            diagnostic_rows.append(_build_diagnostic_row(recebimento_row, base_decision, denodo_decision))

        output_df = pd.DataFrame(output_rows, columns=OUTPUT_COLUMNS)
        diagnostic_df = pd.DataFrame(diagnostic_rows, columns=DIAGNOSTIC_COLUMNS)
        resumo_df = _gerar_resumo_execucao(diagnostic_df, recebimento_stats)

        log_info(
            logger,
            "Processamento de frames concluido",
            fluxo="sudoeste-inicial",
            linhas_saida=len(output_df),
            linhas_diagnostico=len(diagnostic_df),
            base_match_confirmado=int((diagnostic_df["Status Base"] == BASE_STATUS_CONFIRMED).sum()),
            base_match_ausente=int((diagnostic_df["Status Base"] == BASE_STATUS_MISSING).sum()),
            base_match_ambiguo=int((diagnostic_df["Status Base"] == BASE_STATUS_AMBIGUOUS).sum()),
            denodo_match_confirmado=int((diagnostic_df["Status Denodo"] == DENODO_STATUS_CONFIRMED).sum()),
            denodo_match_ausente=int((diagnostic_df["Status Denodo"] == DENODO_STATUS_MISSING).sum()),
            denodo_match_ambiguo=int((diagnostic_df["Status Denodo"] == DENODO_STATUS_AMBIGUOUS).sum()),
        )
        return output_df, diagnostic_df, resumo_df
    except Exception:
        log_exception(logger, "Falha durante processamento de frames", fluxo="sudoeste-inicial")
        raise


def processar_sudoeste(
    base_excel: bytes,
    recebimento_excel: bytes,
    denodo_excel: bytes,
) -> io.BytesIO:
    log_info(logger, "Iniciando fluxo sudoeste-inicial")
    try:
        output_df, _, _ = _processar_sudoeste_frames(base_excel, recebimento_excel, denodo_excel)
        return _exportar_excel(output_df, "Sudoeste Inicial")
    except Exception:
        log_exception(logger, "Erro no fluxo sudoeste-inicial")
        raise


def diagnosticar_sudoeste(
    base_excel: bytes,
    recebimento_excel: bytes,
    denodo_excel: bytes,
) -> pd.DataFrame:
    log_info(logger, "Iniciando geracao de diagnostico sudoeste-inicial")
    try:
        _, diagnostic_df, _ = _processar_sudoeste_frames(base_excel, recebimento_excel, denodo_excel)
        return diagnostic_df
    except Exception:
        log_exception(logger, "Erro ao gerar diagnostico sudoeste-inicial")
        raise


def resumir_execucao_sudoeste(
    base_excel: bytes,
    recebimento_excel: bytes,
    denodo_excel: bytes,
) -> pd.DataFrame:
    log_info(logger, "Iniciando geracao de resumo sudoeste-inicial")
    try:
        _, _, resumo_df = _processar_sudoeste_frames(base_excel, recebimento_excel, denodo_excel)
        return resumo_df
    except Exception:
        log_exception(logger, "Erro ao gerar resumo sudoeste-inicial")
        raise


def processar_sudoeste_com_diagnostico(
    base_excel: bytes,
    recebimento_excel: bytes,
    denodo_excel: bytes,
) -> tuple[io.BytesIO, pd.DataFrame]:
    log_info(logger, "Iniciando fluxo sudoeste-inicial com diagnostico")
    try:
        output_df, diagnostic_df, _ = _processar_sudoeste_frames(base_excel, recebimento_excel, denodo_excel)
        return _exportar_excel(output_df, "Sudoeste Inicial"), diagnostic_df
    except Exception:
        log_exception(logger, "Erro no fluxo sudoeste-inicial com diagnostico")
        raise


def processar_sudoeste_com_diagnostico_e_resumo(
    base_excel: bytes,
    recebimento_excel: bytes,
    denodo_excel: bytes,
) -> tuple[io.BytesIO, pd.DataFrame, pd.DataFrame]:
    log_info(logger, "Iniciando fluxo sudoeste-inicial com diagnostico e resumo")
    try:
        output_df, diagnostic_df, resumo_df = _processar_sudoeste_frames(base_excel, recebimento_excel, denodo_excel)
        return _exportar_excel(output_df, "Sudoeste Inicial"), diagnostic_df, resumo_df
    except Exception:
        log_exception(logger, "Erro no fluxo sudoeste-inicial com diagnostico e resumo")
        raise


def exportar_diagnostico_sudoeste(
    base_excel: bytes,
    recebimento_excel: bytes,
    denodo_excel: bytes,
) -> io.BytesIO:
    log_info(logger, "Iniciando exportacao de diagnostico sudoeste-inicial")
    try:
        _, diagnostic_df, resumo_df = _processar_sudoeste_frames(base_excel, recebimento_excel, denodo_excel)
        return _exportar_diagnostico_com_resumo(diagnostic_df, resumo_df)
    except Exception:
        log_exception(logger, "Erro ao exportar diagnostico sudoeste-inicial")
        raise
