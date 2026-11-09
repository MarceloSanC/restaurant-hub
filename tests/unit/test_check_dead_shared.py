"""O detector de código morto em `shared/`, contra violadores plantados.

Gate 7 da issue #45. O sujeito é `scripts/check_dead_shared.py`; o mesmo
raciocínio de localização de `test_check_layout.py` vale aqui — a regra é do
repositório, não de um bounded context.

**A propriedade que distingue este detector de um `grep`.** `Pagination` era
citado em prosa em `docs/LAYOUT.md`, em dois `concept.md` e em três ADRs, e
usado em zero módulos. Um detector textual teria contado cada citação como uso e
declarado o símbolo vivo por seis Stages — que é precisamente o tempo que ele
durou. Por isso a varredura é `ast` e ignora docstring, e por isso há um teste
plantado só para essa diferença: sem ele, trocar a implementação por `in texto`
deixaria a suíte verde.

**A lista explícita dos nomes de hoje, mais a asserção de que ela cobre a
varredura.** Derivar a lista da varredura a faria concordar com qualquer
resultado, inclusive com o de um detector quebrado que devolvesse conjunto
vazio. Escrita à mão, ela envelhece — então a segunda asserção a cobra contra o
que existe em `src/`. É o par do
`tests/unit/features/staff/adapters/test_composition_root_staff.py`.
"""

import importlib.util
import pathlib
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src" / "restaurant_hub"
_SCRIPT = _REPO_ROOT / "scripts" / "check_dead_shared.py"

# O que `shared/domain/` e `shared/application/` expõem hoje. Cada um tem
# consumidor real, e é isso que a asserção seguinte cobra:
#
# - `DomainError` — raiz da hierarquia de erro de domínio dos BCs;
# - `ApplicationError` — raiz das falhas que não são regra de negócio, de volta na
#   Stage 3.9 com uma subclasse-raiz por BC (ADR 3.9.0001);
# - `Clock`/`IdGenerator` — ports consumidos por use case de identity e staff;
# - `EmailSender`/`EmailMessage` — port promovido na 2.5 com o segundo
#   consumidor já nomeado (Stage 4.6), o critério do ADR 2.5.0001.
_NOMES_PUBLICOS_DE_SHARED = frozenset(
    {
        "ApplicationError",
        "Clock",
        "DomainError",
        "EmailMessage",
        "EmailSender",
        "IdGenerator",
    }
)


def _carregar_script() -> types.ModuleType:
    """Importa `scripts/check_dead_shared.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_dead_shared", _SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


check_dead_shared = _carregar_script()


def _src_falso(tmp_path: pathlib.Path, arquivos: dict[str, str]) -> pathlib.Path:
    """Monta uma árvore mínima de `src/restaurant_hub/` em disco temporário."""
    raiz = tmp_path / "src" / "restaurant_hub"
    for caminho, conteudo in arquivos.items():
        destino = raiz / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    return raiz


def test_gate7_nenhum_nome_publico_de_shared_esta_sem_uso() -> None:
    """O critério de pronto, medido contra o `src/` real.

    Antes da remoção, `Pagination` e `ApplicationError` apareciam aqui — o
    primeiro levantando `ValueError` cru, que não é `DomainError` e produziria
    500 no dia em que o HTTP o alcançasse.
    """
    mortos = check_dead_shared.nomes_mortos(_SRC)

    assert mortos == [], "\n".join(mortos)


def test_gate7_a_lista_deste_teste_cobre_o_que_shared_declara() -> None:
    """Fecha o buraco da lista escrita à mão: ela pode envelhecer.

    A lista existe para que um detector quebrado — um que devolvesse conjunto
    vazio — não passe despercebido; derivá-la da varredura a faria concordar com
    qualquer resultado. O preço é envelhecer, e esta asserção é o que o cobra:
    um nome público novo em `shared/` reprova aqui até ser declarado, o que
    obriga quem o promoveu a nomear o segundo consumidor.
    """
    declarados = set(check_dead_shared.declaracoes(_SRC))

    assert declarados == set(_NOMES_PUBLICOS_DE_SHARED), (
        f"só na varredura: {sorted(declarados - _NOMES_PUBLICOS_DE_SHARED)}; "
        f"só na lista: {sorted(_NOMES_PUBLICOS_DE_SHARED - declarados)}"
    )


def test_gate7_um_value_object_sem_consumidor_reprova(tmp_path: pathlib.Path) -> None:
    """Violador plantado: `Pagination`, reconstruído como era.

    Guarda que nunca viu um positivo não é guarda. Este é o caso exato que a
    auditoria encontrou vivo — um value object em `shared/domain/`, promovido
    pelo template, sem um único módulo que o nomeie.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "shared/domain/value_objects/pagination.py": ("class Pagination:\n    page: int = 1\n"),
            "features/pedidos/application/use_cases/listar.py": "VALOR = 1\n",
        },
    )

    mortos = check_dead_shared.nomes_mortos(raiz)

    assert len(mortos) == 1, mortos
    assert "Pagination" in mortos[0]


def test_gate7_citacao_em_docstring_nao_conta_como_uso(tmp_path: pathlib.Path) -> None:
    """A diferença entre este detector e um `grep`, como asserção.

    `Pagination` era citado em prosa no `LAYOUT.md`, em dois `concept.md` e em
    três ADRs. Um detector textual teria lido cada menção como uso e declarado o
    símbolo vivo — exatamente o que aconteceu por seis Stages, sem detector
    nenhum. Sem este teste, trocar a varredura `ast` por `nome in texto`
    deixaria a suíte verde e o gate inútil.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "shared/domain/value_objects/pagination.py": "class Pagination:\n    pass\n",
            "features/pedidos/application/use_cases/listar.py": (
                '"""Listagem — no futuro paginada com `Pagination` (shared)."""\n'
            ),
        },
    )

    mortos = check_dead_shared.nomes_mortos(raiz)

    assert len(mortos) == 1, mortos
    assert "Pagination" in mortos[0]


def test_gate7_um_uso_real_absolve(tmp_path: pathlib.Path) -> None:
    """A outra direção: o detector não acusa quem tem consumidor.

    Sem este caso, uma varredura que devolvesse **tudo** como morto passaria nos
    três testes acima. Falso positivo num gate é pior que falso negativo: ele
    treina quem o vê a afrouxar a regra.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "shared/domain/value_objects/pagination.py": "class Pagination:\n    pass\n",
            "features/pedidos/application/use_cases/listar.py": (
                "from restaurant_hub.shared.domain.value_objects.pagination import Pagination\n"
                "\n"
                "def listar(p: Pagination) -> None: ...\n"
            ),
        },
    )

    assert check_dead_shared.nomes_mortos(raiz) == []


def test_gate7_a_auto_mencao_do_modulo_declarante_nao_absolve(tmp_path: pathlib.Path) -> None:
    """A armadilha que faria o gate ser vacuamente verde.

    Toda declaração se auto-menciona: `class Pagination` põe `Pagination` na
    varredura, e um `__post_init__` que a nomeie no `repr` põe outra vez. Contar
    o módulo declarante faria **todo** nome público parecer usado, e o script
    passaria a devolver lista vazia para sempre — verde por não ter olhado.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "shared/domain/value_objects/pagination.py": (
                "class Pagination:\n"
                "    def __repr__(self) -> str:\n"
                "        return f'{Pagination.__name__}()'\n"
            ),
            "features/pedidos/application/use_cases/listar.py": "VALOR = 1\n",
        },
    )

    mortos = check_dead_shared.nomes_mortos(raiz)

    assert len(mortos) == 1, mortos
    assert "Pagination" in mortos[0]


def test_gate7_nome_privado_nao_e_superficie_publica(tmp_path: pathlib.Path) -> None:
    """`_helper` de módulo é detalhe interno, e cobrá-lo seria ruído.

    A regra é sobre o que `shared/` **oferece** às features. Um privado sem uso
    é dívida do arquivo que o contém — visível a quem o abre, e fora do modo de
    falha que este gate fecha.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "shared/domain/value_objects/pagination.py": (
                "def _normalizar(p: int) -> int:\n    return p\n"
            ),
            "features/pedidos/application/use_cases/listar.py": "VALOR = 1\n",
        },
    )

    assert check_dead_shared.nomes_mortos(raiz) == []


def test_gate7_shared_infrastructure_fica_de_fora(tmp_path: pathlib.Path) -> None:
    """A fronteira do gate, declarada como asserção e não só em prosa.

    `SystemClock`, `Uuid4Generator` e `ConsoleSender` são alcançados por
    injeção, e hoje só o `composition_root` os nomeia. Incluí-los produziria
    falso positivo previsível no dia em que a configuração passar a escolher o
    adapter por string — e um gate que grita sem motivo é um gate que alguém
    desliga.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "shared/infrastructure/clock/system_clock.py": "class SystemClock:\n    pass\n",
            "features/pedidos/application/use_cases/listar.py": "VALOR = 1\n",
        },
    )

    assert check_dead_shared.nomes_mortos(raiz) == []


def test_gate7_constantes_de_modulo_sao_superficie_publica(tmp_path: pathlib.Path) -> None:
    """`X = ...` e `Y: int = ...` em `shared/` são contrato tanto quanto uma classe.

    O alvo atributo (`obj.attr = ...`) e o privado (`_Z = ...`) não são nome de
    módulo, e ficam fora.
    """
    raiz = _src_falso(
        tmp_path,
        {
            "shared/domain/constantes.py": (
                "LIMITE = 10\nTETO: int = 20\n_PRIVADO = 1\n_ANOTADO: int = 2\n"
                "import types\ntypes.ALVO = 3\n"
            ),
            "features/pedidos/application/use_cases/listar.py": "VALOR = 1\n",
        },
    )

    mortos = check_dead_shared.nomes_mortos(raiz)

    assert len(mortos) == len(["LIMITE", "TETO"]), mortos
    assert any("'LIMITE'" in m for m in mortos)
    assert any("'TETO'" in m for m in mortos)


def test_gate7_arquivo_nao_analisavel_e_pulado(tmp_path: pathlib.Path) -> None:
    """Python com erro de sintaxe não derruba o detector, nem declara nem usa nome."""
    raiz = _src_falso(
        tmp_path,
        {
            "shared/domain/quebrado.py": "class Quebrado(:\n",
            "features/pedidos/application/use_cases/quebrado.py": "def (\n",
            "features/pedidos/application/use_cases/listar.py": "VALOR = 1\n",
        },
    )

    assert check_dead_shared.parse(raiz / "shared" / "domain" / "quebrado.py") is None
    assert check_dead_shared.nomes_mortos(raiz) == []


def _rodar_main(monkeypatch: pytest.MonkeyPatch, src: pathlib.Path) -> int:
    monkeypatch.setattr("sys.argv", ["check_dead_shared.py", "--src", str(src)])
    return int(check_dead_shared.main())


def test_gate7_main_sem_nome_morto_sai_zero(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raiz = _src_falso(
        tmp_path,
        {
            "shared/domain/erro.py": "class Erro(Exception):\n    pass\n",
            "features/pedidos/domain/x.py": "from restaurant_hub.shared.domain.erro import Erro\n",
        },
    )

    assert _rodar_main(monkeypatch, raiz) == 0
    assert "nenhum nome público de shared/ sem uso" in capsys.readouterr().out


def test_gate7_main_com_nome_morto_sai_um_e_lista_no_stderr(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raiz = _src_falso(tmp_path, {"shared/domain/vo.py": "class Pagination:\n    pass\n"})

    assert _rodar_main(monkeypatch, raiz) == 1
    erro = capsys.readouterr().err
    assert "1 nome(s) público(s) sem uso" in erro
    assert "MORTO:" in erro
    assert "'Pagination'" in erro


def test_gate7_main_src_inexistente_sai_um(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Caminho errado reprova em vez de passar vazio — o gate falha fechado."""
    assert _rodar_main(monkeypatch, tmp_path / "nao-existe") == 1
    assert "ERRO: diretório não encontrado" in capsys.readouterr().err
