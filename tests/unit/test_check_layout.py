"""Os detectores do `scripts/check_layout.py`, cada um contra um violador plantado.

**Por que na raiz de `tests/unit/`.** O sujeito é um script do repositório, não
uma camada de um bounded context — o mesmo raciocínio de `test_ci_workflow.py`,
que testa `.github/workflows/ci.yml` daqui. Pô-lo dentro de
`features/<bc>/` afirmaria que a regra é de um BC, o que é falso: as nove regras
são do repositório inteiro.

**Por que cada detector precisa de um violador plantado.** Todos eles são
varreduras que devolvem lista vazia quando o código está limpo — e devolveriam
lista vazia também se estivessem quebrados. Um `rglob` com âncora errada, um
`isinstance` trocado, um `continue` no ramo errado: nada disso tem sintoma numa
base limpa. Guarda que nunca viu um positivo não é guarda; é uma função que
devolve conjunto vazio (precedente:
`tests/unit/features/staff/test_bc_independence.py`).

**O violador mora em `tmp_path`, nunca em `src/`.** Os checadores recebem
`src_root: Path`, então uma árvore de mentira com três arquivos exercita o
detector inteiro — âncora, parsing e mensagem — sem que uma linha de código
violador entre no repositório, onde ela seria copiada por analogia.

**As três allowlists são cobradas nos dois sentidos.** Não-crescimento (entrada
nova reprova até ser justificada) e não-morte (entrada que já não corresponde a
nada em `src/` reprova também). A segunda metade é a que costuma faltar: uma
allowlist com entrada morta continua verde para sempre, e ainda documenta como
verdadeira uma dívida que já foi paga.
"""

import ast
import importlib.util
import pathlib
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src" / "restaurant_hub"
_SCRIPT = _REPO_ROOT / "scripts" / "check_layout.py"


def _carregar_script() -> types.ModuleType:
    """Importa `scripts/check_layout.py` sem mexer no `sys.path`.

    `scripts/` não é pacote instalável (o `pyproject` empacota só
    `src/restaurant_hub`), então não há import estático possível. Acrescentar o
    diretório ao `sys.path` funcionaria e contaminaria as outras 1700 suítes com
    um caminho de import que a aplicação não tem.
    """
    spec = importlib.util.spec_from_file_location("check_layout", _SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


check_layout = _carregar_script()


def _src_falso(tmp_path: pathlib.Path, arquivos: dict[str, str]) -> pathlib.Path:
    """Monta uma árvore mínima de `src/restaurant_hub/` em disco temporário.

    As chaves são caminhos relativos ao pacote (`composition_root.py`,
    `features/x/application/dtos/results.py`). O nome do pacote precisa ser
    literalmente `restaurant_hub` porque três âncoras — a de `shared`, a de
    `main.py` e a do composition root — são ancoradas nele: usar outro nome
    faria o teste passar por não ter olhado.
    """
    raiz = tmp_path / "src" / "restaurant_hub"
    for caminho, conteudo in arquivos.items():
        destino = raiz / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    return raiz


# ---------------------------------------------------------------------------
# M1 — a cobertura, que é o que fecha a causa-raiz da issue #45
# ---------------------------------------------------------------------------


def test_m1_nenhum_arquivo_de_src_escapa_do_check_layout() -> None:
    """O critério de pronto de M1, medido contra o `src/` real.

    Antes desta issue, oito arquivos casavam com zero regras — entre eles
    `composition_root.py`, o único do repositório a carregar uma decisão de
    isolamento de tenant. A auditoria que os encontrou tinha `lint-imports` em
    9 kept / 0 broken e este script em exit 0.
    """
    descobertos = check_layout.check_coverage(_SRC)

    assert descobertos == [], (
        "arquivo de src/ que nenhuma regra do check_layout lê:\n  " + "\n  ".join(descobertos)
    )


def test_m1_as_ancoras_de_cobertura_saem_das_regras_e_nao_de_uma_lista_paralela() -> None:
    """A propriedade que impede a cobertura de envelhecer.

    Se `coverage_anchors()` fosse uma segunda lista escrita à mão, uma regra
    nova entraria sem âncora e M1 voltaria a ter buraco — com o gate verde, que
    é exatamente o defeito que M1 existe para fechar. Esta asserção cobra a
    derivação: toda âncora de camada declarada em `FORBIDDEN_IMPORTS` aparece na
    cobertura sem ninguém a copiar.
    """
    ancoras = check_layout.coverage_anchors()
    de_camada = {padrao for padrao, _ in check_layout.FORBIDDEN_IMPORTS}

    assert de_camada <= set(ancoras)


def test_m1_nenhuma_ancora_de_cobertura_esta_morta() -> None:
    """A outra metade: âncora que já não corresponde a arquivo nenhum.

    Uma âncora morta não reprova nada e nunca reprovará — e pior, ela *conta*
    como cobertura para quem lê a lista, escondendo que a regra correspondente
    deixou de ter sujeito. É a mesma falha de uma allowlist com entrada morta,
    do outro lado do gate.
    """
    caminhos = [check_layout.posix(arquivo) for arquivo in _SRC.rglob("*.py")]
    mortas = sorted(
        f"{ancora} ({regra})"
        for ancora, regra in check_layout.coverage_anchors().items()
        if not any(ancora in caminho for caminho in caminhos)
    )

    assert mortas == [], f"âncoras que não casam com nenhum arquivo de src/: {mortas}"


def test_m1_um_arquivo_fora_de_toda_ancora_reprova(tmp_path: pathlib.Path) -> None:
    """Violador plantado: o arquivo solto na raiz do pacote.

    É a forma exata que `composition_root.py` tinha — um módulo na raiz, fora de
    `domain/`, `application/`, `adapters/` e `shared/`. Nenhuma âncora o alcança,
    e antes desta issue isso não produzia sinal nenhum.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "orquestrador.py": "VALOR = 1\n",
            "shared/__init__.py": '"""Marcador."""\n',
        },
    )

    violacoes = check_layout.check_coverage(raiz)

    assert len(violacoes) == 1
    assert "orquestrador.py" in violacoes[0]


# ---------------------------------------------------------------------------
# Gate 1 (regra 6) — o charter do composition root
# ---------------------------------------------------------------------------


def test_gate1_o_composition_root_real_cumpre_o_charter() -> None:
    """O gate nasce verde — com a dívida na allowlist, não escondida."""
    assert check_layout.check_composition_root_charter(_SRC) == []


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        pytest.param(
            "class _Politica:\n    def decide(self) -> bool:\n        return True\n",
            "não é @dataclass",
            id="classe-com-comportamento",
        ),
        pytest.param(
            "def _resolver_tenant() -> str:\n    return 'x'\n",
            "fora do charter",
            id="funcao-que-nao-e-wiring",
        ),
        pytest.param(
            "def wire_dependencies() -> None:\n    raise ValueError('sem tenant')\n",
            "`raise` no composition root",
            id="raise-dentro-do-wiring",
        ),
    ],
)
def test_gate1_o_detector_do_charter_reprova_as_tres_formas(
    tmp_path: pathlib.Path, corpo: str, esperado: str
) -> None:
    """As três portas pelas quais a decisão entra no wiring, uma a uma.

    São três testes e não um porque são três ramos independentes do detector: um
    `elif` trocado deixaria dois deles sempre verdes, e um único caso composto
    não distinguiria qual ramo morreu.

    O `raise` é o terceiro de propósito, e é o que a auditoria encontrou vivo:
    `composition_root.py:272` decide isolamento de tenant, e nenhum gate olhava
    para lá.
    """
    raiz = _src_falso(tmp_path, {"composition_root.py": corpo})

    violacoes = check_layout.check_composition_root_charter(raiz)

    assert len(violacoes) == 1, violacoes
    assert esperado in violacoes[0]


def test_gate1_a_allowlist_do_charter_nao_cresceu() -> None:
    """Não-crescimento: entrada nova reprova até ser justificada.

    O valor da allowlist não é perdoar `_IdentityAccessGuard`; é tornar
    **contável** o número de classes que decidem acesso dentro do wiring. Hoje é
    um. Passar a dois exige editar esta linha, o que é visível em qualquer
    revisão de diff — ao contrário de acrescentar a segunda classe ao módulo.
    """
    assert set(check_layout.COMPOSITION_ROOT_CLASS_ALLOWLIST) == {"_IdentityAccessGuard"}


def test_gate1_cada_entrada_da_allowlist_do_charter_cita_a_issue_que_a_remove() -> None:
    """Justificativa é requisito, não cortesia.

    Allowlist sem ponteiro vira permanente por esquecimento: ninguém sabe dizer
    se a entrada ainda vale, e a resposta segura é sempre deixá-la. Com a issue
    citada, a pergunta tem endereço.
    """
    sem_ponteiro = sorted(
        nome
        for nome, motivo in check_layout.COMPOSITION_ROOT_CLASS_ALLOWLIST.items()
        if "#" not in motivo and "ADR" not in motivo
    )

    assert sem_ponteiro == []


def test_gate1_a_allowlist_do_charter_nao_tem_entrada_morta() -> None:
    """Entrada morta reprova: a classe perdoada precisa existir de fato.

    Quando a #47 mover `_IdentityAccessGuard` para
    `features/staff/adapters/out/identity/`, é este teste que cobra a remoção da
    linha — sem ele a dívida continuaria documentada como viva depois de paga, e
    a próxima classe entraria por baixo de um perdão já vencido.
    """
    arvore = ast.parse((_SRC / "composition_root.py").read_text(encoding="utf-8"))
    declaradas = {no.name for no in arvore.body if isinstance(no, ast.ClassDef)}
    orfas = sorted(set(check_layout.COMPOSITION_ROOT_CLASS_ALLOWLIST) - declaradas)

    assert orfas == [], f"allowlist perdoa classe que não existe mais: {orfas}"


# ---------------------------------------------------------------------------
# Gate 6 (regra 7) — DTO não tem comportamento
# ---------------------------------------------------------------------------


def test_gate6_os_dtos_reais_nao_tem_comportamento_fora_da_allowlist() -> None:
    assert check_layout.check_dto_behaviour(_SRC) == []


def test_gate6_um_metodo_plantado_num_dto_reprova(tmp_path: pathlib.Path) -> None:
    """Violador plantado, e com um dunder ao lado para provar o filtro.

    `__post_init__` é o método legítimo mais comum num DTO `frozen`; se o
    detector o acusasse, a regra seria inaplicável e a saída seria afrouxá-la.
    O teste cobra as duas coisas de uma vez: acusa `total_devido`, ignora
    `__post_init__`.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "features/pedidos/application/dtos/results.py": (
                "class PedidoResult:\n"
                "    def __post_init__(self) -> None:\n"
                "        pass\n"
                "\n"
                "    def total_devido(self) -> int:\n"
                "        return 0\n"
            )
        },
    )

    violacoes = check_layout.check_dto_behaviour(raiz)

    assert len(violacoes) == 1, violacoes
    assert "PedidoResult.total_devido" in violacoes[0]


def test_gate6_a_allowlist_de_dtos_nao_cresceu() -> None:
    """Os dois métodos que a auditoria encontrou, e nenhum a mais."""
    assert set(check_layout.DTO_METHOD_ALLOWLIST) == {
        ("Session", "is_active"),
        ("PasswordSetupToken", "is_usable"),
    }


def test_gate6_cada_entrada_da_allowlist_de_dtos_cita_o_seu_adr() -> None:
    sem_ponteiro = sorted(
        f"{classe}.{metodo}"
        for (classe, metodo), motivo in check_layout.DTO_METHOD_ALLOWLIST.items()
        if "ADR" not in motivo
    )

    assert sem_ponteiro == []


def test_gate6_a_allowlist_de_dtos_nao_tem_entrada_morta() -> None:
    """O par (classe, método) perdoado precisa existir em `application/dtos/`.

    A chave é o par justamente para isto: um `is_active` numa classe nova não
    herda o perdão deste, e um `Session.is_active` renomeado deixa a entrada
    órfã — que é o momento em que ela deve sair, não ficar.
    """
    reais: set[tuple[str, str]] = set()
    for arquivo in _SRC.rglob("*.py"):
        if check_layout.DTOS_ANCHOR not in check_layout.posix(arquivo):
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ClassDef):
                continue
            reais.update(
                (no.name, membro.name)
                for membro in no.body
                if isinstance(membro, ast.FunctionDef | ast.AsyncFunctionDef)
            )

    orfas = sorted(set(check_layout.DTO_METHOD_ALLOWLIST) - reais)

    assert orfas == [], f"allowlist perdoa método que não existe mais: {orfas}"


# ---------------------------------------------------------------------------
# Regras 5 e 9 — as duas que M1 obrigou a existir
# ---------------------------------------------------------------------------


def test_regra5_o_entrypoint_real_nao_conhece_feature() -> None:
    assert [v for v in check_layout.check_layer_imports(_SRC) if "main.py" in v] == []


def test_regra5_um_entrypoint_que_importa_feature_reprova(tmp_path: pathlib.Path) -> None:
    """`main.py` é o caminho mais curto para instanciar adapter fora do wiring.

    `app = create_app()` a uma linha de distância de um repositório concreto não
    pareceria estranho a ninguém — e nenhuma âncora de camada olhava para este
    arquivo antes de M1.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "main.py": (
                "from restaurant_hub.features.identity.adapters.out.postgres."
                "user_repository import PostgresUserRepository\n"
            )
        },
    )

    violacoes = check_layout.check_layer_imports(raiz)

    assert len(violacoes) == 1, violacoes
    assert "main.py" in violacoes[0]


def test_regra9_os_marcadores_de_pacote_reais_so_tem_docstring() -> None:
    assert check_layout.check_package_markers(_SRC) == []


def test_regra9_um_reexport_no_marcador_de_pacote_reprova(tmp_path: pathlib.Path) -> None:
    """O ponto cego de M1 em miniatura.

    `from restaurant_hub.features.identity import User` não casa com `/domain/`,
    `/application/` nem `/adapters/` — o import atravessa a fronteira por um
    caminho que nenhuma regra de camada inspeciona. E re-exportar parece
    cortesia com quem importa, que é o que torna esta a porta mais fácil de
    abrir sem intenção.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "features/identity/__init__.py": (
                '"""Feature identity."""\n'
                "from restaurant_hub.features.identity.domain.entities.user import User\n"
            )
        },
    )

    violacoes = check_layout.check_package_markers(raiz)

    assert len(violacoes) == 1, violacoes
    assert "ImportFrom" in violacoes[0]
