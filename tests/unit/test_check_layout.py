"""Os detectores do `scripts/check_layout.py`, cada um contra um violador plantado.

**Por que na raiz de `tests/unit/`.** O sujeito é um script do repositório, não
uma camada de um bounded context — o mesmo raciocínio de `test_ci_workflow.py`,
que testa `.github/workflows/ci.yml` daqui. Pô-lo dentro de
`features/<bc>/` afirmaria que a regra é de um BC, o que é falso: as dez regras
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
import sys
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

    O valor da allowlist é tornar **contável** o número de classes que decidem
    acesso dentro do wiring. Era um (`_IdentityAccessGuard`) até a issue #47, que
    o moveu para `staff/adapters/out/identity/` e pagou a dívida: hoje é zero.
    Passar a um exige editar esta linha, o que é visível em qualquer revisão de
    diff — ao contrário de acrescentar a classe ao módulo.
    """
    assert set(check_layout.COMPOSITION_ROOT_CLASS_ALLOWLIST) == set()


def test_gate1_a_allowlist_de_funcoes_do_charter_nao_cresceu() -> None:
    """A segunda metade do charter, e a que a Stage 3.6 estreou.

    `_tenant_id_do_ator` entrou no `composition_root.py` **depois** que este gate
    foi escrito e **antes** de ele mergear — o gate a encontrou em vez de tê-la
    impedido. Saiu com a issue #47, junto do tradutor que a usava. Fixar o
    conjunto vazio é o que impede a próxima.
    """
    assert set(check_layout.COMPOSITION_ROOT_FUNCTION_ALLOWLIST) == set()


def test_gate1_a_allowlist_de_funcoes_nao_tem_entrada_morta() -> None:
    """A função perdoada precisa existir — e sair da lista quando a #47 a mover."""
    arvore = ast.parse((_SRC / "composition_root.py").read_text(encoding="utf-8"))
    declaradas = {
        no.name for no in arvore.body if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    orfas = sorted(set(check_layout.COMPOSITION_ROOT_FUNCTION_ALLOWLIST) - declaradas)

    assert orfas == [], f"allowlist perdoa função que não existe mais: {orfas}"


def test_gate1_a_allowlist_de_raise_cobre_as_duas_unidades_da_mesma_divida() -> None:
    """As três allowlists do charter descrevem **uma** dívida, e derivam disso.

    `_IdentityAccessGuard` e o seu helper saem juntos na #47. Se a allowlist de
    `raise` fosse escrita à parte, tirar a classe de uma delas deixaria o `raise`
    perdoado pela outra — e a dívida contaria como paga com metade dela de pé.
    """
    assert set(check_layout.COMPOSITION_ROOT_RAISE_ALLOWLIST) == (
        set(check_layout.COMPOSITION_ROOT_CLASS_ALLOWLIST)
        | set(check_layout.COMPOSITION_ROOT_FUNCTION_ALLOWLIST)
    )


def test_gate1_cada_entrada_das_allowlists_do_charter_cita_a_issue_que_a_remove() -> None:
    """Justificativa é requisito, não cortesia.

    Allowlist sem ponteiro vira permanente por esquecimento: ninguém sabe dizer
    se a entrada ainda vale, e a resposta segura é sempre deixá-la. Com a issue
    citada, a pergunta tem endereço. Vale para as **duas** listas — a de classes
    e a de funções —, porque as duas perdoam pelo mesmo motivo.
    """
    entradas = {
        **check_layout.COMPOSITION_ROOT_CLASS_ALLOWLIST,
        **check_layout.COMPOSITION_ROOT_FUNCTION_ALLOWLIST,
    }
    sem_ponteiro = sorted(
        nome for nome, motivo in entradas.items() if "#" not in motivo and "ADR" not in motivo
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
# Gate 8 (regra 8) — um sítio de construção por result
# ---------------------------------------------------------------------------


def test_gate8_cada_result_real_e_construido_em_um_sitio() -> None:
    """Verde depois da extração dos mapeadores; era 11 sítios para `EmployeeResult`."""
    assert check_layout.check_result_construction_sites(_SRC) == []


def test_gate8_dois_sitios_reprovam(tmp_path: pathlib.Path) -> None:
    """O caso que a issue mediu: o result montado campo a campo em vários lugares."""
    raiz = _src_falso(
        tmp_path,
        {
            "features/pedidos/application/dtos/results.py": "class PedidoResult:\n    pass\n",
            "features/pedidos/application/use_cases/criar.py": "x = PedidoResult()\n",
            "features/pedidos/application/use_cases/listar.py": "y = PedidoResult()\n",
        },
    )

    violacoes = check_layout.check_result_construction_sites(raiz)

    assert len(violacoes) == 1, violacoes
    assert "construído em 2 sítio(s)" in violacoes[0]


def test_gate8_zero_sitios_tambem_reprova(tmp_path: pathlib.Path) -> None:
    """Result que ninguém constrói é DTO morto — e é como uma extração pela metade termina.

    Sem este caso, `EXPECTED_CONSTRUCTION_SITES` poderia virar `<= 1` sem que a
    suíte notasse, e o gate passaria a aprovar o DTO órfão que o Gate 7 existe
    para caçar do outro lado.
    """
    raiz = _src_falso(
        tmp_path,
        {"features/pedidos/application/dtos/results.py": "class PedidoResult:\n    pass\n"},
    )

    violacoes = check_layout.check_result_construction_sites(raiz)

    assert len(violacoes) == 1, violacoes
    assert "construído em 0 sítio(s)" in violacoes[0]


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


# ---------------------------------------------------------------------------
# Regra 10 — escrita múltipla só dentro de uma unidade (Stage 2.6, ADR 2.6.0002 §5)
# ---------------------------------------------------------------------------

_PORT_DE_REPOSITORIO = (
    "from typing import Protocol\n\n\n"
    "class CoisaRepository(Protocol):\n"
    "    def add(self, x: str) -> None: ...\n"
    "    def remove(self, x: str) -> None: ...\n"
    "    def find_by_id(self, x: str) -> str | None: ...\n"
)
_PORT_DA_UNIDADE = (
    "from typing import Protocol\n\n\n"
    "class UnitOfWork(Protocol):\n"
    "    def transaction(self) -> object: ...\n"
)
_CABECALHO_DO_USE_CASE = (
    "class Fazer:\n"
    "    def __init__(self, coisas: CoisaRepository, unit_of_work: UnitOfWork) -> None:\n"
    "        self._coisas = coisas\n"
    "        self._unit_of_work = unit_of_work\n\n"
)


@pytest.fixture
def regra10_isolada(monkeypatch: pytest.MonkeyPatch) -> None:
    """Esvazia as tabelas globais da regra 10 para a árvore sintética.

    A allowlist e os métodos de gateway declarados apontam para o `src/` real; numa
    árvore de três arquivos eles apareceriam como entradas mortas e afogariam a
    violação que o teste planta.
    """
    monkeypatch.setattr(check_layout, "MULTI_WRITE_ALLOWLIST", {})
    monkeypatch.setattr(check_layout, "GATEWAY_WRITE_METHODS", {})


def _src_com_use_case(tmp_path: pathlib.Path, corpo: str) -> pathlib.Path:
    return _src_falso(
        tmp_path,
        {
            "features/x/application/ports/out/coisa_repository.py": _PORT_DE_REPOSITORIO,
            "features/x/application/ports/out/unit_of_work.py": _PORT_DA_UNIDADE,
            "features/x/application/use_cases/fazer.py": _CABECALHO_DO_USE_CASE + corpo,
        },
    )


_DUAS_DENTRO = (
    "    def execute(self) -> None:\n"
    "        with self._unit_of_work.transaction():\n"
    "            self._coisas.add('a')\n"
    "            self._coisas.remove('b')\n"
)


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        pytest.param(
            "    def execute(self) -> None:\n"
            "        self._coisas.add('a')\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.remove('b')\n",
            "fora de unidade: self._coisas.add",
            id="uma-escrita-movida-para-fora",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.add('a')\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.remove('b')\n",
            "2 blocos de unidade",
            id="duas-unidades",
        ),
        pytest.param(
            "    def execute(self, xs: list[str]) -> None:\n"
            "        for x in xs:\n"
            "            self._coisas.add(x)\n",
            "fora de unidade: self._coisas.add",
            id="escrita-em-laco-fora-de-unidade",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        self._gravar()\n\n"
            "    def _gravar(self) -> None:\n"
            "        self._coisas.add('a')\n"
            "        self._coisas.remove('b')\n",
            "fora de unidade",
            id="escritas-num-helper-sem-unidade",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        self._coisas.add('a')\n"
            "        self._coisas.remove('b')\n",
            "fora de unidade",
            id="duas-escritas-sem-unidade",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        if not self._coisas.remove('x'):\n"
            "            raise ValueError('perdeu')\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.add('a')\n",
            "fora de unidade: self._coisas.remove",
            id="escrita-no-teste-de-um-if-fora-da-unidade",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        try:\n"
            "            self._coisas.find_by_id('a')\n"
            "        except KeyError:\n"
            "            self._coisas.remove('a')\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.add('a')\n",
            "fora de unidade: self._coisas.remove",
            id="escrita-num-except-fora-da-unidade",
        ),
        pytest.param(
            "    def execute(self, xs: list[str]) -> None:\n"
            "        for x in xs:\n"
            "            with self._unit_of_work.transaction():\n"
            "                self._coisas.add(x)\n",
            "2 blocos de unidade",
            id="unidade-dentro-de-laco",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        self._gravar('a')\n"
            "        self._gravar('b')\n\n"
            "    def _gravar(self, x: str) -> None:\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.add(x)\n",
            "2 blocos de unidade",
            id="helper-que-abre-unidade-chamado-duas-vezes",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        while self._coisas.remove('lote'):\n"
            "            pass\n",
            "fora de unidade: self._coisas.remove",
            id="escrita-na-condicao-de-um-while",
        ),
        pytest.param(
            "    async def execute(self) -> None:\n"
            "        self._coisas.add('a')\n"
            "        self._coisas.remove('b')\n",
            "fora de unidade",
            id="metodo-async",
        ),
        pytest.param(
            "    def execute(self, x: str) -> None:\n"
            "        match x:\n"
            "            case 'a':\n"
            "                self._coisas.add('a')\n"
            "                self._coisas.remove('b')\n",
            "fora de unidade",
            id="escritas-dentro-de-match",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        while self._continuar():\n"
            "            self._coisas.add('a')\n\n"
            "    def _continuar(self) -> bool:\n"
            "        return False\n",
            "fora de unidade: self._coisas.add",
            id="escrita-no-corpo-de-um-while-fora-de-unidade",
        ),
        pytest.param(
            "    def execute(self, xs: list[str]) -> None:\n"
            "        [self._coisas.add(x) for x in xs]\n",
            "fora de unidade: self._coisas.add",
            id="escrita-dentro-de-compreensao-fora-de-unidade",
        ),
        pytest.param(
            "    def execute(self, xs: list[str]) -> None:\n"
            "        any(self._coisas.add(x) for x in xs)\n",
            "fora de unidade: self._coisas.add",
            id="escrita-dentro-de-genexp-fora-de-unidade",
        ),
        pytest.param(
            "    def execute(self, xs: list[str]) -> None:\n"
            "        {self._coisas.add(x) for x in xs}\n",
            "fora de unidade: self._coisas.add",
            id="escrita-dentro-de-setcomp-fora-de-unidade",
        ),
        pytest.param(
            "    async def execute(self, xs: object) -> None:\n"
            "        async for x in xs:\n"
            "            self._coisas.add(x)\n",
            "fora de unidade: self._coisas.add",
            id="escrita-em-async-for-fora-de-unidade",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        match self._coisas.remove('x'):\n"
            "            case _:\n"
            "                pass\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.add('a')\n",
            "fora de unidade: self._coisas.remove",
            id="escrita-no-subject-de-um-match",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        for _ in [self._coisas.remove('x')]:\n"
            "            pass\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.add('a')\n",
            "fora de unidade: self._coisas.remove",
            id="escrita-no-iter-de-um-for",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        with self._ctx(self._coisas.remove('x')):\n"
            "            pass\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.add('a')\n\n"
            "    def _ctx(self, x: object) -> object:\n"
            "        return x\n",
            "fora de unidade: self._coisas.remove",
            id="escrita-nos-itens-de-um-with",
        ),
        pytest.param(
            "    def execute(self, xs: list[str]) -> None:\n"
            "        for x in xs:\n"
            "            pass\n"
            "        else:\n"
            "            self._coisas.remove('x')\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.add('a')\n",
            "fora de unidade: self._coisas.remove",
            id="escrita-no-else-de-um-for",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        self._gravar(3)\n\n"
            "    def _gravar(self, n: int) -> None:\n"
            "        self._coisas.add('a')\n"
            "        if n:\n"
            "            self._gravar(n - 1)\n"
            "        self._coisas.remove('b')\n",
            "fora de unidade",
            id="helper-recursivo-nao-trava-o-detector",
        ),
    ],
)
@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_o_detector_reprova_cada_forma(
    tmp_path: pathlib.Path, corpo: str, esperado: str
) -> None:
    """CA11 — as formas que a regra existe para barrar, uma a uma.

    A primeira é a do achado do Checkpoint A: o `consume` movido para fora da
    unidade de `set_password_with_token`, com o resto dentro — uma regra de
    "no máximo uma escrita fora" a deixaria passar.
    """
    violacoes = check_layout.check_multi_write_unit_of_work(_src_com_use_case(tmp_path, corpo))

    assert len(violacoes) == 1, violacoes
    assert "'Fazer'" in violacoes[0]
    assert esperado in violacoes[0]


@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param(_DUAS_DENTRO, id="duas-dentro-de-uma-unidade"),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._gravar()\n\n"
            "    def _gravar(self) -> None:\n"
            "        self._coisas.add('a')\n"
            "        self._coisas.remove('b')\n",
            id="helper-chamado-de-dentro-da-unidade",
        ),
        pytest.param(
            "    def execute(self, reuso: bool) -> None:\n"
            "        if reuso:\n"
            "            self._coisas.remove('todas')\n"
            "            raise ValueError('reuso')\n"
            "        with self._unit_of_work.transaction():\n"
            "            self._coisas.remove('a')\n"
            "            self._coisas.add('b')\n",
            id="grava-e-recusa-fora-da-unidade",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        if self._coisas.find_by_id('a') is None:\n"
            "            self._coisas.add('a')\n",
            id="leitura-mais-uma-escrita",
        ),
        pytest.param(
            "    def execute(self, xs: list[str]) -> None:\n"
            "        self._coisas.add(','.join(x for x in xs))\n",
            id="uma-escrita-com-compreensao-no-argumento",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        self.outro()\n\n"
            "    def outro(self) -> None:\n"
            "        self._coisas.add('a')\n",
            id="publico-chamando-publico-nao-conta-duas-vezes",
        ),
        pytest.param(
            "    def execute(self) -> None:\n"
            "        with self._unit_of_work.transaction():\n"
            "            with open('x') as f:\n"
            "                self._coisas.add(f.read())\n"
            "                self._coisas.remove('b')\n",
            id="with-aninhado-dentro-da-unidade",
        ),
        pytest.param(
            "    async def execute(self) -> None:\n"
            "        async with self._unit_of_work.transaction():\n"
            "            self._coisas.add('a')\n"
            "            self._coisas.remove('b')\n",
            id="async-with-da-unidade",
        ),
    ],
)
@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_o_detector_aceita_o_que_o_adr_permite(tmp_path: pathlib.Path, corpo: str) -> None:
    assert check_layout.check_multi_write_unit_of_work(_src_com_use_case(tmp_path, corpo)) == []


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_unidade_de_atributo_que_nao_e_unit_of_work_nao_conta(
    tmp_path: pathlib.Path,
) -> None:
    """`with self._coisas.transaction()` não é unidade: o atributo não é `UnitOfWork`."""
    corpo = (
        "    def execute(self) -> None:\n"
        "        with self._coisas.transaction():\n"
        "            self._coisas.add('a')\n"
        "            self._coisas.remove('b')\n"
    )
    violacoes = check_layout.check_multi_write_unit_of_work(_src_com_use_case(tmp_path, corpo))

    assert len(violacoes) == 1, violacoes


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_entrada_da_allowlist_sem_violacao_reprova(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check_layout, "MULTI_WRITE_ALLOWLIST", {"Fazer": "motivo de teste"})

    violacoes = check_layout.check_multi_write_unit_of_work(
        _src_com_use_case(tmp_path, _DUAS_DENTRO)
    )

    assert any("'Fazer' está na allowlist mas não viola" in v for v in violacoes), violacoes


# --- Auxiliares que escrevem: derivados do código (issue #243) -----------------
#
# Até a issue #243 a regra 10 só contava a chamada a um auxiliar declarado à mão
# (`HELPER_WRITES`); um auxiliar novo que gravasse pelo parâmetro ficava invisível.
# Os casos abaixo plantam o auxiliar num módulo `_aux.py` ao lado do use case e o
# importam como o código real importa (`from <pacote>.use_cases._aux import f`).

_PACOTE_DOS_USE_CASES = "restaurant_hub.features.x.application.use_cases"
_GATEWAY = (
    "from typing import Protocol\n\n\n"
    "class OutroGateway(Protocol):\n"
    "    def gravar(self, x: str) -> None: ...\n"
    "    def ler(self, x: str) -> str: ...\n"
)


def _use_case_que_chama(chamada: str, importacao: str) -> str:
    """Use case com uma escrita própria fora de unidade, mais a `chamada` ao auxiliar."""
    return (
        importacao
        + "\n\n"
        + _CABECALHO_DO_USE_CASE
        + "    def execute(self) -> None:\n"
        + f"        {chamada}\n"
        + "        self._coisas.add('a')\n"
    )


def _src_com_auxiliar(
    tmp_path: pathlib.Path,
    auxiliar: str,
    chamada: str = "revogar(self._coisas)",
    importacao: str = f"from {_PACOTE_DOS_USE_CASES}._aux import revogar",
    extras: dict[str, str] | None = None,
) -> pathlib.Path:
    return _src_falso(
        tmp_path,
        {
            "features/x/application/ports/out/coisa_repository.py": _PORT_DE_REPOSITORIO,
            "features/x/application/ports/out/unit_of_work.py": _PORT_DA_UNIDADE,
            "features/x/application/ports/out/outro_gateway.py": _GATEWAY,
            "features/x/application/use_cases/_aux.py": auxiliar,
            "features/x/application/use_cases/fazer.py": _use_case_que_chama(chamada, importacao),
            **(extras or {}),
        },
    )


_AUXILIAR_QUE_REMOVE = "def revogar(coisas: CoisaRepository) -> None:\n    coisas.remove('s')\n"


@pytest.mark.parametrize(
    "auxiliar",
    [
        pytest.param(_AUXILIAR_QUE_REMOVE, id="repositorio-por-parametro"),
        pytest.param(
            "def revogar(coisas: CoisaRepository | None) -> None:\n"
            "    if coisas is not None:\n"
            "        coisas.remove('s')\n",
            id="anotacao-com-none",
        ),
        pytest.param(
            "def revogar(coisas: 'CoisaRepository') -> None:\n    coisas.remove('s')\n",
            id="anotacao-em-string",
        ),
        pytest.param(
            "def revogar(*, coisas: ports.CoisaRepository) -> None:\n    coisas.remove('s')\n",
            id="anotacao-qualificada-e-keyword-only",
        ),
        pytest.param(
            "def revogar(coisas: CoisaRepository) -> None:\n"
            "    def dentro() -> None:\n"
            "        coisas.remove('s')\n"
            "    dentro()\n",
            id="closure-sobre-o-parametro",
        ),
        pytest.param(
            "async def revogar(coisas: CoisaRepository) -> None:\n    await coisas.remove('s')\n",
            id="auxiliar-async",
        ),
        pytest.param(
            "def revogar(coisas: CoisaRepository) -> None:\n    _gravar(coisas)\n\n\n"
            "def _gravar(coisas: CoisaRepository) -> None:\n    coisas.remove('s')\n",
            id="transitivo-no-mesmo-modulo",
        ),
        pytest.param(
            f"from {_PACOTE_DOS_USE_CASES}._base import gravar\n\n\n"
            "def revogar(coisas: CoisaRepository) -> None:\n    gravar(coisas)\n",
            id="transitivo-por-import",
        ),
        pytest.param(
            "from . import _base\n\n\n"
            "def revogar(coisas: CoisaRepository) -> None:\n    _base.gravar(coisas)\n",
            id="transitivo-por-import-relativo-de-modulo",
        ),
        pytest.param(
            "from functools import partial\n\n\n"
            "def revogar(coisas: CoisaRepository) -> None:\n    partial(_gravar, coisas)()\n\n\n"
            "def _gravar(coisas: CoisaRepository) -> None:\n    coisas.remove('s')\n",
            id="transitivo-por-referencia-em-partial",
        ),
        pytest.param(
            "class _Gravador:\n"
            "    @staticmethod\n"
            "    def gravar(coisas: CoisaRepository) -> None:\n"
            "        coisas.remove('s')\n\n\n"
            "def revogar(coisas: CoisaRepository) -> None:\n    _Gravador.gravar(coisas)\n",
            id="transitivo-por-metodo-estatico-do-modulo",
        ),
    ],
)
@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_auxiliar_que_escreve_e_contado_sem_declaracao(
    tmp_path: pathlib.Path, auxiliar: str
) -> None:
    """Critério da #243: o auxiliar que grava pelo parâmetro conta, sem tabela nenhuma."""
    base = "def gravar(coisas: CoisaRepository) -> None:\n    coisas.remove('s')\n"
    raiz = _src_com_auxiliar(
        tmp_path, auxiliar, extras={"features/x/application/use_cases/_base.py": base}
    )

    violacoes = check_layout.check_multi_write_unit_of_work(raiz)

    assert len(violacoes) == 1, violacoes
    assert "'Fazer'" in violacoes[0]
    assert "revogar() (linha" in violacoes[0]


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_auxiliar_que_escreve_por_gateway_declarado_e_contado(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O caso de `end_active_link`: a escrita é método de `GATEWAY_WRITE_METHODS`."""
    monkeypatch.setattr(
        check_layout, "GATEWAY_WRITE_METHODS", {"OutroGateway": frozenset({"gravar"})}
    )
    auxiliar = "def revogar(gateway: OutroGateway) -> None:\n    gateway.gravar('s')\n"

    violacoes = check_layout.check_multi_write_unit_of_work(
        _src_com_auxiliar(tmp_path, auxiliar, chamada="revogar(object())")
    )

    assert len(violacoes) == 1, violacoes
    assert "revogar()" in violacoes[0]


@pytest.mark.parametrize(
    "auxiliar",
    [
        pytest.param(
            "def revogar(coisas: CoisaRepository) -> None:\n    coisas.find_by_id('s')\n",
            id="so-le-o-repositorio",
        ),
        pytest.param(
            "def revogar(gateway: OutroGateway) -> None:\n    gateway.ler('s')\n",
            id="so-le-o-gateway",
        ),
        pytest.param(
            "def revogar(coisas: CoisaRepository) -> None:\n    _ler(coisas)\n\n\n"
            "def _ler(coisas: CoisaRepository) -> None:\n    coisas.find_by_id('s')\n",
            id="so-chama-quem-le",
        ),
        pytest.param(
            "def revogar(coisas: object) -> None:\n    coisas.remove('s')\n",
            id="parametro-que-nao-e-port",
        ),
    ],
)
@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_auxiliar_que_so_le_nao_e_contado(tmp_path: pathlib.Path, auxiliar: str) -> None:
    """Controle negativo — os auxiliares de scheduling recebem repositório só para ler."""
    raiz = _src_com_auxiliar(tmp_path, auxiliar)

    assert check_layout.check_multi_write_unit_of_work(raiz) == []
    assert check_layout.helper_writes(raiz) == {}


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_homonimo_em_outro_modulo_nao_contamina(tmp_path: pathlib.Path) -> None:
    """A chamada é resolvida pelo import: o `revogar` que só lê não herda a escrita do outro."""
    que_le = "def revogar(coisas: CoisaRepository) -> None:\n    coisas.find_by_id('s')\n"
    raiz = _src_com_auxiliar(
        tmp_path,
        que_le,
        extras={"features/x/application/use_cases/_outro.py": _AUXILIAR_QUE_REMOVE},
    )

    assert check_layout.check_multi_write_unit_of_work(raiz) == []
    assert set(check_layout.helper_writes(raiz)) == {f"{_PACOTE_DOS_USE_CASES}._outro.revogar"}

    pelo_outro = _src_com_auxiliar(
        tmp_path / "b",
        que_le,
        importacao=f"from {_PACOTE_DOS_USE_CASES}._outro import revogar",
        extras={"features/x/application/use_cases/_outro.py": _AUXILIAR_QUE_REMOVE},
    )
    assert len(check_layout.check_multi_write_unit_of_work(pelo_outro)) == 1


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_definicao_local_vence_o_homonimo_de_outro_modulo(tmp_path: pathlib.Path) -> None:
    """O `revogar` definido no próprio módulo do use case é o chamado — não o de `_outro`."""
    raiz = _src_falso(
        tmp_path,
        {
            "features/x/application/ports/out/coisa_repository.py": _PORT_DE_REPOSITORIO,
            "features/x/application/ports/out/unit_of_work.py": _PORT_DA_UNIDADE,
            "features/x/application/use_cases/_outro.py": _AUXILIAR_QUE_REMOVE,
            "features/x/application/use_cases/fazer.py": (
                "def revogar(coisas: CoisaRepository) -> None:\n"
                "    coisas.find_by_id('s')\n\n\n"
                + _use_case_que_chama("revogar(self._coisas)", "")
            ),
        },
    )

    assert check_layout.check_multi_write_unit_of_work(raiz) == []


@pytest.mark.parametrize(
    ("chamada", "importacao"),
    [
        pytest.param(
            "apagar(self._coisas)",
            f"from {_PACOTE_DOS_USE_CASES}._aux import revogar as apagar",
            id="import-com-alias",
        ),
        pytest.param(
            "_aux.revogar(self._coisas)",
            f"from {_PACOTE_DOS_USE_CASES} import _aux",
            id="atributo-de-modulo-importado",
        ),
        pytest.param(
            "aux.revogar(self._coisas)",
            f"import {_PACOTE_DOS_USE_CASES}._aux as aux",
            id="import-de-modulo-com-alias",
        ),
        pytest.param(
            "revogar(self._coisas)",
            f"from {_PACOTE_DOS_USE_CASES}._aux import *",
            id="star-import-cai-no-fail-closed-por-nome",
        ),
        # A função citada sem ser chamada ali (auditoria do PR #257): a chamada de
        # verdade a árvore não resolve, então a referência conta no lugar dela.
        pytest.param(
            "partial(revogar, self._coisas)()",
            f"from functools import partial\nfrom {_PACOTE_DOS_USE_CASES}._aux import revogar",
            id="referencia-em-functools-partial",
        ),
        pytest.param(
            "list(map(revogar, [self._coisas]))",
            f"from {_PACOTE_DOS_USE_CASES}._aux import revogar",
            id="referencia-passada-como-callable",
        ),
        pytest.param(
            "apagar = revogar; apagar(self._coisas)",
            f"from {_PACOTE_DOS_USE_CASES}._aux import revogar",
            id="alias-local-da-funcao",
        ),
    ],
)
@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_a_chamada_ao_auxiliar_e_resolvida_em_cada_forma_de_import(
    tmp_path: pathlib.Path, chamada: str, importacao: str
) -> None:
    raiz = _src_com_auxiliar(tmp_path, _AUXILIAR_QUE_REMOVE, chamada, importacao)

    violacoes = check_layout.check_multi_write_unit_of_work(raiz)

    assert len(violacoes) == 1, violacoes
    assert "revogar()" in violacoes[0]


@pytest.mark.parametrize(
    ("auxiliar", "chamada", "importacao"),
    [
        pytest.param(
            "class Gravador:\n"
            "    @staticmethod\n"
            "    def revogar(coisas: CoisaRepository) -> None:\n"
            "        coisas.remove('s')\n",
            "Gravador.revogar(self._coisas)",
            f"from {_PACOTE_DOS_USE_CASES}._aux import Gravador",
            id="estatico-de-classe-importada",
        ),
        pytest.param(
            "class Gravador:\n"
            "    @classmethod\n"
            "    def revogar(cls, coisas: CoisaRepository) -> None:\n"
            "        coisas.remove('s')\n",
            "_aux.Gravador.revogar(self._coisas)",
            f"from {_PACOTE_DOS_USE_CASES} import _aux",
            id="de-classe-pelo-modulo",
        ),
    ],
)
@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_metodo_estatico_ou_de_classe_de_modulo_auxiliar_conta(
    tmp_path: pathlib.Path, auxiliar: str, chamada: str, importacao: str
) -> None:
    """Chamado sem instância, é função de módulo com outro nome (auditoria do PR #257)."""
    raiz = _src_com_auxiliar(tmp_path, auxiliar, chamada, importacao)

    violacoes = check_layout.check_multi_write_unit_of_work(raiz)

    assert len(violacoes) == 1, violacoes
    assert "Gravador.revogar() (linha" in violacoes[0]


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_port_entregue_por_parametro_a_metodo_do_use_case_conta(
    tmp_path: pathlib.Path,
) -> None:
    """`self._salvar(self._coisas)` com `c.remove()` dentro: a escrita é do use case.

    O varredor só lia `self.<atributo>.<método>`; o repositório entregue por parâmetro
    a um método da própria classe escapava (auditoria do PR #257).
    """
    raiz = _src_com_use_case(
        tmp_path,
        "    def execute(self) -> None:\n"
        "        self._salvar(self._coisas)\n"
        "        self._coisas.add('a')\n\n"
        "    def _salvar(self, c: CoisaRepository) -> None:\n"
        "        c.remove('s')\n"
        "        c.find_by_id('s')\n",
    )

    violacoes = check_layout.check_multi_write_unit_of_work(raiz)

    assert len(violacoes) == 1, violacoes
    assert "c.remove (linha" in violacoes[0]
    assert "find_by_id" not in violacoes[0]


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_referencia_a_auxiliar_que_so_le_ou_a_nome_local_nao_conta(
    tmp_path: pathlib.Path,
) -> None:
    """Controle das referências: só a que o módulo resolve para um auxiliar que escreve."""
    que_le = "def revogar(coisas: CoisaRepository) -> None:\n    coisas.find_by_id('s')\n"
    raiz = _src_com_auxiliar(tmp_path, que_le, chamada="partial(revogar, self._coisas)()")
    assert check_layout.check_multi_write_unit_of_work(raiz) == []

    homonimo_local = _src_com_auxiliar(
        tmp_path / "b",
        _AUXILIAR_QUE_REMOVE,
        chamada="revogar = [self._coisas]; print(revogar)",
        importacao="",
    )
    assert check_layout.check_multi_write_unit_of_work(homonimo_local) == []


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_auxiliar_definido_no_proprio_modulo_do_use_case_conta(
    tmp_path: pathlib.Path,
) -> None:
    raiz = _src_falso(
        tmp_path,
        {
            "features/x/application/ports/out/coisa_repository.py": _PORT_DE_REPOSITORIO,
            "features/x/application/ports/out/unit_of_work.py": _PORT_DA_UNIDADE,
            "features/x/application/use_cases/fazer.py": _AUXILIAR_QUE_REMOVE
            + "\n\n"
            + _use_case_que_chama("revogar(self._coisas)", ""),
        },
    )

    assert len(check_layout.check_multi_write_unit_of_work(raiz)) == 1


@pytest.mark.parametrize(
    "auxiliar",
    [
        pytest.param(
            "def revogar(coisas: CoisaRepository) -> None:\n"
            "    coisas.remove('s')\n"
            "    coisas.add('t')\n",
            id="duas-escritas",
        ),
        pytest.param(
            "def revogar(coisas: CoisaRepository, xs: list[str]) -> None:\n"
            "    for x in xs:\n"
            "        coisas.remove(x)\n",
            id="escrita-em-laco",
        ),
        pytest.param(
            "def revogar(coisas: CoisaRepository) -> None:\n"
            "    coisas.remove('s')\n"
            "    revogar(coisas)\n",
            id="recursao",
        ),
    ],
)
@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_auxiliar_multiplo_pesa_duas_escritas(
    tmp_path: pathlib.Path, auxiliar: str
) -> None:
    """Sozinho no use case e fora de unidade, o auxiliar múltiplo já reprova."""
    raiz = _src_falso(
        tmp_path,
        {
            "features/x/application/ports/out/coisa_repository.py": _PORT_DE_REPOSITORIO,
            "features/x/application/ports/out/unit_of_work.py": _PORT_DA_UNIDADE,
            "features/x/application/use_cases/_aux.py": auxiliar,
            "features/x/application/use_cases/fazer.py": (
                f"from {_PACOTE_DOS_USE_CASES}._aux import revogar\n\n\n"
                + _CABECALHO_DO_USE_CASE
                + "    def execute(self) -> None:\n"
                "        revogar(self._coisas)\n"
            ),
        },
    )

    violacoes = check_layout.check_multi_write_unit_of_work(raiz)

    assert len(violacoes) == 1, violacoes
    assert "revogar()" in violacoes[0]


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_auxiliar_de_uma_escrita_sozinho_nao_reprova(tmp_path: pathlib.Path) -> None:
    """Controle do anterior: uma escrita só, num auxiliar, é uma escrita só."""
    raiz = _src_falso(
        tmp_path,
        {
            "features/x/application/ports/out/coisa_repository.py": _PORT_DE_REPOSITORIO,
            "features/x/application/ports/out/unit_of_work.py": _PORT_DA_UNIDADE,
            "features/x/application/use_cases/_aux.py": _AUXILIAR_QUE_REMOVE,
            "features/x/application/use_cases/fazer.py": (
                f"from {_PACOTE_DOS_USE_CASES}._aux import revogar\n\n\n"
                + _CABECALHO_DO_USE_CASE
                + "    def execute(self) -> None:\n"
                "        revogar(self._coisas)\n"
            ),
        },
    )

    assert check_layout.check_multi_write_unit_of_work(raiz) == []


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_auxiliar_chamado_dentro_da_unidade_nao_reprova(tmp_path: pathlib.Path) -> None:
    raiz = _src_falso(
        tmp_path,
        {
            "features/x/application/ports/out/coisa_repository.py": _PORT_DE_REPOSITORIO,
            "features/x/application/ports/out/unit_of_work.py": _PORT_DA_UNIDADE,
            "features/x/application/use_cases/_aux.py": _AUXILIAR_QUE_REMOVE,
            "features/x/application/use_cases/fazer.py": (
                f"from {_PACOTE_DOS_USE_CASES}._aux import revogar\n\n\n"
                + _CABECALHO_DO_USE_CASE
                + "    def execute(self) -> None:\n"
                "        with self._unit_of_work.transaction():\n"
                "            revogar(self._coisas)\n"
                "            self._coisas.add('a')\n"
            ),
        },
    )

    assert check_layout.check_multi_write_unit_of_work(raiz) == []


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_auxiliar_que_deixou_de_escrever_mata_a_entrada_da_allowlist(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Critério da #243, segunda metade, na forma derivada.

    Não há mais entrada de tabela para envelhecer: quando o auxiliar deixa de gravar,
    a escrita some do use case, e a entrada dele na allowlist (que só existia por
    causa dela) reprova como morta.
    """
    monkeypatch.setattr(check_layout, "MULTI_WRITE_ALLOWLIST", {"Fazer": "ADR 2.6.0002 §2"})
    escreve = _src_com_auxiliar(tmp_path / "antes", _AUXILIAR_QUE_REMOVE)
    assert check_layout.check_multi_write_unit_of_work(escreve) == []

    deixou = _src_com_auxiliar(
        tmp_path / "depois",
        "def revogar(coisas: CoisaRepository) -> None:\n    coisas.find_by_id('s')\n",
    )

    assert check_layout.check_multi_write_unit_of_work(deixou) == [
        "ESCRITA MÚLTIPLA: 'Fazer' está na allowlist mas não viola mais a regra 10 — tire "
        "a entrada (allowlist morta documenta dívida já paga)."
    ]


# O piso: hoje a derivação acha exatamente um auxiliar que escreve. Mais pode entrar
# (e entra calado, contado pela regra); zero significaria a derivação quebrada.
_PISO_DE_AUXILIARES_QUE_ESCREVEM = 1


def test_regra10_a_derivacao_acha_os_auxiliares_reais_que_escrevem() -> None:
    auxiliares = check_layout.helper_writes(_SRC)

    assert len(auxiliares) >= _PISO_DE_AUXILIARES_QUE_ESCREVEM, auxiliares
    ponto_unico = auxiliares[
        "restaurant_hub.features.staff.application.use_cases._login_link.end_active_link"
    ]
    assert ponto_unico.escritas == ("IdentityGateway.revoke_login_sessions",)
    assert not ponto_unico.multipla


def test_regra10_os_auxiliares_reais_que_so_leem_ficam_fora() -> None:
    """Os que recebem port só para ler (ADR 2.6.0002, nota da issue #205) não entram."""
    auxiliares = {q.rsplit(".", 1)[1] for q in check_layout.helper_writes(_SRC)}

    for so_le in (
        "resolve_linkable_login",
        "issue_setup_token",
        "deliver_invitation",
        "settings_of",
        "neighbours_of",
        "load_for_edit",
        "run_batch",
    ):
        assert so_le not in auxiliares


def test_regra10_o_desligamento_conta_o_ponto_unico_como_a_escrita_em_identity() -> None:
    """Sem a derivação, R13 teria uma escrita só e a entrada dele na allowlist morreria."""
    achados = check_layout.scan_multi_write_use_cases(_SRC)

    for classe in ("DeactivateEmployeeUseCase", "RelinkLoginUseCase", "UnlinkLoginUseCase"):
        assert "end_active_link()" in achados[classe][2]


def test_regra10_os_use_cases_reais_cumprem_a_regra() -> None:
    """O gate nasce verde, com exatamente as duas travessias de staff na allowlist."""
    assert check_layout.check_multi_write_unit_of_work(_SRC) == []


def test_regra10_a_allowlist_nao_cresceu() -> None:
    assert set(check_layout.MULTI_WRITE_ALLOWLIST) == {
        "CreateLoginForEmployeeUseCase",
        "DeactivateEmployeeUseCase",
        # Stage 3.10 — revogam pelo ponto único antes de gravar o vínculo (ADR 3.10.0001 §5).
        "UnlinkLoginUseCase",
        "RelinkLoginUseCase",
    }


def test_regra10_cada_entrada_da_allowlist_cita_o_adr() -> None:
    sem_adr = [
        classe
        for classe, motivo in check_layout.MULTI_WRITE_ALLOWLIST.items()
        if "ADR 2.6.0002" not in motivo
    ]
    assert sem_adr == []


def test_regra10_o_classificador_bate_com_os_ports_reais() -> None:
    """A classificação por nome, fixada sobre os ports de verdade.

    Um método de repositório novo que escreva com nome de leitura (`find_*`), ou
    que leia com nome de escrita, muda este conjunto e reprova aqui — é o preço de
    classificar por convenção, cobrado no lugar onde ela pode falhar.
    """
    portas = check_layout.repository_port_names(_SRC)
    metodos = check_layout.port_methods(_SRC)

    escritas = {
        f"{porta}.{metodo}"
        for porta in portas
        for metodo in metodos[porta]
        if check_layout.is_write(porta, metodo, portas)
    }

    assert escritas == {
        "RestaurantRepository.add",
        "UnitRepository.add",
        "UserRepository.add",
        "UserRepository.set_password_hash",
        "SessionRepository.add",
        "SessionRepository.revoke",
        "SessionRepository.revoke_all_for_user",
        "SessionRepository.purge_expired",
        "PasswordSetupTokenRepository.add",
        "PasswordSetupTokenRepository.consume",
        "PasswordSetupTokenRepository.invalidate_all_for_user",
        "PasswordSetupTokenRepository.purge_expired",
        "JobFunctionRepository.add",
        "JobFunctionRepository.update",
        "JobFunctionRepository.update_enablement",
        "JobFunctionRepository.delete",
        "EmployeeRepository.add",
        "EmployeeRepository.update",
        "EmployeeRepository.link_login",
        "EmployeeRepository.unlink_login",
        "EmployeeRepository.relink_login",
        "EmployeeRepository.deactivate",
        "EmployeeRepository.reactivate",
        "EmployeeRepository.delete",
        "ScheduleRepository.add",
        "ScheduleRepository.save",
    }
    assert check_layout.is_write("IdentityGateway", "provision_employee_login", portas)
    assert check_layout.is_write("IdentityGateway", "revoke_login_sessions", portas)
    assert not check_layout.is_write("IdentityGateway", "send_login_invitation", portas)
    assert not check_layout.is_write("IdentityGateway", "is_employee_login", portas)


def test_regra10_tem_ancora_de_cobertura() -> None:
    assert check_layout.USE_CASES_ANCHOR in check_layout.coverage_anchors()


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_metodo_de_gateway_declarado_que_nao_existe_reprova(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        check_layout, "GATEWAY_WRITE_METHODS", {"OutroGateway": frozenset({"gravar"})}
    )

    violacoes = check_layout.check_multi_write_unit_of_work(
        _src_com_use_case(tmp_path, _DUAS_DENTRO)
    )

    assert violacoes == [
        "ESCRITA MÚLTIPLA: GATEWAY_WRITE_METHODS declara 'OutroGateway.gravar', que não "
        "existe em ports/out — a classificação de escrita está desatualizada."
    ]


@pytest.mark.usefixtures("regra10_isolada")
def test_regra10_construtor_com_atribuicao_anotada_tambem_e_lido(tmp_path: pathlib.Path) -> None:
    """`self._coisas: CoisaRepository = coisas` não pode esconder as escritas da classe."""
    cabecalho = _CABECALHO_DO_USE_CASE.replace(
        "        self._coisas = coisas\n", "        self._coisas: CoisaRepository = coisas\n"
    )
    raiz = _src_falso(
        tmp_path,
        {
            "features/x/application/ports/out/coisa_repository.py": _PORT_DE_REPOSITORIO,
            "features/x/application/ports/out/unit_of_work.py": _PORT_DA_UNIDADE,
            "features/x/application/use_cases/fazer.py": cabecalho
            + "    def execute(self) -> None:\n"
            "        self._coisas.add('a')\n"
            "        self._coisas.remove('b')\n",
        },
    )

    assert len(check_layout.check_multi_write_unit_of_work(raiz)) == 1


# Todo port de saída que não é repositório, com a classificação de cada método
# (`True` grava, `False` não grava). Medido em `develop` `0b57697` (issue #260). Port
# novo entra aqui **e** em `GATEWAY_WRITE_METHODS` (os métodos que gravam) ou em
# `NON_WRITING_PORTS` (com o motivo), no script; método novo num port daqui também
# reprova até ser classificado — inclusive num port que hoje não grava.
_GRAVA = True
_NAO_GRAVA = False
_PORTS_FORA_DE_REPOSITORIO: dict[tuple[str, str], dict[str, bool]] = {
    ("features/identity/application/ports/out/action_authorizer.py", "ActionAuthorizer"): {
        "execute": _NAO_GRAVA,
    },
    ("features/identity/application/ports/out/password_hasher.py", "PasswordHasher"): {
        "hash": _NAO_GRAVA,
        "verify": _NAO_GRAVA,
        "dummy_hash": _NAO_GRAVA,
        "unusable_hash": _NAO_GRAVA,
    },
    ("features/identity/application/ports/out/setup_token_issuer.py", "SetupTokenIssuer"): {
        "issue": _NAO_GRAVA,
        "fingerprint": _NAO_GRAVA,
    },
    ("features/identity/application/ports/out/token_issuer.py", "TokenIssuer"): {
        "issue_access_token": _NAO_GRAVA,
        "issue_refresh_token": _NAO_GRAVA,
        "fingerprint": _NAO_GRAVA,
        "decode_access_token": _NAO_GRAVA,
    },
    ("features/identity/application/ports/out/unit_of_work.py", "UnitOfWork"): {
        "transaction": _NAO_GRAVA,
    },
    ("features/scheduling/application/ports/out/access_guard.py", "AccessGuard"): {
        "authenticate": _NAO_GRAVA,
        "authorize": _NAO_GRAVA,
    },
    ("features/scheduling/application/ports/out/staff_read_port.py", "StaffReadPort"): {
        "list_active_members": _NAO_GRAVA,
        "list_members": _NAO_GRAVA,
        "list_members_of_user": _NAO_GRAVA,
        "list_job_functions": _NAO_GRAVA,
        "list_unit_job_functions": _NAO_GRAVA,
    },
    ("features/staff/application/ports/out/access_guard.py", "AccessGuard"): {
        "authenticate": _NAO_GRAVA,
        "authorize": _NAO_GRAVA,
    },
    ("features/staff/application/ports/out/identity_gateway.py", "IdentityGateway"): {
        "provision_employee_login": _GRAVA,
        "revoke_login_sessions": _GRAVA,
        "send_login_invitation": _NAO_GRAVA,
        # Leitura (L-IG5, Stage 3.8): fica fora de `GATEWAY_WRITE_METHODS`.
        "is_employee_login": _NAO_GRAVA,
        # Leitura (L-IG6, Stage 3.10): fica fora de `GATEWAY_WRITE_METHODS`.
        "find_login_by_email": _NAO_GRAVA,
    },
    ("shared/application/ports/out/clock.py", "Clock"): {"now": _NAO_GRAVA},
    # E-mail depois do commit: fora da contagem por propósito (ADR 2.6.0002 §3).
    ("shared/application/ports/out/email_sender.py", "EmailSender"): {"send": _NAO_GRAVA},
    ("shared/application/ports/out/id_generator.py", "IdGenerator"): {"next_id": _NAO_GRAVA},
}


def test_regra10_todo_metodo_dos_gateways_declarados_esta_classificado() -> None:
    """Todo método de todo port de saída fora de repositório está classificado aqui.

    Para repositório, a classificação sai do nome; para o resto, de
    `GATEWAY_WRITE_METHODS`. Até a issue #260 este pino só cobria `IdentityGateway`;
    agora cobre o conjunto, derivado da árvore. Sem ele, um `unlink_login` novo em
    `IdentityGateway` — ou um método que grave num port que hoje só lê — seria lido
    como leitura em silêncio.
    """
    portas = check_layout.non_repository_ports(_SRC)
    repositorios = check_layout.repository_port_names(_SRC)

    assert {chave: set(metodos) for chave, metodos in portas.items()} == {
        chave: set(metodos) for chave, metodos in _PORTS_FORA_DE_REPOSITORIO.items()
    }
    classificacao = {
        chave: {m: check_layout.is_write(chave[1], m, repositorios) for m in metodos}
        for chave, metodos in portas.items()
    }
    assert classificacao == _PORTS_FORA_DE_REPOSITORIO


# Os 12 da medição da #260. Piso, não igualdade — o pino exato é o dicionário acima.
_MINIMO_DE_PORTS_FORA_DE_REPOSITORIO = 12


def test_regra10_os_ports_reais_estao_todos_classificados() -> None:
    """Sobre `src/`: nenhum port sem classificação, nenhuma entrada morta.

    O piso de contagem impede o verde vazio: se a âncora de `ports/out/` mudasse e a
    descoberta voltasse vazia, a lista de violações também viria vazia.
    """
    assert len(check_layout.non_repository_ports(_SRC)) >= _MINIMO_DE_PORTS_FORA_DE_REPOSITORIO
    assert check_layout.check_out_port_classification(_SRC) == []


def test_regra10_cada_port_que_nao_grava_diz_o_motivo() -> None:
    sem_motivo = [nome for nome, motivo in check_layout.NON_WRITING_PORTS.items() if not motivo]
    assert sem_motivo == []
    assert "ADR 2.6.0002 §3" in check_layout.NON_WRITING_PORTS["EmailSender"]


_PORT_NOVO = (
    "from typing import Protocol\n\n\n"
    "class NovoGateway(Protocol):\n"
    "    def gravar_no_outro_bc(self, x: str) -> None: ...\n"
)


def _src_com_ports(tmp_path: pathlib.Path, extras: dict[str, str]) -> pathlib.Path:
    return _src_falso(
        tmp_path,
        {
            "features/x/application/ports/out/coisa_repository.py": _PORT_DE_REPOSITORIO,
            "features/x/application/ports/out/unit_of_work.py": _PORT_DA_UNIDADE,
            **extras,
        },
    )


@pytest.fixture
def classificacao_sintetica(monkeypatch: pytest.MonkeyPatch) -> None:
    """Só a unidade classificada — a árvore sintética não tem os ports do `src/` real."""
    monkeypatch.setattr(check_layout, "GATEWAY_WRITE_METHODS", {})
    monkeypatch.setattr(check_layout, "NON_WRITING_PORTS", {"UnitOfWork": "a unidade"})


@pytest.mark.parametrize(
    "caminho",
    [
        pytest.param("features/x/application/ports/out/novo_gateway.py", id="feature"),
        pytest.param("shared/application/ports/out/novo_gateway.py", id="shared"),
    ],
)
@pytest.mark.usefixtures("classificacao_sintetica")
def test_regra10_port_novo_nao_classificado_reprova(tmp_path: pathlib.Path, caminho: str) -> None:
    """Critério da #260: port sintético novo, nem repositório nem classificado, reprova."""
    raiz = _src_com_ports(tmp_path, {caminho: _PORT_NOVO})

    assert check_layout.check_out_port_classification(raiz) == [
        f"ESCRITA MÚLTIPLA: {caminho} — o port de saída 'NovoGateway' não está "
        "classificado. Ponha os métodos que gravam em GATEWAY_WRITE_METHODS, ou "
        "declare-o em NON_WRITING_PORTS com o motivo (issue #260)."
    ]


@pytest.mark.parametrize(
    "base",
    [
        pytest.param("typing.Protocol", id="protocol-qualificado"),
        pytest.param("Protocol[T]", id="protocol-generico"),
        pytest.param("ABC", id="abc"),
    ],
)
@pytest.mark.usefixtures("classificacao_sintetica")
def test_regra10_port_novo_e_achado_em_cada_forma_de_declaracao(
    tmp_path: pathlib.Path, base: str
) -> None:
    port = f"class NovoGateway({base}):\n    def gravar(self) -> None: ...\n"
    raiz = _src_com_ports(tmp_path, {"features/x/application/ports/out/novo.py": port})

    violacoes = check_layout.check_out_port_classification(raiz)

    assert len(violacoes) == 1, violacoes
    assert "'NovoGateway' não está classificado" in violacoes[0]


_DECLARA_PROTOCOLO = (
    "from typing import Protocol\n\n\nclass Base(Protocol):\n    def ler(self) -> int: ...\n"
)


@pytest.mark.parametrize(
    "arquivos",
    [
        pytest.param(
            {
                "features/x/application/ports/out/novo.py": (
                    "from typing import Protocol as P\n\n\n"
                    "class NovoGateway(P):\n    def gravar(self) -> None: ...\n"
                )
            },
            id="protocol-com-apelido",
        ),
        pytest.param(
            {
                "features/x/application/ports/out/novo.py": (
                    "from abc import ABCMeta, abstractmethod\n\n\n"
                    "class NovoGateway(metaclass=ABCMeta):\n"
                    "    @abstractmethod\n    def gravar(self) -> None: ...\n"
                )
            },
            id="metaclass-abcmeta",
        ),
        pytest.param(
            {
                "features/x/application/ports/out/novo.py": (
                    "from abc import ABCMeta as M\n\n\n"
                    "class NovoGateway(metaclass=M):\n    def gravar(self) -> None: ...\n"
                )
            },
            id="metaclass-com-apelido",
        ),
        pytest.param(
            {"features/x/application/ports/out/sub/novo.py": _PORT_NOVO},
            id="subpasta",
        ),
        pytest.param(
            {"features/x/application/ports/out/__init__.py": _PORT_NOVO},
            id="init",
        ),
        pytest.param(
            {
                "features/x/application/ports/out/novo.py": (
                    "from .base import Base\n\n\n"
                    "class NovoGateway(Base):\n    def gravar(self) -> None: ...\n"
                ),
            },
            id="herda-de-port-sem-protocol",
        ),
        pytest.param(
            {
                "features/x/application/ports/out/novo.py": (
                    "from .coisa_repository import CoisaRepository\n\n\n"
                    "class NovoGateway(CoisaRepository):\n    def gravar(self) -> None: ...\n"
                )
            },
            id="herda-de-repositorio",
        ),
    ],
)
@pytest.mark.usefixtures("classificacao_sintetica")
def test_regra10_port_novo_escondido_tambem_e_achado(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, arquivos: dict[str, str]
) -> None:
    """Formas que a auditoria do PR #263 plantou: as três primeiras e a herança escapavam."""
    monkeypatch.setattr(
        check_layout, "NON_WRITING_PORTS", {"UnitOfWork": "a unidade", "Base": "só lê"}
    )
    # `Base` (classificado) fica em toda árvore: é o port de que um dos casos herda.
    raiz = _src_com_ports(
        tmp_path, {"features/x/application/ports/out/base.py": _DECLARA_PROTOCOLO, **arquivos}
    )

    violacoes = check_layout.check_out_port_classification(raiz)

    assert len(violacoes) == 1, violacoes
    assert "'NovoGateway' não está classificado" in violacoes[0]


def test_regra10_homonimos_tem_cada_um_o_seu_pino(tmp_path: pathlib.Path) -> None:
    """Os dois `AccessGuard` partilham a classificação no script, não o pino de métodos.

    Um método novo num deles não muda nada no script (o nome já está classificado),
    mas muda a chave (arquivo, port) dele em `non_repository_ports` — é o que faz
    `test_regra10_todo_metodo_dos_gateways_declarados_esta_classificado` reprovar.
    """
    guarda = (
        "from typing import Protocol\n\n\n"
        "class Guard(Protocol):\n    def authorize(self) -> None: ...\n"
    )
    raiz = _src_falso(
        tmp_path,
        {
            "features/a/application/ports/out/guard.py": guarda,
            "features/b/application/ports/out/guard.py": (
                guarda + "    def provisionar(self) -> None: ...\n"
            ),
        },
    )

    assert check_layout.non_repository_ports(raiz) == {
        ("features/a/application/ports/out/guard.py", "Guard"): frozenset({"authorize"}),
        ("features/b/application/ports/out/guard.py", "Guard"): frozenset(
            {"authorize", "provisionar"}
        ),
    }


@pytest.mark.parametrize(
    ("tabela", "valor"),
    [
        pytest.param(
            "GATEWAY_WRITE_METHODS",
            {"NovoGateway": frozenset({"gravar_no_outro_bc"})},
            id="grava",
        ),
        pytest.param(
            "NON_WRITING_PORTS",
            {"UnitOfWork": "a unidade", "NovoGateway": "só lê"},
            id="nao-grava",
        ),
    ],
)
@pytest.mark.usefixtures("classificacao_sintetica")
def test_regra10_port_novo_classificado_passa(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, tabela: str, valor: object
) -> None:
    monkeypatch.setattr(check_layout, tabela, valor)
    raiz = _src_com_ports(
        tmp_path, {"features/x/application/ports/out/novo_gateway.py": _PORT_NOVO}
    )

    assert check_layout.check_out_port_classification(raiz) == []


@pytest.mark.usefixtures("classificacao_sintetica")
def test_regra10_o_que_nao_e_port_fora_de_repositorio_nao_e_cobrado(
    tmp_path: pathlib.Path,
) -> None:
    """Dataclass e enum de `ports/out/`, o repositório e o `Protocol` fora de `ports/out/`."""
    raiz = _src_com_ports(
        tmp_path,
        {
            "features/x/application/ports/out/novo_gateway.py": (
                "from dataclasses import dataclass\nfrom enum import StrEnum\n\n\n"
                "@dataclass(frozen=True)\nclass Retorno:\n    x: str\n\n\n"
                "class Modo(StrEnum):\n    A = 'a'\n"
            ),
            "features/x/application/ports/out/outra_repository.py": _PORT_NOVO,
            "features/x/application/use_cases/fazer.py": _PORT_NOVO,
        },
    )

    assert check_layout.check_out_port_classification(raiz) == []


@pytest.mark.parametrize(
    ("tabela", "valor", "esperado"),
    [
        pytest.param(
            "GATEWAY_WRITE_METHODS",
            {"SumidoGateway": frozenset({"gravar"})},
            "GATEWAY_WRITE_METHODS declara 'SumidoGateway'",
            id="gateway-que-nao-existe",
        ),
        pytest.param(
            "GATEWAY_WRITE_METHODS",
            {"CoisaRepository": frozenset({"add"})},
            "GATEWAY_WRITE_METHODS declara 'CoisaRepository'",
            id="repositorio-declarado-como-gateway",
        ),
        pytest.param(
            "NON_WRITING_PORTS",
            {"UnitOfWork": "a unidade", "SumidoPort": "só lê"},
            "NON_WRITING_PORTS declara 'SumidoPort'",
            id="nao-grava-que-nao-existe",
        ),
    ],
)
@pytest.mark.usefixtures("classificacao_sintetica")
def test_regra10_classificacao_morta_reprova(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    tabela: str,
    valor: object,
    esperado: str,
) -> None:
    monkeypatch.setattr(check_layout, tabela, valor)

    violacoes = check_layout.check_out_port_classification(_src_com_ports(tmp_path, {}))

    assert len(violacoes) == 1, violacoes
    assert esperado in violacoes[0]
    assert "classificação morta" in violacoes[0]


@pytest.mark.usefixtures("classificacao_sintetica")
def test_regra10_port_nos_dois_lados_reprova(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check_layout, "GATEWAY_WRITE_METHODS", {"UnitOfWork": frozenset()})

    assert check_layout.check_out_port_classification(_src_com_ports(tmp_path, {})) == [
        "ESCRITA MÚLTIPLA: 'UnitOfWork' está em GATEWAY_WRITE_METHODS e em "
        "NON_WRITING_PORTS — um port grava ou não grava."
    ]


def test_regra10_a_classificacao_dos_ports_esta_ligada_ao_main(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A checagem só protege o build se o script a executa — é o `main()` que roda no CI."""
    raiz = _src_falso(tmp_path, {"features/x/application/ports/out/novo_gateway.py": _PORT_NOVO})
    monkeypatch.setattr(sys, "argv", ["check_layout.py", "--src", str(raiz)])

    assert check_layout.main() == 1
    assert "o port de saída 'NovoGateway' não está classificado" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Regra 11 — a hierarquia de exceções não fala de protocolo (Stage 3.9, CA6)
# ---------------------------------------------------------------------------


# Os módulos da hierarquia em `src/` hoje (Stage 3.9): 12 — três em `shared` e três
# por BC, contando os `__init__.py` de `exceptions/`. Piso, não igualdade — BC novo soma.
_MINIMO_DE_ARQUIVOS_DA_HIERARQUIA = 12


def test_regra11_os_modulos_reais_da_hierarquia_nao_falam_de_protocolo() -> None:
    """Verde sobre `src/` — e sobre um universo que não encolheu sem ninguém ver."""
    assert len(check_layout.error_hierarchy_files(_SRC)) >= _MINIMO_DE_ARQUIVOS_DA_HIERARQUIA
    assert check_layout.check_error_hierarchy_protocol(_SRC) == []


def test_regra11_esta_ligada_ao_main(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A regra só protege o build se o script a executa — é o `main()` que roda no CI."""
    raiz = _src_falso(tmp_path, {"features/x/application/errors.py": '"""vira 404."""\n'})
    monkeypatch.setattr(sys, "argv", ["check_layout.py", "--src", str(raiz)])

    assert check_layout.main() == 1
    assert "PROTOCOLO:" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("caminho", "termo"),
    [
        ("shared/domain/exceptions/base.py", "convertida em HTTP"),
        ("shared/application/errors.py", "o FastAPI registra"),
        ("features/x/domain/exceptions/errors.py", "o lookup do Starlette"),
        ("features/x/domain/exceptions/errors.py", "o error handler alcança"),
        ("features/x/application/errors.py", "dois handlers"),
        ("features/x/application/errors.py", "a MRO fica"),
        ("features/x/application/errors.py", "type(exc).__mro__"),
        ("features/x/application/errors.py", "vira 404"),
        ("features/x/application/errors.py", "e não 500"),
        ("features/x/domain/exceptions/errors.py", "resposta 4xx"),
        ("features/x/application/errors.py", "via app.exception_handler"),
        ("features/x/application/errors.py", "levanta HTTPException"),
        ("features/x/application/errors.py", "como Http404"),
        ("features/x/application/errors.py", "status.HTTP_404_NOT_FOUND"),
        ("features/x/application/errors.py", "a method-resolution order"),
        ("features/x/application/errors.py", "a ordem de resolução de métodos"),
        # Sem distinção de caixa (concept 3.9 §5.5 lista termos, não grafias).
        ("features/x/application/errors.py", "o Handler do BC"),
        ("features/x/application/errors.py", "via http"),
        ("features/x/application/errors.py", "a Mro"),
        ("features/x/application/errors.py", "o fastapi"),
    ],
)
def test_regra11_cada_termo_do_vocabulario_reprova(
    tmp_path: pathlib.Path, caminho: str, termo: str
) -> None:
    """Um violador plantado **por termo**, em docstring — onde a inversão morava."""
    raiz = _src_falso(tmp_path, {caminho: f'"""Erro de exemplo — {termo}."""\n'})

    violacoes = check_layout.check_error_hierarchy_protocol(raiz)

    assert len(violacoes) == 1, violacoes
    assert caminho in violacoes[0].replace("\\", "/")


def test_regra11_comentario_tambem_reprova(tmp_path: pathlib.Path) -> None:
    raiz = _src_falso(
        tmp_path,
        {"features/x/domain/exceptions/errors.py": "class XError(Exception):\n    pass  # 422\n"},
    )

    assert len(check_layout.check_error_hierarchy_protocol(raiz)) == 1


def test_regra11_numero_e_palavra_fora_do_vocabulario_nao_reprovam(tmp_path: pathlib.Path) -> None:
    """O caso negativo: o vocabulário é estreito de propósito."""
    raiz = _src_falso(
        tmp_path,
        {
            "features/x/domain/exceptions/errors.py": (
                '"""ADR 2.3.0003, regra R13, 600 minutos, status da escala, bordas inclusivas,\n'
                'versão 4.5 e §4.1 — nada disto é transporte."""\n'
            )
        },
    )

    assert check_layout.check_error_hierarchy_protocol(raiz) == []


def test_regra11_arquivo_fora_da_hierarquia_nao_e_varrido(tmp_path: pathlib.Path) -> None:
    """A regra mira os módulos que definem a hierarquia (concept 3.9 D6), não o domínio."""
    raiz = _src_falso(
        tmp_path,
        {"features/x/domain/value_objects/email.py": '"""Evita um 500 em POST /users."""\n'},
    )

    assert check_layout.check_error_hierarchy_protocol(raiz) == []
