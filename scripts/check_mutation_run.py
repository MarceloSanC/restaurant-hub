"""Reprova a corrida de mutação que não mediu (issue #87) ou que deixou mutante vivo novo (#217).

O `mutmut run` sai com 1 quando a coleta de estatísticas quebra, mas há
corridas que saem com 0 e não mediram nada: o `only_mutate` que não casa com
arquivo nenhum (zero mutantes) e a corrida que para no meio (mutantes ainda
`not checked`). O job noturno do `audit-gate.yml` lê o resumo que o
`mutmut export-cicd-stats` grava e cobra as duas coisas.

**Sobrevivente só passa se for equivalente conhecido** (issue #217). Até a
#217 sobrevivente não reprovava (o limiar da issue #45 ficou por decidir), e o
placar dos módulos de acesso era zero: um sobrevivente novo e real em
`authorize_action.py` só apareceria para quem lesse o resumo do job. Com o
adapter Postgres da escala no escopo, dez sobreviventes equivalentes aparecem
em toda corrida, e "zero" deixou de ser o número a olhar. Agora, com
`--sobreviventes` (a saída de `mutmut results`) e `--equivalentes` (a lista em
`scripts/mutation_equivalents.txt`):

- mutante não morto que **não** está na lista reprova (sobrevivente novo);
- item da lista que **não** sobreviveu reprova (lista desatualizada: o código
  mudou e o mutmut renumerou, ou um teste novo o matou — a lista se refaz).

O JSON do mutmut 3.7.0 (`save_cicd_stats`) traz `total` e a contagem de cada
desfecho, mas não `not_checked`; os não testados são o `total` menos a soma dos
desfechos de mutante testado. `check_was_interrupted_by_user` conta como não
testado.

Uso:
    python scripts/check_mutation_run.py [mutants/mutmut-cicd-stats.json]
        [--sobreviventes RESULTS.txt --equivalentes LISTA.txt]

Exit codes:
  0  todo mutante gerado foi testado (e, com a lista, só os equivalentes vivem)
  1  nenhum resumo, nenhum mutante, mutante sem desfecho, sobrevivente fora da
     lista ou item da lista que não sobreviveu
  2  uso errado (só um dos dois argumentos da lista)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PADRAO = Path("mutants/mutmut-cicd-stats.json")

# Desfechos de mutante que chegou a rodar contra a suíte (ou foi decidido sem
# ela, como `no_tests` e `skipped`). Fora daqui fica só o `not checked` e a
# interrupção.
_TESTADOS = (
    "killed",
    "survived",
    "no_tests",
    "skipped",
    "suspicious",
    "timeout",
    "segfault",
)

# Os estados do `mutmut results` (mutmut 3.7.0, `status_by_exit_code`) que
# contam como mutante morto. Todo o resto que o comando lista — `survived`,
# `no tests`, `skipped`, `suspicious` — é mutante que a suíte não derrubou.
# `not checked` e a interrupção já reprovam pelo resumo, acima.
_MORTOS = frozenset({"killed", "timeout", "segfault", "caught by type check"})


def problemas(resumo: dict[str, int]) -> list[str]:
    """O que faz a corrida não ter medido nada, em texto; vazio se mediu tudo."""
    total = resumo["total"]
    if total == 0:
        return ["a corrida não gerou mutante nenhum (only_mutate vazio ou que não casa)"]
    testados = sum(resumo[chave] for chave in _TESTADOS)
    if testados < total:
        return [
            f"{total - testados} de {total} mutantes ficaram sem teste "
            f"(not checked ou interrompidos): a corrida não mediu a suíte"
        ]
    return []


def nao_mortos(saida_do_results: str) -> dict[str, str]:
    """`nome -> estado` de cada mutante que a suíte não derrubou, lido do `mutmut results`.

    Formato do mutmut 3.7.0: uma linha `    <nome>: <estado>` por mutante. O nome
    não tem `": "` (é `modulo.funcao__mutmut_N`); o estado é o que vem depois.
    Linha sem `__mutmut_` no nome (aviso de ferramenta, log) não é mutante.
    """
    vivos: dict[str, str] = {}
    for linha in saida_do_results.splitlines():
        nome, separador, estado = linha.strip().rpartition(": ")
        if separador and "__mutmut_" in nome and estado not in _MORTOS:
            vivos[nome] = estado
    return vivos


def equivalentes(texto: str) -> frozenset[str]:
    """Os nomes da lista: um por linha; `#` abre comentário; linha vazia não conta."""
    nomes = (linha.split("#", 1)[0].strip() for linha in texto.splitlines())
    return frozenset(nome for nome in nomes if nome)


def problemas_de_sobreviventes(vivos: dict[str, str], conhecidos: frozenset[str]) -> list[str]:
    """Sobrevivente fora da lista e item da lista que não sobreviveu, em texto."""
    achados = [
        f"mutante não morto fora da lista de equivalentes: {nome} ({estado})"
        for nome, estado in sorted(vivos.items())
        if nome not in conhecidos
    ]
    achados += [
        f"equivalente da lista que não sobreviveu (lista desatualizada): {nome}"
        for nome in sorted(conhecidos - vivos.keys())
    ]
    return achados


def _ler(caminho: Path) -> str | None:
    return caminho.read_text(encoding="utf-8") if caminho.is_file() else None


def main(argv: list[str]) -> int:
    posicionais: list[str] = []
    opcoes: dict[str, str] = {}
    argumentos = iter(argv)
    for argumento in argumentos:
        if argumento in {"--sobreviventes", "--equivalentes"}:
            opcoes[argumento] = next(argumentos, "")
        else:
            posicionais.append(argumento)
    if len(opcoes) == 1 or "" in opcoes.values() or len(posicionais) > 1:
        print(
            "ERRO: uso — [resumo.json] [--sobreviventes RESULTS --equivalentes LISTA]",
            file=sys.stderr,
        )
        return 2

    caminho = Path(posicionais[0]) if posicionais else _PADRAO
    if not caminho.is_file():
        print(
            f"ERRO: {caminho} não existe — o mutmut não registrou resultado de "
            f"mutante nenhum (a coleta quebrou antes da corrida?)",
            file=sys.stderr,
        )
        return 1
    resumo = json.loads(caminho.read_text(encoding="utf-8"))
    achados = problemas(resumo)

    if opcoes:
        saida = _ler(Path(opcoes["--sobreviventes"]))
        lista = _ler(Path(opcoes["--equivalentes"]))
        if saida is None or lista is None:
            achados.append("a saída do `mutmut results` ou a lista de equivalentes não existe")
        else:
            achados += problemas_de_sobreviventes(nao_mortos(saida), equivalentes(lista))

    for achado in achados:
        print(f"ERRO: {achado}", file=sys.stderr)
    if achados:
        return 1
    print(f"OK: {resumo['total']} mutantes testados ({resumo['survived']} sobreviventes).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
