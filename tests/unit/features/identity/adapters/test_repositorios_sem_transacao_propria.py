"""Nenhum repositório Postgres de identity abre transação por conta própria (Stage 2.6, CA3).

A atomicidade da unidade de trabalho depende de **todo** método de repositório
pedir a conexão a `conexao_da_unidade`. Um método esquecido com
`self._engine.begin()` não quebra teste nenhum fora de unidade — e, dentro dela,
falha em silêncio de três jeitos: a escrita comita sozinha; a leitura não vê as
escritas da unidade; e um `UPDATE` numa linha que a unidade já travou espera numa
**segunda** conexão do pool, uma trava que o Postgres não enxerga como deadlock.

A checagem é **positiva**, não uma lista de padrões proibidos: todo uso do engine
num `*_repository.py` tem de ser o argumento de `para_escrita`/`para_leitura` ou a
atribuição `self._engine = engine` do construtor. Qualquer outra forma — alias
local, método ligado guardado numa variável, `raw_connection()`, o engine guardado
sob outro nome — reprova, porque cada uma é uma saída silenciosa da unidade.
"""

import ast
import pathlib

import pytest

import restaurant_hub.features.identity.adapters.out.postgres as pacote_postgres

_PASTA = pathlib.Path(pacote_postgres.__file__).parent
_REPOSITORIOS = sorted(_PASTA.glob("*_repository.py"))
_HELPERS = {"para_escrita", "para_leitura"}


def _usos_indevidos_do_engine(arquivo: pathlib.Path) -> list[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    permitidos: set[int] = set()
    achados: list[str] = []

    for no in ast.walk(arvore):
        if (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Name)
            and no.func.id in _HELPERS
            and len(no.args) == 1
            and isinstance(no.args[0], ast.Attribute)
            and no.args[0].attr == "_engine"
        ):
            permitidos.add(id(no.args[0]))
        if isinstance(no, ast.Assign) and len(no.targets) == 1:
            alvo = no.targets[0]
            vem_do_engine = isinstance(no.value, ast.Name) and no.value.id == "engine"
            if isinstance(alvo, ast.Attribute) and alvo.attr == "_engine" and vem_do_engine:
                permitidos.add(id(alvo))
            elif vem_do_engine:
                achados.append(f"{arquivo.name}:{no.lineno} engine guardado fora de `_engine`")

    for no in ast.walk(arvore):
        if isinstance(no, ast.Attribute) and no.attr == "_engine" and id(no) not in permitidos:
            achados.append(
                f"{arquivo.name}:{no.lineno} `_engine` fora de para_escrita/para_leitura"
            )
        if (
            isinstance(no, ast.Attribute)
            and isinstance(no.value, ast.Name)
            and no.value.id == "engine"
        ):
            achados.append(f"{arquivo.name}:{no.lineno} `engine.{no.attr}` direto")
    return sorted(achados)


def test_os_cinco_repositorios_estao_na_varredura() -> None:
    assert [r.name for r in _REPOSITORIOS] == [
        "password_setup_token_repository.py",
        "restaurant_repository.py",
        "session_repository.py",
        "unit_repository.py",
        "user_repository.py",
    ]


@pytest.mark.parametrize("arquivo", _REPOSITORIOS, ids=lambda a: a.name)
def test_repositorio_so_usa_o_engine_pelos_helpers(arquivo: pathlib.Path) -> None:
    assert _usos_indevidos_do_engine(arquivo) == []


_AMOSTRAS_INDEVIDAS = {
    "chamada_direta": "with self._engine.begin() as c:\n            pass",
    "alias_local": "e = self._engine\n        with e.connect() as c:\n            pass",
    "metodo_ligado": "abrir = self._engine.begin\n        with abrir() as c:\n            pass",
    "raw_connection": "self._engine.raw_connection()",
}


@pytest.mark.parametrize("amostra", sorted(_AMOSTRAS_INDEVIDAS))
def test_o_detector_reprova_cada_forma_de_escapar(tmp_path: pathlib.Path, amostra: str) -> None:
    """Sem isto, um detector quebrado aprovaria os repositórios em silêncio."""
    falso = tmp_path / "x_repository.py"
    falso.write_text(
        "class R:\n"
        "    def __init__(self, engine):\n"
        "        self._engine = engine\n"
        "    def add(self):\n"
        f"        {_AMOSTRAS_INDEVIDAS[amostra]}\n",
        encoding="utf-8",
    )
    assert _usos_indevidos_do_engine(falso) != []


def test_o_detector_reprova_engine_guardado_sob_outro_nome(tmp_path: pathlib.Path) -> None:
    falso = tmp_path / "x_repository.py"
    falso.write_text(
        "class R:\n    def __init__(self, engine):\n        self._motor = engine\n",
        encoding="utf-8",
    )
    assert _usos_indevidos_do_engine(falso) == [
        "x_repository.py:3 engine guardado fora de `_engine`"
    ]


def test_o_detector_aprova_o_uso_pelos_helpers(tmp_path: pathlib.Path) -> None:
    falso = tmp_path / "x_repository.py"
    falso.write_text(
        "class R:\n"
        "    def __init__(self, engine):\n"
        "        self._engine = engine\n"
        "    def add(self):\n"
        "        with para_escrita(self._engine) as c:\n"
        "            pass\n"
        "    def find(self):\n"
        "        with para_leitura(self._engine) as c:\n"
        "            pass\n",
        encoding="utf-8",
    )
    assert _usos_indevidos_do_engine(falso) == []
