"""Reprova a corrida de mutação que terminou sem testar os mutantes (issue #87).

O `mutmut run` sai com 1 quando a coleta de estatísticas quebra, mas há
corridas que saem com 0 e não mediram nada: o `only_mutate` que não casa com
arquivo nenhum (zero mutantes) e a corrida que para no meio (mutantes ainda
`not checked`). O job noturno do `audit-gate.yml` lê o resumo que o
`mutmut export-cicd-stats` grava e cobra as duas coisas.

Sobrevivente **não** reprova aqui: o limiar de sobreviventes é decisão
separada (issue #45). O que reprova é a corrida que não mediu.

O JSON do mutmut 3.7.0 (`save_cicd_stats`) traz `total` e a contagem de cada
desfecho, mas não `not_checked`; os não testados são o `total` menos a soma dos
desfechos de mutante testado. `check_was_interrupted_by_user` conta como não
testado.

Uso:
    python scripts/check_mutation_run.py [mutants/mutmut-cicd-stats.json]

Exit codes:
  0  todo mutante gerado foi testado
  1  nenhum resumo, nenhum mutante, ou mutante sem desfecho
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


def main(argv: list[str]) -> int:
    caminho = Path(argv[0]) if argv else _PADRAO
    if not caminho.is_file():
        print(
            f"ERRO: {caminho} não existe — o mutmut não registrou resultado de "
            f"mutante nenhum (a coleta quebrou antes da corrida?)",
            file=sys.stderr,
        )
        return 1
    resumo = json.loads(caminho.read_text(encoding="utf-8"))
    achados = problemas(resumo)
    for achado in achados:
        print(f"ERRO: {achado}", file=sys.stderr)
    if achados:
        return 1
    print(f"OK: {resumo['total']} mutantes testados ({resumo['survived']} sobreviventes).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
