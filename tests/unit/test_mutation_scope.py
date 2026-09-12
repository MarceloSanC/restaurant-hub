"""O escopo do teste de mutação (M2 da issue #45) aponta para arquivos que existem.

**Por que existe: um caminho morto no `only_mutate` exclui o módulo em silêncio.**
O mutmut filtra os arquivos de `source_paths` por `fnmatch` contra cada padrão de
`only_mutate`. Um padrão que não casa com arquivo nenhum não produz erro, não
produz aviso — produz uma corrida com um módulo a menos, e um relatório que
continua dizendo "N mutantes, N mortos" sobre um universo menor que o declarado.

Foi exatamente o que aconteceu no rename `adapters/in/` → `adapters/inbound/`:
o `pyproject.toml` ficou com `adapters/in/http/dependencies.py`, e a corrida
seguinte mediu **três** dos quatro módulos que decidem acesso, reportando zero
sobreviventes sobre a borda que extrai o Bearer sem tê-la mutado uma vez sequer.
Achado por revisão, não por sintoma — que é o modo de falha que este arquivo
existe para tornar barulhento.

**Lista explícita + asserção de que ela cobre a configuração**, o par de sempre.
A lista aqui é a dos quatro módulos que a issue nomeia; a asserção seguinte cobra
o `pyproject.toml` contra ela nos dois sentidos, para que nem um módulo saia do
escopo por edição distraída, nem um quinto entre sem que a issue que o justifica
seja escrita neste arquivo.
"""

import pathlib
import tomllib

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# Os quatro módulos que decidem acesso, como a issue #45 os nomeia. Um quinto
# entra aqui com a justificativa ao lado — e só então no `pyproject.toml`.
_MODULOS_DE_ACESSO = frozenset(
    {
        # Os quatro passos do guard (ADR 2.2.0002).
        "src/restaurant_hub/features/identity/application/use_cases/authorize_action.py",
        # A visibilidade de unidade — o eixo B do acesso.
        "src/restaurant_hub/features/identity/domain/entities/user.py",
        # Só pelo `_IdentityAccessGuard`, que impõe L-AG3 num `raise` (sai na #47).
        "src/restaurant_hub/composition_root.py",
        # A borda que extrai o Bearer e delega ao use case.
        "src/restaurant_hub/features/identity/adapters/inbound/http/dependencies.py",
    }
)


def _config_do_mutmut() -> dict[str, object]:
    with _PYPROJECT.open("rb") as arquivo:
        return dict(tomllib.load(arquivo)["tool"]["mutmut"])


def test_todo_caminho_do_only_mutate_existe() -> None:
    """A asserção que faltava no dia do rename.

    `fnmatch` sobre caminho inexistente não reprova nada — apenas deixa o módulo
    de fora. Aqui a existência é cobrada antes de a corrida ser lançada.
    """
    caminhos = _config_do_mutmut()["only_mutate"]
    assert isinstance(caminhos, list)
    ausentes = sorted(caminho for caminho in caminhos if not (_REPO_ROOT / caminho).is_file())

    assert ausentes == [], (
        f"only_mutate aponta para arquivo que não existe: {ausentes}. O mutmut "
        f"não reprova — ele exclui o módulo em silêncio e reporta a corrida "
        f"como completa."
    )


def test_o_escopo_do_mutmut_e_exatamente_os_modulos_de_acesso() -> None:
    """Nos dois sentidos: nada sai sem ser notado, nada entra sem justificativa.

    Um módulo a menos é o rename repetido; um módulo a mais é o escopo
    crescendo sem a issue que o justifica — e a corrida noturna ficando mais
    lenta sem que ninguém tenha decidido isso.
    """
    caminhos = _config_do_mutmut()["only_mutate"]
    assert isinstance(caminhos, list)

    assert set(caminhos) == _MODULOS_DE_ACESSO, (
        f"só no pyproject: {sorted(set(caminhos) - _MODULOS_DE_ACESSO)}; "
        f"só nesta lista: {sorted(_MODULOS_DE_ACESSO - set(caminhos))}"
    )


def test_todo_caminho_do_also_copy_existe() -> None:
    """O mesmo defeito, do outro lado: `also_copy` para caminho ausente.

    Um `also_copy` morto não derruba a corrida — e o arquivo que ele deveria
    levar para o sandbox simplesmente não vai, o que reaparece como
    `FileNotFoundError` dentro de um teste, longe da causa. Medido na primeira
    corrida desta configuração, antes de `docs/` entrar na lista.
    """
    caminhos = _config_do_mutmut()["also_copy"]
    assert isinstance(caminhos, list)
    ausentes = sorted(caminho for caminho in caminhos if not (_REPO_ROOT / caminho).exists())

    assert ausentes == [], f"also_copy aponta para caminho que não existe: {ausentes}"


def test_o_gate_estrutural_do_check_layout_fica_fora_da_corrida() -> None:
    """A exclusão de `test_check_layout.py` é deliberada e continua declarada.

    Dentro de `mutants/` o `composition_root.py` tem centenas de funções geradas
    pela ferramenta, e o Gate 1 reprova sobre um arquivo que o mutmut escreveu.
    Se alguém tirar o `--ignore` por achar que é sobra, a corrida volta a morrer
    na coleta de estatísticas — e este teste diz o porquê antes disso.
    """
    selecao = _config_do_mutmut()["pytest_add_cli_args_test_selection"]
    assert isinstance(selecao, list)

    assert "--ignore=tests/unit/test_check_layout.py" in selecao
