"""Nenhum repositório Postgres de identity abre transação por conta própria (Stage 2.6, CA3).

A atomicidade da unidade de trabalho depende de **todo** método de repositório
pedir a conexão a `conexao_da_unidade`. Um método esquecido com
`self._engine.begin()` não quebra teste nenhum fora de unidade — e, dentro dela,
falha em silêncio de três jeitos: a escrita comita sozinha; a leitura não vê as
escritas da unidade; e um `UPDATE` numa linha que a unidade já travou espera numa
**segunda** conexão do pool, uma trava que o Postgres não enxerga como deadlock.

Por isso a checagem é sobre o texto, e total: todo `*_repository.py` do pacote.
"""

import ast
import pathlib

import pytest

import restaurant_hub.features.identity.adapters.out.postgres as pacote_postgres

_PASTA = pathlib.Path(pacote_postgres.__file__).parent
_REPOSITORIOS = sorted(_PASTA.glob("*_repository.py"))


def _chamadas_diretas_ao_engine(arquivo: pathlib.Path) -> list[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    achadas: list[str] = []
    for no in ast.walk(arvore):
        if (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr in {"begin", "connect"}
            and isinstance(no.func.value, ast.Attribute)
            and no.func.value.attr == "_engine"
        ):
            achadas.append(f"{arquivo.name}:{no.lineno} _engine.{no.func.attr}()")
    return achadas


def test_os_cinco_repositorios_estao_na_varredura() -> None:
    assert [r.name for r in _REPOSITORIOS] == [
        "password_setup_token_repository.py",
        "restaurant_repository.py",
        "session_repository.py",
        "unit_repository.py",
        "user_repository.py",
    ]


@pytest.mark.parametrize("arquivo", _REPOSITORIOS, ids=lambda a: a.name)
def test_repositorio_nao_abre_transacao_propria(arquivo: pathlib.Path) -> None:
    assert _chamadas_diretas_ao_engine(arquivo) == []


def test_o_detector_acha_a_chamada_direta(tmp_path: pathlib.Path) -> None:
    """Sem isto, um detector quebrado passaria todos os repositórios em silêncio."""
    falso = tmp_path / "x_repository.py"
    falso.write_text(
        "class R:\n"
        "    def add(self):\n"
        "        with self._engine.begin() as c:\n"
        "            pass\n"
        "    def find(self):\n"
        "        with self._engine.connect() as c:\n"
        "            pass\n",
        encoding="utf-8",
    )
    assert _chamadas_diretas_ao_engine(falso) == [
        "x_repository.py:3 _engine.begin()",
        "x_repository.py:6 _engine.connect()",
    ]
