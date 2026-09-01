"""O detector de claim falsa na árvore do `LAYOUT.md` §2, contra violadores plantados.

Gate 5 da issue #45.

**O que este gate protege é uma instrução, não um documento.** `CLAUDE.md` manda
conferir o LAYOUT §2 antes de criar qualquer arquivo novo, e a §2 é um desenho de
árvore. Uma linha falsa ali é uma instrução errada dada a quem for criar o
próximo arquivo — e nenhuma ferramenta a corrige, porque nada no repositório
compara documento com sistema de arquivos.

`application/ports/in/` foi o caso: seis Stages de árvore afirmando um diretório
que nunca existiu, mais duas seções inteiras (§5 e §8) escritas para explicar
como contornar a keyword `in` num pacote que ninguém tinha. Ele saiu do
documento na #45 (ADR 0.0.0006), e este gate é o que impede a terceira promessa.

**Os violadores são plantados num `LAYOUT.md` de mentira**, montado em
`tmp_path` com uma árvore mínima — o script recebe `repo_root`, então dá para
exercitar o parser, a expansão de `<feature>` e as duas direções da anotação sem
tocar no documento real.
"""

import importlib.util
import pathlib
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_docs_claims.py"


def _carregar_script() -> types.ModuleType:
    """Importa `scripts/check_docs_claims.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_docs_claims", _SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


check_docs_claims = _carregar_script()


def _repo_falso(
    tmp_path: pathlib.Path, arvore: str, caminhos: tuple[str, ...] = ()
) -> pathlib.Path:
    """Monta um repositório de mentira: um `LAYOUT.md` com §2 e as pastas dele.

    A árvore chega como texto porque é assim que o script a lê — passar uma
    estrutura já parseada testaria o comparador e deixaria o parser, que é a
    metade frágil, sem cobertura.
    """
    layout = tmp_path / "docs" / "LAYOUT.md"
    layout.parent.mkdir(parents=True, exist_ok=True)
    layout.write_text(
        f"# LAYOUT\n\n{check_docs_claims.SECAO}\n\n```\n{arvore}\n```\n\n## 3. Outra\n",
        encoding="utf-8",
    )
    for caminho in caminhos:
        destino = tmp_path / caminho
        if destino.suffix:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text("", encoding="utf-8")
        else:
            destino.mkdir(parents=True, exist_ok=True)
    return tmp_path


# A árvore mínima que exercita tudo o que importa: dois níveis, um placeholder de
# feature e um arquivo com placeholder de entidade.
_ARVORE = """src/restaurant_hub/
├── main.py                         # Entrypoint ASGI
└── features/                       # Um diretório por bounded context
    └── <feature>/                  # Placeholder
        ├── domain/                 # Núcleo
        └── adapters/               # Implementações
            └── inbound/            # Adapters primários"""


def test_gate5_a_arvore_real_do_layout_confere_com_o_repositorio() -> None:
    """O critério de pronto, medido contra o `LAYOUT.md` real.

    Antes desta issue, `application/ports/in/` reprovava aqui — e
    `domain/services/` também, que é o caminho anotado `[planejado]` hoje.
    """
    problemas = check_docs_claims.claims_falsas(_REPO_ROOT)

    assert problemas == [], "\n".join(problemas)


def test_gate5_um_caminho_desenhado_que_nao_existe_reprova(tmp_path: pathlib.Path) -> None:
    """Violador plantado: a promessa de `ports/in/`, reconstruída.

    `features/identity/adapters/inbound` existe; `features/identity/domain` não. A
    árvore afirma os dois, e só o segundo deve reprovar — é o que distingue o
    detector de uma função que devolve tudo.
    """
    repo = _repo_falso(
        tmp_path,
        _ARVORE,
        caminhos=(
            "src/restaurant_hub/main.py",
            "src/restaurant_hub/features/identity/adapters/inbound",
        ),
    )

    problemas = check_docs_claims.claims_falsas(repo)

    assert len(problemas) == 1, problemas
    assert "features/<feature>/domain" in problemas[0]


def test_gate5_uma_feature_basta_para_o_caminho_com_placeholder(tmp_path: pathlib.Path) -> None:
    """A claim de `<feature>` é existencial, e a distinção é deliberada.

    A §2 desenha UMA feature genérica; ela não afirma que todo bounded context
    tem toda pasta. `staff` legitimamente não teve `adapters/inbound/` até a Stage
    3.6, e cobrar a existência em todas as features faria o gate exigir pastas
    vazias — o oposto do que ele existe para produzir.
    """
    repo = _repo_falso(
        tmp_path,
        _ARVORE,
        caminhos=(
            "src/restaurant_hub/main.py",
            "src/restaurant_hub/features/identity/domain",
            "src/restaurant_hub/features/identity/adapters/inbound",
            "src/restaurant_hub/features/staff/domain",
        ),
    )

    assert check_docs_claims.claims_falsas(repo) == []


def test_gate5_a_anotacao_de_planejado_absolve_o_caminho_ausente(tmp_path: pathlib.Path) -> None:
    """A válvula: promessa declarada como futura é legítima.

    É o que mantém `domain/services/` no documento — slot hexagonal real, sem
    ocupante ainda — sem que o gate obrigue a criar uma pasta vazia para
    silenciá-lo.
    """
    arvore = _ARVORE.replace(
        "        ├── domain/                 # Núcleo",
        "        ├── domain/                 # Núcleo [planejado]",
    )
    repo = _repo_falso(
        tmp_path,
        arvore,
        caminhos=(
            "src/restaurant_hub/main.py",
            "src/restaurant_hub/features/identity/adapters/inbound",
        ),
    )

    assert check_docs_claims.claims_falsas(repo) == []


def test_gate5_a_anotacao_de_planejado_sobre_caminho_existente_reprova(
    tmp_path: pathlib.Path,
) -> None:
    """A outra direção da válvula — a metade que costuma faltar.

    Anotação que ninguém remove deixa de significar alguma coisa: em pouco tempo
    metade da árvore está marcada como futura, e o gate passa a aprovar
    qualquer coisa. Por isso `[planejado]` sobre caminho que já existe também
    reprova, e é este teste que obriga a anotação de `domain/services/` a sair
    no mesmo commit que criar o primeiro serviço de domínio.
    """
    arvore = _ARVORE.replace(
        "        ├── domain/                 # Núcleo",
        "        ├── domain/                 # Núcleo [planejado]",
    )
    repo = _repo_falso(
        tmp_path,
        arvore,
        caminhos=(
            "src/restaurant_hub/main.py",
            "src/restaurant_hub/features/identity/domain",
            "src/restaurant_hub/features/identity/adapters/inbound",
        ),
    )

    problemas = check_docs_claims.claims_falsas(repo)

    assert len(problemas) == 1, problemas
    assert "ANOTAÇÃO MORTA" in problemas[0]


def test_gate5_o_placeholder_de_entidade_vira_glob(tmp_path: pathlib.Path) -> None:
    """`in_memory_<entity>_repository.py` é padrão de nome, não arquivo.

    Tratá-lo como literal reprovaria uma linha correta da árvore de `tests/`, e a
    saída seria apagar a linha — perdendo a convenção de nome que ela documenta.
    """
    arvore = (
        "tests/\n"
        "└── fakes/\n"
        "    └── features/<feature>/\n"
        "        └── in_memory_<entity>_repository.py"
    )
    repo = _repo_falso(
        tmp_path,
        arvore,
        caminhos=(
            "src/restaurant_hub/features/identity/x",
            "tests/fakes/features/identity/in_memory_user_repository.py",
        ),
    )

    assert check_docs_claims.claims_falsas(repo) == []


def test_gate5_bloco_de_arvore_ausente_falha_fechado(tmp_path: pathlib.Path) -> None:
    """Sem a §2, o gate reprova em vez de passar.

    Um script que não encontra o que verificar e devolve 0 é a forma mais pura de
    "verde por não ter olhado": renomear o título da seção desligaria o gate sem
    que nada reclamasse.
    """
    layout = tmp_path / "docs" / "LAYOUT.md"
    layout.parent.mkdir(parents=True, exist_ok=True)
    layout.write_text("# LAYOUT\n\n## 2. Outra coisa\n", encoding="utf-8")

    problemas = check_docs_claims.claims_falsas(tmp_path)

    assert len(problemas) == 1, problemas
    assert problemas[0].startswith("FATAL:")
