# Sudoeste Processado V2

## Visão geral
Este fluxo é novo e **independente** dos fluxos antigos (`sudoeste`, `sudoeste-direto`, `sudoeste-indireto`, `sudoeste-consolidado`).

Objetivo:
- usar `sudoeste_inicial_processado.xlsx` como fonte da verdade;
- manter todas as colunas originais da planilha inicial;
- filtrar linhas em duas saídas separadas:
  - um excel com match no Direto;
  - um excel com match no Indireto.

## Como a regra funciona
1. Cada linha do inicial é avaliada individualmente.
2. Testamos match com Direto e com Indireto de forma independente.
3. A linha pode entrar no arquivo de Direto, no de Indireto ou em ambos.
4. O retorno da API é um `.zip` com dois arquivos `.xlsx`.
5. Não existe consolidação por CPF.

## Tipos de título do inicial
- `contrato`: títulos iniciando com contrato (`C...`).
- `cartao`: títulos `MAS` ou `CAR`.
- `chi`: título `CHI`.
- `ignorar`: qualquer outro caso.

## Match por tipo
- Contrato: mesmo CPF + mesmo contrato + parcela vinculada ao contrato no produto.
- Cartão: mesmo CPF + produto indicando cartão (`cartao`, `cartão`, `mas`, `car`).
- CHI: mesmo CPF + produto indicando `chi`, `inadimplencia`, `cheque especial` ou `conta corrente`.

## Parser de produto
O parser identifica blocos por contrato para não misturar parcelas entre contratos.

Exemplo:
`C138304510_34+35+36+37 + C438310906_2+3+4+5+6 + Conta corrente`

Resultado:
- `C138304510` -> parcelas `34,35,36,37`
- `C438310906` -> parcelas `2,3,4,5,6`

## Produtos ignorados
- `capital de giro` é sempre ignorado.
- também ignoramos textos sem contrato e sem indicação de cartão/CHI.
