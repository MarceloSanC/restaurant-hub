"""A extração da emissão do token não abre ponto cego na regra 10 (issue #205).

A regra 10 do `scripts/check_layout.py` (ADR 2.6.0002 §5) conta escrita por
atributo de repositório **do use case** — `self._tokens.add(...)`, no corpo dele ou
nos seus métodos privados. Ela não segue um repositório entregue a uma função de
módulo: é ponto cego declarado do ADR. Uma extração que recebesse o repositório e
gravasse por dentro esconderia da regra a escrita do token nos cinco use cases que
emitem — e então tirar a unidade de trabalho de volta de `users.add` + `tokens.add`
deixaria a suíte verde e a atomicidade perdida.

Dois lados, cada um com o seu controle:

1. **O helper não grava.** Nenhuma função do módulo `_invitation.py` recebe um
   repositório (`ports/out/*_repository.py`). O detector é provado contra um módulo
   plantado que recebe um, e reprova.
2. **Os cinco use cases reais continuam contados.** Numa cópia de `src/` em
   `tmp_path`, a unidade de cada um é desfeita (`with ...transaction():` vira
   `if True:`) — e a regra 10 reprova cada um, nomeando `self._tokens.add`. Se a
   escrita do token tivesse saído do alcance da regra, a cópia sem unidade passaria.
"""

import ast
import importlib.util
import pathlib
import shutil
import types

import pytest

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


def _recebem_repositorio(modulo: pathlib.Path, ports: set[str]) -> list[str]:
    """`função(parâmetro: <Port>Repository)` em qualquer função ou método do módulo."""
    arvore = ast.parse(modulo.read_text(encoding="utf-8"))
    achados: list[str] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        argumentos = no.args
        for arg in [*argumentos.posonlyargs, *argumentos.args, *argumentos.kwonlyargs]:
            # O mesmo leitor de anotação que a regra 10 usa no construtor.
            tipo = check_layout._anotacao(arg.annotation)
            if tipo in ports:
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
