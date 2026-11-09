"""Reprova a corrida de mutação cujos workers disputaram o mesmo Postgres (issue #132).

O mutmut 3.7.0 testa os mutantes em processos paralelos, e cada um roda uma
sessão nova de pytest — com a fixture `engine` recriando o schema. Com um banco
só para todos, um worker derrubava as tabelas que outro usava, e o mutante
"morto" assim morria pela corrida entre workers, não pela asserção do teste. O
run 41475839122 terminou `581/581 mortos` com 11 `deadlock detected` e 49
`relation ... does not exist` no log do Postgres: a contagem não media a suíte.

A fixture `database_url` de `tests/conftest.py` dá a cada worker um banco
próprio. Este script lê o log do Postgres durante o `mutmut run` e cobra que a
disputa não voltou — as duas assinaturas que ela deixava. Violação de chave ou
de FK **não** entra: a suíte provoca essas de propósito (o adapter traduz o
erro de constraint), e elas aparecem no log de qualquer corrida limpa.

Uso:
    python scripts/check_mutation_db_isolation.py <log do Postgres>

Exit codes:
  0  nenhuma assinatura de disputa no log
  1  log ausente, ou deadlock / tabela sumida durante a corrida
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# As duas assinaturas da disputa, como o Postgres 16 as escreve no log. A
# tabela sumida é a de outro worker recriando o schema no meio do teste; o
# deadlock, dois `TRUNCATE`/`DROP` cruzando locks.
SIGNATURES = {
    "deadlock detected": re.compile(r"deadlock detected"),
    'relation "..." does not exist': re.compile(r'relation "[^"]+" does not exist'),
}


def contention(log: str) -> dict[str, int]:
    """Quantas linhas do log carregam cada assinatura de disputa."""
    lines = log.splitlines()
    return {
        name: sum(1 for line in lines if pattern.search(line))
        for name, pattern in SIGNATURES.items()
    }


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("uso: check_mutation_db_isolation.py <log do Postgres>", file=sys.stderr)
        return 1
    path = Path(argv[0])
    if not path.is_file():
        print(f"ERRO: {path} não existe — o log do Postgres não foi coletado", file=sys.stderr)
        return 1
    log = path.read_text(encoding="utf-8", errors="replace")
    print(f"linhas do log lidas: {len(log.splitlines())}")
    counts = contention(log)
    for name, count in counts.items():
        print(f"{name}: {count}")
    if any(counts.values()):
        print(
            "ERRO: workers do mutmut disputaram o Postgres — mutante morto por "
            "concorrência não mede a suíte (issue #132)",
            file=sys.stderr,
        )
        return 1
    print("OK: nenhuma disputa de Postgres entre os workers do mutmut.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
