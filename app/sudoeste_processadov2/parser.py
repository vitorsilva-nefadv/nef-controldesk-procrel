import re
import unicodedata


CONTRATO_PATTERN = re.compile(
    r"(?<![A-Z0-9-])(C[A-Z0-9-]*\d)(?=[_+\s]|$)",
    flags=re.IGNORECASE,
)

TOKENS_CARTAO = {"cartao", "cartoes", "mas", "car"}
TOKENS_CHI = {"chi", "inadimplencia"}
FRASES_CHI = ("cheque especial", "conta corrente")


def normalizar_texto(valor: object) -> str:
    """Normaliza texto para facilitar comparações de negócio."""
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return texto.lower().strip()


def normalizar_cpf_cnpj(valor: object) -> str:
    """Remove qualquer caractere não numérico de CPF/CNPJ."""
    return re.sub(r"\D+", "", normalizar_texto(valor))


def normalizar_contrato(valor: object) -> str:
    """Padroniza contrato removendo pontuações e espaços."""
    texto = normalizar_texto(valor).upper()
    return re.sub(r"[^A-Z0-9]+", "", texto)


def normalizar_parcela(valor: object) -> str:
    """Padroniza parcela para string simples (ex.: 12.0 -> '12')."""
    if valor is None:
        return ""

    texto = str(valor).strip()
    if not texto:
        return ""

    if re.fullmatch(r"\d+(?:[.,]0+)?", texto):
        return str(int(float(texto.replace(",", "."))))
    return re.sub(r"\D+", "", texto)


def classificar_titulo_inicial(titulo: object) -> str:
    """
    Classifica o título do inicial processado.

    Retornos:
    - contrato
    - cartao
    - chi
    - ignorar
    """
    texto = normalizar_texto(titulo)
    if not texto:
        return "ignorar"

    if texto in {"mas", "car"}:
        return "cartao"
    if texto == "chi":
        return "chi"

    contrato = normalizar_contrato(titulo)
    if contrato.startswith("C") and any(char.isdigit() for char in contrato):
        return "contrato"
    return "ignorar"


def _tokenizar_produto(produto: object) -> set[str]:
    texto = normalizar_texto(produto)
    return set(re.findall(r"[a-z0-9]+", texto))


def produto_eh_cartao(produto: object) -> bool:
    """Retorna True quando o produto representa cartão."""
    texto = normalizar_texto(produto)
    tokens = _tokenizar_produto(produto)
    if "cartao" in texto or "cartoes" in texto:
        return True
    return bool(tokens.intersection(TOKENS_CARTAO))


def produto_eh_chi(produto: object) -> bool:
    """Retorna True quando o produto representa CHI/conta corrente."""
    texto = normalizar_texto(produto)
    tokens = _tokenizar_produto(produto)
    if tokens.intersection(TOKENS_CHI):
        return True
    return any(frase in texto for frase in FRASES_CHI)


def _produto_tem_contrato(produto: object) -> bool:
    return bool(CONTRATO_PATTERN.search(str(produto or "")))


def produto_deve_ser_ignorado(produto: object) -> bool:
    """
    Ignora produtos sem relação com contrato/cartão/CHI.

    Regra explícita de negócio:
    - "capital de giro" sempre ignorado.
    """
    texto = normalizar_texto(produto)
    if not texto:
        return True
    if "capital de giro" in texto:
        return True
    if _produto_tem_contrato(produto):
        return False
    if produto_eh_cartao(produto) or produto_eh_chi(produto):
        return False
    return True


def _extrair_parcelas_do_sufixo(sufixo: str) -> set[str]:
    """
    Extrai parcelas conectadas imediatamente ao contrato.

    Aceita padrões com `_` e `+`, sem capturar números soltos de outros blocos.
    Exemplo: `_34+35+36` -> {"34", "35", "36"}.
    """
    parcelas: set[str] = set()
    i = 0
    tamanho = len(sufixo)

    while i < tamanho:
        while i < tamanho and sufixo[i].isspace():
            i += 1
        if i >= tamanho or sufixo[i] not in "_+":
            break

        i += 1
        while i < tamanho and sufixo[i].isspace():
            i += 1

        inicio_numero = i
        while i < tamanho and sufixo[i].isdigit():
            i += 1

        if inicio_numero == i:
            break

        parcelas.add(sufixo[inicio_numero:i])

    return parcelas


def extrair_blocos_contrato_parcelas(produto: object) -> list[dict[str, object]]:
    """
    Extrai blocos de contrato com as parcelas associadas a cada contrato.

    Retorno:
    [
      {"contrato": "...", "contrato_norm": "...", "parcelas": {"1", "2"}}
    ]
    """
    texto = str(produto or "")
    matches = list(CONTRATO_PATTERN.finditer(texto))
    blocos: list[dict[str, object]] = []

    for indice, match in enumerate(matches):
        contrato_raw = match.group(1).strip()
        contrato_norm = normalizar_contrato(contrato_raw)
        inicio_sufixo = match.end()
        fim_sufixo = matches[indice + 1].start() if indice + 1 < len(matches) else len(texto)
        sufixo = texto[inicio_sufixo:fim_sufixo]

        blocos.append(
            {
                "contrato": contrato_raw,
                "contrato_norm": contrato_norm,
                "parcelas": _extrair_parcelas_do_sufixo(sufixo),
            }
        )

    return blocos
