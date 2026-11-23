"""A extração da emissão do token não abre ponto cego na regra 10 (issue #205).

A regra 10 do `scripts/check_layout.py` (ADR 2.6.0002 §5) conta escrita por
atributo de repositório **do use case** — `self._tokens.add(...)`, no corpo dele ou
nos seus métodos privados. Quando este guarda nasceu, ela não seguia um repositório
entregue a uma função de módulo (ponto cego declarado do ADR): uma extração que
recebesse o repositório e gravasse por dentro esconderia da regra a escrita do token
nos cinco use cases que emitem — e então tirar a unidade de trabalho de volta de
`users.add` + `tokens.add` deixaria a suíte verde e a atomicidade perdida. Desde a
issue #243 a regra segue o repositório **anotado no parâmetro** de uma função de
módulo (`helper_writes`), mas não os embrulhos do limite abaixo; e o ADR 0.0.0024
continua pedindo que o helper não grave, que é o que o lado 1 cobra.

Dois lados, cada um com o seu controle:

1. **O helper não grava.** Nenhuma função do módulo `_invitation.py` recebe um
   repositório (`ports/out/*_repository.py`). O detector é provado contra um módulo
   plantado que recebe um, e reprova.
2. **Os cinco use cases reais continuam contados.** Numa cópia de `src/` em
   `tmp_path`, a unidade de cada um é desfeita (`with ...transaction():` vira
   `if True:`) — e a regra 10 reprova cada um, nomeando `self._tokens.add`. Se a
   escrita do token tivesse saído do alcance da regra, a cópia sem unidade passaria.

**Limite do lado 1** (auditoria da #205): o detector lê nomes na anotação. Não vê
um repositório que chegue embrulhado — anotado como `Any`, como `Callable[...]`
(o `self._tokens.add` passado como função), dentro de um objeto de contexto ou por
closure. Para os cinco emissores de hoje o lado 2 fecha o buraco por propriedade, e
não por forma: qualquer embrulho tira o `self._tokens.add` do corpo do use case, e
a cópia sem unidade deixa de reprovar (medido na auditoria com o método ligado a
um nome local). Um emissor novo só fica coberto se entrar em `_EMISSORES`.
"""

import ast
import importlib.util
import pathlib
import shutil
import types

import pytest

# `_anotacao` da regra 10 lê só `Name`, `Attribute` e string; o detector deste
# arquivo lê todos os nomes da anotação, então não depende dele.

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
_SRC = _REPO_ROOT / "src" / "restaurant_hub"
_USE_CASES = pathlib.Path("features/identity/application/use_cases")
_HELPER = _SRC / _USE_CASES / "_invitation.py"
_UNIDADE = "with self._unit_of_work.transaction():"


def _carregar_check_layout() -> types.ModuleType:
    """Importa `scripts/check_layout.py` sem mexer no `sys.path` (como `test_check_layout`)."""
    spec = importlib.util.spec_from_file_location(
        "check_layout_issue_205", _REPO_ROOT / "scripts" / "check_layout.py"
    )
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


check_layout = _carregar_check_layout()


def _nomes_na_anotacao(anotacao: ast.expr | None) -> set[str]:
    """Todo nome que aparece na anotação — `X`, `mod.X`, `"X"`, `X | None`, `Optional[X]`."""
    if anotacao is None:
        return set()
    nomes: set[str] = set()
    for no in ast.walk(anotacao):
        if isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes.add(no.attr)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            nomes |= _nomes_na_anotacao(ast.parse(no.value, mode="eval").body)
    return nomes


def _recebem_repositorio(modulo: pathlib.Path, ports: set[str]) -> list[str]:
    """`função(parâmetro: ...<Port>Repository...)` em qualquer função ou método do módulo.

    Lê **todo** parâmetro (`*args` e `**kwargs` inclusive) e todo nome dentro da
    anotação, para que `X | None`, `Optional[X]` ou `"X"` não escapem.
    """
    arvore = ast.parse(modulo.read_text(encoding="utf-8"))
    achados: list[str] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        a = no.args
        parametros = [*a.posonlyargs, *a.args, *a.kwonlyargs, *filter(None, (a.vararg, a.kwarg))]
        for arg in parametros:
            for tipo in sorted(_nomes_na_anotacao(arg.annotation) & ports):
                achados.append(f"{no.name}({arg.arg}: {tipo})")
    return achados


# --- 1. o helper não grava ---------------------------------------------------


def test_nenhuma_funcao_do_helper_de_emissao_recebe_repositorio() -> None:
    ports = check_layout.repository_port_names(_SRC)
    assert "PasswordSetupTokenRepository" in ports  # o detector olha os ports reais

    assert _recebem_repositorio(_HELPER, ports) == []


def test_o_detector_reprova_um_helper_que_recebe_o_repositorio(tmp_path: pathlib.Path) -> None:
    """O violador plantado: a forma que a regra 10 não enxergaria."""
    plantado = tmp_path / "_invitation.py"
    plantado.write_text(
        "def issue_setup_token(\n"
        "    tokens: PasswordSetupTokenRepository, *, base_url: str\n"
        ") -> str:\n"
        "    tokens.add(object())\n"
        "    return base_url\n",
        encoding="utf-8",
    )

    achados = _recebem_repositorio(plantado, {"PasswordSetupTokenRepository"})

    assert achados == ["issue_setup_token(tokens: PasswordSetupTokenRepository)"]


@pytest.mark.parametrize(
    "assinatura",
    [
        "tokens: PasswordSetupTokenRepository | None",
        "tokens: Optional[PasswordSetupTokenRepository]",
        "tokens: 'PasswordSetupTokenRepository'",
        "tokens: ports.PasswordSetupTokenRepository",
        "*tokens: PasswordSetupTokenRepository",
        "**tokens: PasswordSetupTokenRepository",
    ],
)
def test_o_detector_reprova_as_formas_disfarcadas_do_repositorio(
    tmp_path: pathlib.Path, assinatura: str
) -> None:
    plantado = tmp_path / "_invitation.py"
    plantado.write_text(f"def emitir({assinatura}) -> None:\n    pass\n", encoding="utf-8")

    achados = _recebem_repositorio(plantado, {"PasswordSetupTokenRepository"})

    assert achados == ["emitir(tokens: PasswordSetupTokenRepository)"]


# --- 2. os cinco use cases reais continuam contados ----------------------------

_EMISSORES = {
    "invite_user.py": "InviteUserUseCase",
    "invite_owner.py": "InviteOwnerUseCase",
    "provision_restaurant.py": "ProvisionRestaurantUseCase",
    "provision_account.py": "ProvisionAccountUseCase",
    "request_password_reset.py": "RequestPasswordResetUseCase",
}


def test_os_cinco_emissores_reais_cumprem_a_regra_10() -> None:
    achados = check_layout.scan_multi_write_use_cases(_SRC)

    assert set(_EMISSORES.values()) & set(achados) == set()


@pytest.mark.parametrize("arquivo", sorted(_EMISSORES))
def test_sem_a_unidade_a_regra_10_reprova_a_escrita_do_token(
    tmp_path: pathlib.Path, arquivo: str
) -> None:
    copia = tmp_path / "src" / "restaurant_hub"
    shutil.copytree(_SRC, copia, ignore=shutil.ignore_patterns("__pycache__"))
    alvo = copia / _USE_CASES / arquivo
    fonte = alvo.read_text(encoding="utf-8")
    assert fonte.count(_UNIDADE) == 1, "o emissor abre exatamente uma unidade"
    alvo.write_text(fonte.replace(_UNIDADE, "if True:"), encoding="utf-8")

    achados = check_layout.scan_multi_write_use_cases(copia)

    classe = _EMISSORES[arquivo]
    assert classe in achados, achados
    _, _, motivo = achados[classe]
    assert "self._tokens.add" in motivo
