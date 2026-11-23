"""Conduta e concorrência — os comportamentos que asserção sobre estado final NÃO distingue.

**Esta é a Task que fecha o finding herdado nº 4 ("a suíte travava resultado,
não conduta").** Todo teste das Tasks 06 e 07 pergunta "o que ficou gravado?", e
para cada peça verificada aqui existe uma implementação **sem** ela que responde
exatamente o mesmo — e que portanto passa nas outras duas suítes inteiras:

| Peça omitida | O que muda no estado final | Onde morre |
|---|---|---|
| `COLLATE "C"` no `ORDER BY` | **nada** nesta imagem (musl) | CA10b, aqui |
| `REPEATABLE READ` na leitura de agregado | nada, sem escrita concorrente | CA17b, aqui |
| `FOR UPDATE` no lookup de `update` | nada, sem edição concorrente | CA6b, aqui |
| filhas por diferença (§5.20) | nada — o estado final é idêntico | regressão de deadlock, aqui |
| tradução **por operação** (mapa global) | nada nos caminhos comuns | CA8b/CA8c, aqui |
| `user_id` fora do `SET` do `update` (#68) | nada, sem vínculo concorrente | #68, aqui |
| `FOR UPDATE` no lookup de `link_login` (#68) | nada, sem vínculo concorrente | #68, aqui |
| `FOR UPDATE` + guarda do vínculo no `delete` (#108) | nada, sem vínculo concorrente | #108, aqui |
| `tenant_id` no `WHERE` do `DELETE` (#108) | nada, o lookup sob lock já o conferiu | #108, aqui |
| condição sob `FOR NO KEY UPDATE` em `update_enablement` (#206) | nada, sem corrida | #206, aqui |
| snapshot único nas leituras de função (#225) | nada, sem alteração concorrente | #225, aqui |
| condição sob lock em `update` e `delete` de função (#207) | nada, sem corrida | #207, aqui |

Por isso cada teste daqui **reproduz** o comportamento em vez de observar o
resultado: prende um lock de verdade, força um entrelace de verdade, lê o SQL
que o adapter mandou de verdade.

**Nenhum teste deste arquivo sincroniza por relógio.** Não há `sleep` como
mecanismo: o entrelace vem de `after_cursor_execute` (que dispara **entre**
statements, de forma determinística) e de `threading.Barrier(2)`; o que
converteria um bloqueio indefinido em pendura é convertido em falha rápida por
`lock_timeout`. Teste de concorrência sincronizado por relógio é teste que passa
por sorte — e que, quando falha no CI, é lido como flakiness em vez de como o
achado que é.

**Sobre os `Engine` dedicados.** Cada teste daqui cria os seus, e não usa o
`engine` de sessão, por duas razões que são a mesma: `lock_timeout` vive na
conexão, e listener de evento vive no `Engine`. Postos no `Engine` de sessão, os
dois **vazariam** — pelo pool — para todo teste seguinte da suíte, e o sintoma
seria falha em outro arquivo.
"""

import re
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal

import pytest
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import IntegrityError, OperationalError

from restaurant_hub.features.staff.adapters.out.postgres.employee_repository import (
    PostgresEmployeeRepository,
)
from restaurant_hub.features.staff.adapters.out.postgres.integrity_errors import (
    ON_DELETE_JOB_FUNCTION,
    ON_WRITE_EMPLOYEE,
    constraint_name,
    translate,
)
from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from restaurant_hub.features.staff.application.dtos.commands import (
    DeleteEmployeeCommand,
    RenameEmployeeCommand,
    SetJobFunctionUnitsCommand,
)
from restaurant_hub.features.staff.application.errors import (
    EmployeeAlreadyExistsError,
    EmployeeHasLoginError,
    JobFunctionEnablementChangedError,
    JobFunctionInUseError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_JOB_FUNCTIONS,
)
from restaurant_hub.features.staff.application.use_cases.delete_employee import (
    DeleteEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_employee import (
    RenameEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.set_job_function_units import (
    SetJobFunctionUnitsUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeAlreadyHasLoginError,
    EmployeeLoginChangedError,
    InvalidUnitEnablementError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_access_guard import InMemoryAccessGuard
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard

pytestmark = [pytest.mark.integration]

_A = TenantId("tenant-a")
_U1 = UnitId("u1")
_E1 = EmployeeId("e1")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")

# Curto de propósito: o objetivo é que um bloqueio vire **falha legível** em
# segundos, não que a suíte espere pela resolução. Quem espera indefinidamente
# não distingue "bloqueou" de "travou".
_LOCK_TIMEOUT = "2s"

# Teto das esperas de barreira e de `join`. Estourá-lo é falha do teste, não
# flakiness: significa que um dos lados não chegou ao ponto de sincronização —
# quase sempre porque o statement que o dispara deixou de ser emitido.
_TIMEOUT_SINCRONIA = 15.0


@pytest.fixture
def motores(banco_limpo: Engine, database_url: str) -> Iterator[Callable[[], Engine]]:
    """Fábrica de `Engine` dedicado — pool próprio, `lock_timeout` próprio, descartado no fim.

    Depende de `banco_limpo` só pela ordem: garante que o `TRUNCATE` roda antes
    de qualquer conexão deste teste abrir transação.
    """
    criados: list[Engine] = []

    def _criar() -> Engine:
        motor = create_engine(
            database_url,
            connect_args={"options": f"-c timezone=UTC -c lock_timeout={_LOCK_TIMEOUT}"},
        )
        criados.append(motor)
        return motor

    yield _criar
    for motor in criados:
        motor.dispose()


@contextmanager
def _statements_de(motor: Engine) -> Iterator[tuple[list[str], list[str]]]:
    """Grava o SQL **tentado** e o **concluído** por um `Engine`.

    A distinção é o instrumento central de CA6b: `before_cursor_execute` dispara
    antes do `cursor.execute`, `after_cursor_execute` depois. Um statement que
    **bloqueia** aparece no primeiro e não no segundo — é assim que se observa
    *onde* o adapter parou, e não apenas *que* ele falhou.
    """
    tentados: list[str] = []
    concluidos: list[str] = []

    def _antes(conn: object, cursor: object, statement: str, *resto: object) -> None:
        tentados.append(statement)

    def _depois(conn: object, cursor: object, statement: str, *resto: object) -> None:
        concluidos.append(statement)

    event.listen(motor, "before_cursor_execute", _antes)
    event.listen(motor, "after_cursor_execute", _depois)
    try:
        yield tentados, concluidos
    finally:
        event.remove(motor, "before_cursor_execute", _antes)
        event.remove(motor, "after_cursor_execute", _depois)


@contextmanager
def _entrelacar(motor: Engine, gatilho: str, acao: Callable[[], None]) -> Iterator[list[bool]]:
    """Executa `acao` **uma vez**, logo depois do primeiro statement que contém `gatilho`.

    É o entrelace forçado que o plano exige: sem forçá-lo, um teste de leitura
    concorrente passa por sorte — a escrita quase sempre cai fora da janela — e
    não prova nada. Com ele, a escrita concorrente comita **exatamente** entre
    dois statements escolhidos.

    Devolve uma lista de um elemento com o registro de disparo, para que o teste
    possa asserir que o entrelace **aconteceu**. Sem essa asserção, um `gatilho`
    escrito errado faria o teste passar sem ter exercitado nada.
    """
    disparou = [False]

    def _ouvinte(conn: object, cursor: object, statement: str, *resto: object) -> None:
        if disparou[0] or gatilho not in statement:
            return
        disparou[0] = True
        acao()

    event.listen(motor, "after_cursor_execute", _ouvinte)
    try:
        yield disparou
    finally:
        event.remove(motor, "after_cursor_execute", _ouvinte)


def _funcionario(
    *, funcoes: frozenset[JobFunctionId] = frozenset({_F1}), name: str = "Maria"
) -> Employee:
    return Employee(
        id=_E1,
        tenant_id=_A,
        unit_id=_U1,
        name=name,
        workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
        shift_preference=None,
        job_function_ids=funcoes,
    )


def _semear(motor: Engine, *, funcoes: frozenset[JobFunctionId] = frozenset({_F1})) -> None:
    """Funções `f1`/`f2` e o funcionário `e1` com o conjunto pedido."""
    repositorio = PostgresJobFunctionRepository(motor)
    repositorio.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    repositorio.add(JobFunction(id=_F2, tenant_id=_A, name="Chapeiro"))
    PostgresEmployeeRepository(motor).add(_funcionario(funcoes=funcoes))


# ---------------------------------------------------------------------------
# CA10b — a cláusula de colação existe (parte 1: o SQL; parte 2: controle positivo)
# ---------------------------------------------------------------------------

_ORDER_BY = re.compile(r"ORDER BY (?P<clausula>.+?)(?:\s*$)", re.DOTALL)

# `list_by_tenant`, `find_all_by_ids` e, desde a Stage 3.11, `list_by_unit` (L-JF6) —
# as listagens que `L-ORD` governa no port de função. Se outra nascer, esta
# constante é o lugar que reclama.
_LISTAGENS_DO_PORT_DE_FUNCAO = 3


def _clausula_de_ordem(statements: list[str], tabela: str) -> str:
    """A cláusula `ORDER BY` da listagem de `tabela`, normalizada em uma linha."""
    for statement in statements:
        if f"FROM {tabela}" in statement and "ORDER BY" in statement:
            casamento = _ORDER_BY.search(statement)
            assert casamento is not None
            return " ".join(casamento.group("clausula").split())
    raise AssertionError(f"nenhuma listagem de {tabela!r} foi emitida")


def test_ca10b_o_sql_emitido_pelas_tres_listagens_leva_collate_c_nos_dois_termos(
    motores: Callable[[], Engine],
) -> None:
    """CA10b parte 1 — a asserção que **reprova a omissão**, e a única que reprova.

    Medido nesta imagem (`postgres:16-alpine`, musl, `datlocprovider = c`):
    `ORDER BY name`, `ORDER BY name COLLATE "C"` e o `sorted()` do Python
    produzem a **mesma** saída para o dado adversarial. Nenhuma asserção sobre
    **resultado** — nem a de CA10, nas Tasks 06 e 07 — distingue a presença da
    ausência da cláusula. Ela passaria hoje e sempre, e explodiria no primeiro
    cluster glibc/ICU, quando a paginação da 3.4 já dependesse do cursor.

    Por isso o objeto da asserção é o **SQL que o adapter mandou**, lido do
    evento `before_cursor_execute` — estritamente mais forte que recompilar o
    statement no teste, porque assere o texto emitido e não um statement
    reconstruído (`[decision]` datada na §7 do technical).

    E a asserção é sobre a cláusula **inteira**, não sobre a presença da
    substring: `COLLATE` liga-se ao operando à sua esquerda, então
    `ORDER BY name, id COLLATE "C"` **contém** a substring e continua com o
    `name` na colação do banco.
    """
    motor = motores()
    _semear(motor)
    funcoes = PostgresJobFunctionRepository(motor)
    funcionarios = PostgresEmployeeRepository(motor)

    with _statements_de(motor) as (tentados, _):
        funcoes.list_by_tenant(_A)
        funcoes.find_all_by_ids(_A, frozenset({_F1, _F2}))
        funcoes.list_by_unit(_A, _U1)
        funcionarios.list_by_unit(_A, _U1)

    listagens_de_funcao = [
        statement
        for statement in tentados
        if "FROM job_functions" in statement and "ORDER BY" in statement
    ]
    assert len(listagens_de_funcao) == _LISTAGENS_DO_PORT_DE_FUNCAO, (
        "as três listagens de função têm de ordenar"
    )
    for statement in listagens_de_funcao:
        casamento = _ORDER_BY.search(statement)
        assert casamento is not None
        assert (
            " ".join(casamento.group("clausula").split())
            == 'job_functions.name COLLATE "C", job_functions.id COLLATE "C"'
        )

    assert (
        _clausula_de_ordem(tentados, "employees")
        == 'employees.name COLLATE "C", employees.id COLLATE "C"'
    )


def test_ca10b_controle_positivo_a_colacao_escolhida_tem_efeito_semantico(
    motores: Callable[[], Engine],
) -> None:
    """CA10b parte 2 — prova que a cláusula não é ruído, e por que o teste acima existe.

    Três leituras do **mesmo** dado, contra o **mesmo** banco:

    - `COLLATE "C"` bate com o `sorted()` do Python — é a coincidência que
      permite à suíte de contrato ter um corpo só;
    - **sem** cláusula, o resultado depende da colação **default do cluster**, e
      é isso que a terceira leitura assere: sob colação de bytes ela bate (o
      falso verde desta imagem, medido aqui e não suposto), sob colação
      linguística ela **diverge**;
    - `COLLATE "und-x-icu"` **diverge** (`Álvaro` antes de `ana`, minúscula antes
      de maiúscula) — é a prova de que a escolha de colação decide o resultado, e
      de que o dia em que o banco tiver colação linguística a omissão deixa de
      ser inócua.

    **Por que a terceira leitura é condicionada, e não uma igualdade fixa.**
    Afirmar cru que "sem cláusula bate com o `sorted()`" trava uma propriedade do
    **ambiente** (`postgres:16-alpine`, musl), não do adapter. No dia em que a
    imagem virar glibc/ICU — exatamente o cenário contra o qual esta suíte
    existe — a linha ficaria **vermelha sobre adapter correto**, e o sinal seria
    lido como regressão de código. Condicionada à sonda de colação, a asserção
    passa a travar a **relação** (colação de bytes ⇔ omissão indistinguível),
    que é o fato que justifica CA10b asserir sobre o SQL emitido.
    """
    motor = motores()
    repositorio = PostgresJobFunctionRepository(motor)
    nomes = ["Zeus", "Álvaro", "ana", "Ana", "Zeus "]
    for indice, nome in enumerate(nomes):
        repositorio.add(JobFunction(id=JobFunctionId(f"f{indice}"), tenant_id=_A, name=nome))

    def _ordenado_por(clausula: str) -> list[str]:
        with motor.connect() as conexao:
            return list(
                conexao.execute(
                    text(f"SELECT name FROM job_functions WHERE tenant_id = :t {clausula}"),
                    {"t": _A},
                ).scalars()
            )

    def _cluster_ordena_por_bytes() -> bool:
        """A colação **default** deste cluster ordena por byte?

        `datcollate` não responde: esta imagem declara `en_US.utf8` e ordena por
        byte assim mesmo, porque a musl não implementa locales. A sonda é
        semântica e independe do dado do teste — sob colação de bytes `'a'`
        (0x61) vem **depois** de `'B'` (0x42); sob qualquer colação linguística,
        antes.
        """
        with motor.connect() as conexao:
            return bool(conexao.execute(text("SELECT 'a' > 'B'")).scalar_one())

    esperado = sorted(nomes)
    assert _ordenado_por('ORDER BY name COLLATE "C"') == esperado
    assert _ordenado_por('ORDER BY name COLLATE "und-x-icu"') != esperado, (
        "se esta colação não divergisse, a cláusula seria de fato inócua"
    )

    sem_clausula = _ordenado_por("ORDER BY name")
    if _cluster_ordena_por_bytes():
        assert sem_clausula == esperado, (
            "sob colação de bytes, omitir a cláusula produz o mesmo resultado — "
            "é este falso verde que obriga CA10b a asserir sobre o SQL emitido"
        )
    else:
        assert sem_clausula != esperado, (
            "num cluster de colação linguística a omissão passa a ser observável "
            "— é exatamente o cenário contra o qual a cláusula do adapter existe"
        )


# ---------------------------------------------------------------------------
# CA6b — o `FOR UPDATE` do lookup de `update` existe
# ---------------------------------------------------------------------------


def test_ca6b_update_concorrente_bloqueia_no_lookup_e_nao_depois(
    motores: Callable[[], Engine],
) -> None:
    """CA6b — o `FOR UPDATE` serializa duas edições do **mesmo** registro.

    O que torna esta asserção não-trivial: um `UPDATE` **também** trava a linha,
    então um adapter sem `FOR UPDATE` no lookup acabaria bloqueando de todo jeito
    — mais tarde, no `UPDATE`. O resultado final é idêntico nos dois casos, e é
    por isso que nenhum teste de estado distingue.

    O discriminador é **onde** o bloqueio acontece. Com `FOR UPDATE`, o adapter
    para no **primeiro** statement e nada mais chega a rodar; sem ele, o lookup e
    a pré-checagem referencial completam antes — isto é, o adapter decide
    "existe, mesma unidade, funções válidas" a partir de um estado que a
    transação concorrente já está mudando, que é exatamente a check-then-act que
    o lock existe para impedir.

    O bloqueio é observado por `lock_timeout`, não por relógio: a segunda
    conexão falha rápido e legivelmente em vez de pendurar a suíte.
    """
    motor_adapter = motores()
    motor_bloqueador = motores()
    _semear(motor_adapter)
    repositorio = PostgresEmployeeRepository(motor_adapter)

    with motor_bloqueador.begin() as bloqueador:
        # Segura a linha do funcionário: é o que uma edição concorrente em curso
        # e **não commitada** segura.
        bloqueador.execute(
            text("SELECT unit_id FROM employees WHERE id = :e AND tenant_id = :t FOR UPDATE"),
            {"e": _E1, "t": _A},
        )

        with (
            _statements_de(motor_adapter) as (tentados, concluidos),
            pytest.raises(OperationalError) as excecao,
        ):
            repositorio.update(_funcionario(name="Joana"))

    # Pelo `sqlstate`, não pelo texto: `55P03` é `lock_not_available`, e ler a
    # mensagem seria parsing de string cujo conteúdo varia entre versões e
    # locales do Postgres — a mesma disciplina de `integrity_errors.py`.
    assert getattr(excecao.value.orig, "sqlstate", None) == "55P03"
    assert tentados, "o adapter nem chegou a emitir statement"
    assert "FOR UPDATE" in tentados[-1], (
        "o adapter bloqueou em outro statement — o lookup não está tomando o lock"
    )
    assert concluidos == [], (
        "algum statement completou antes do bloqueio: o adapter leu (e decidiu) "
        "sobre um estado que a transação concorrente está mudando"
    )


# ---------------------------------------------------------------------------
# CA17b — a leitura de agregado não é rasgada
# ---------------------------------------------------------------------------


def _mudar_nome_e_funcoes(motor: Engine) -> Callable[[], None]:
    """Escrita concorrente: renomeia **e** troca o vínculo, numa transação só."""

    def _acao() -> None:
        with motor.begin() as conexao:
            conexao.execute(text("UPDATE employees SET name = 'Joana' WHERE id = :e"), {"e": _E1})
            conexao.execute(
                text("DELETE FROM employee_job_functions WHERE employee_id = :e"), {"e": _E1}
            )
            conexao.execute(
                text(
                    "INSERT INTO employee_job_functions "
                    "(employee_id, job_function_id, tenant_id) VALUES (:e, :f, :t)"
                ),
                {"e": _E1, "f": _F2, "t": _A},
            )

    return _acao


def _ler_agregado(repositorio: PostgresEmployeeRepository, metodo: str) -> Employee | None:
    """Os **dois** métodos que montam agregado de quatro tabelas (§5.18).

    A §5.18 nomeia `find_by_id` **e** `list_by_unit`, e os dois têm o mesmo
    problema pela mesma razão. Parametrizar sobre eles é o que impede que só um
    fique preso: com CA17b travando apenas `find_by_id`, `list_by_unit` podia
    voltar a `READ COMMITTED` sem sintoma em teste nenhum.
    """
    if metodo == "find_by_id":
        return repositorio.find_by_id(_A, _U1, _E1)
    encontrados = repositorio.list_by_unit(_A, _U1)
    return encontrados[0] if encontrados else None


@pytest.mark.parametrize("metodo", ["find_by_id", "list_by_unit"])
def test_ca17b_a_leitura_de_agregado_e_consistente_sob_escrita_concorrente(
    motores: Callable[[], Engine], metodo: str
) -> None:
    """CA17b — com uma escrita commitando **entre** os statements, o agregado é coerente.

    Os dois métodos montam o `Employee` a partir de quatro tabelas em statements
    separados. Sob `READ COMMITTED` — o default — **cada statement pega um
    snapshot novo**, e uma escrita que comite no meio produz uma entidade que
    nunca existiu: pai antigo com filha nova.

    O entrelace é **forçado**: a escrita concorrente comita exatamente depois do
    `SELECT … FROM employees` e antes da leitura dos vínculos. Sem forçá-lo, a
    janela é de microssegundos e o teste passaria por sorte.

    A asserção é sobre a **coerência**, não sobre qual das duas versões vem: o
    que o port promete é um agregado que existiu, e o snapshot único entrega o
    anterior por inteiro.
    """
    motor_leitor = motores()
    motor_escritor = motores()
    _semear(motor_leitor)
    repositorio = PostgresEmployeeRepository(motor_leitor)

    with _entrelacar(motor_leitor, "FROM employees", _mudar_nome_e_funcoes(motor_escritor)) as (
        disparou
    ):
        lido = _ler_agregado(repositorio, metodo)

    assert disparou[0], "o entrelace não disparou — o teste não exercitou nada"
    assert lido is not None
    assert (lido.name, lido.job_function_ids) == ("Maria", frozenset({_F1})), (
        "leitura rasgada: o agregado devolvido mistura estados de dois instantes"
    )


def test_ca17b_controle_sob_read_committed_a_mesma_leitura_rasga(
    motores: Callable[[], Engine],
) -> None:
    """O controle que prova o mecanismo — sem ele, o teste acima passaria por nada.

    Repete a leitura **à mão**, na ordem do adapter mas sob o isolamento default,
    com o mesmo entrelace. Se este teste ficasse verde (isto é, se a leitura
    **não** rasgasse), a conclusão correta não seria "o `READ COMMITTED` também
    serve": seria que o entrelace não está disparando onde se pensa, e que o
    teste anterior é decorativo.
    """
    motor_leitor = motores()
    motor_escritor = motores()
    _semear(motor_leitor)

    with (
        _entrelacar(motor_leitor, "FROM employees", _mudar_nome_e_funcoes(motor_escritor)) as (
            disparou
        ),
        motor_leitor.connect() as conexao,
        conexao.begin(),
    ):
        nome = conexao.execute(
            text("SELECT name FROM employees WHERE id = :e AND tenant_id = :t"),
            {"e": _E1, "t": _A},
        ).scalar_one()
        vinculos = set(
            conexao.execute(
                text("SELECT job_function_id FROM employee_job_functions WHERE employee_id = :e"),
                {"e": _E1},
            ).scalars()
        )

    assert disparou[0]
    assert (nome, vinculos) == ("Maria", {_F2}), (
        "sob READ COMMITTED a leitura deveria rasgar (pai antigo, filha nova); "
        "se não rasgou, o entrelace não está caindo entre os dois statements"
    )


# ---------------------------------------------------------------------------
# §5.20 — a regressão que protege a escrita por diferença
# ---------------------------------------------------------------------------


def test_regressao_5_20_update_que_nao_mexe_no_conjunto_nao_deadlocka_com_delete_de_funcao(
    motores: Callable[[], Engine],
) -> None:
    """§5.20 — o terceiro invariante medido, e o **único sem CA numerado** no concept.

    É a regressão que impede a "simplificação" futura de trocar a escrita por
    diferença por `DELETE`-tudo-`INSERT`-tudo. Essa troca produz o **mesmo**
    estado final e passa em **todos** os outros testes desta Stage, inclusive nos
    de lei — hoje **58 funções / 122 ids** (a parametrização `[fake]`/`[postgres]`
    duplica cada uma); os "46" que o plano cita são os **herdados** da 3.2, antes
    dos de `L-ORD`. E foi medida contra o banco real produzindo `40P01
    DeadlockDetected`, que é `OperationalError`, **não** `IntegrityError`: escapa
    do tradutor e vira 500 na 3.4.

    O cenário: `E` tem `{f1, f2}`. A conexão A faz `update(E)` com o **mesmo**
    conjunto; a B apaga a função `f2`.

    Por que a reescrita cega deadlockaria: ao reinserir os vínculos, A pega
    `FOR KEY SHARE` nas linhas de `job_functions` de `f1` e `f2`; B já segura
    lock exclusivo na de `f2` e precisa varrer `employee_job_functions` pelo
    `RESTRICT`. Ordem de aquisição invertida ⇒ `40P01`. Por diferença, A não
    toca vínculo nenhum e portanto não pega lock nenhum em `job_functions`.

    Sincronização **nomeada**: `threading.Barrier(2)` liberada depois que cada
    lado abriu a transação e tomou (ou está prestes a tomar) o seu primeiro lock,
    mais `lock_timeout` nas duas conexões. É a ordem de aquisição, não o relógio,
    que produz o deadlock — e o `lock_timeout` converte um bloqueio indefinido em
    falha rápida em vez de pendurar a suíte.

    **Qual asserção carrega a regressão — e não é a que o plano nomeia.**
    Medido contra duas variantes da reescrita cega: das reprovações observadas,
    **todas** caem na asserção sobre B, com `40P01 DeadlockDetected` — nenhuma
    em A (classificado pelo número de linha do `AssertionError`). Ou seja,
    `resultados["a"] is None` (o critério **literal** do plano, "o `update` de A
    completa") **passa** sob o mutante: o deadlock elege B como vítima. O que
    reprova é B voltar `40P01` em vez do `JobFunctionInUseError` do `RESTRICT` —
    e `40P01` é `OperationalError`, escapa do tradutor e viraria 500 na 3.4.

    Por isso a linha marcada abaixo é load-bearing, e a frase do plano ("o que B
    recebe é consequência esperada e não é o objeto do teste") **não** vale como
    licença para apagá-la: apagada, este teste passa a aceitar o mutante.
    """
    motor_a = motores()
    motor_b = motores()
    _semear(motor_a, funcoes=frozenset({_F1, _F2}))
    barreira = threading.Barrier(2, timeout=_TIMEOUT_SINCRONIA)
    resultados: dict[str, BaseException | None] = {"a": None, "b": None}

    def _esperar() -> None:
        barreira.wait()

    def _lado_a() -> None:
        try:
            # O conjunto é o **mesmo** que já está gravado: é este `update` que a
            # escrita por diferença faz não tocar em vínculo nenhum.
            PostgresEmployeeRepository(motor_a).update(
                _funcionario(funcoes=frozenset({_F1, _F2}), name="Joana")
            )
        except BaseException as erro:
            resultados["a"] = erro

    def _lado_b() -> None:
        try:
            PostgresJobFunctionRepository(motor_b).delete(
                _A, _F2, expected=UnitEnablement.everywhere()
            )
        except BaseException as erro:
            resultados["b"] = erro

    # A sincroniza na leitura dos vínculos — o statement imediatamente **antes**
    # de onde a reescrita cega tomaria os seus locks —; B, depois do lookup da
    # função, prestes a tomar o lock exclusivo no `DELETE`. Os dois gatilhos
    # existem nas **duas** variantes do adapter, senão a barreira penduraria sob
    # a implementação correta em vez de reprovar a errada.
    with (
        _entrelacar(motor_a, "FROM employee_job_functions", _esperar) as disparou_a,
        _entrelacar(motor_b, "FROM job_functions", _esperar) as disparou_b,
    ):
        thread_a = threading.Thread(target=_lado_a, name="update-do-funcionario")
        thread_b = threading.Thread(target=_lado_b, name="delete-da-funcao")
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=_TIMEOUT_SINCRONIA)
        thread_b.join(timeout=_TIMEOUT_SINCRONIA)

    assert not thread_a.is_alive() and not thread_b.is_alive(), "algum lado pendurou"
    assert disparou_a[0] and disparou_b[0], "a barreira não sincronizou os dois lados"
    # O critério literal do plano. Medido: **passa** sob o mutante — o deadlock
    # nunca cai em A. Fica porque descreve o que a lei promete, mas não é ele
    # que reprova a reescrita cega.
    assert resultados["a"] is None, (
        f"o `update` legítimo foi derrubado: {resultados['a']!r}. "
        f"É a assinatura da reescrita cega das filhas (§5.20)."
    )
    # >>> LOAD-BEARING: é ESTA linha que mata a reescrita cega (§5.20). <<<
    # Medido contra dois mutantes: **todas** as reprovações caem aqui, com B
    # voltando `40P01 DeadlockDetected` em vez do `RESTRICT`; nenhuma reprova na
    # asserção acima. Não a enxugue com base no "não é o objeto do teste" do
    # plano — ver o docstring.
    assert isinstance(resultados["b"], JobFunctionInUseError), (
        f"esperado o `RESTRICT` respondendo em negócio do lado B, veio "
        f"{resultados['b']!r} — `40P01` aqui é a assinatura da reescrita cega (§5.20)"
    )

    gravado = PostgresEmployeeRepository(motor_a).find_by_id(_A, _U1, _E1)
    assert gravado is not None
    assert gravado.name == "Joana"
    assert gravado.job_function_ids == frozenset({_F1, _F2})


def test_regressao_5_20_update_sem_mudanca_no_conjunto_nao_segura_lock_em_job_functions(
    motores: Callable[[], Engine],
) -> None:
    """§5.20 pela **pegada de lock** — a mesma regressão do teste acima, medida na causa.

    **Os dois testes matam a reescrita cega**; este existe por ser
    **determinístico e sem thread**, e por medir a **causa** em vez do sintoma.
    Medido contra duas variantes do mutante (uma mantém a leitura dos vínculos e
    zera a diferença; a outra apaga tudo e reinsere sem ler), somando todas as
    execuções da medição:

    | | contra os mutantes | limpo |
    |---|---|---|
    | teste de deadlock (acima) | 154 de 160 reprovam (~96%) | 25/25 passam |
    | **este teste** | **50 de 50 reprovam** | 25/25 passam |

    As 6 sobreviventes são o que se espera de um teste de concorrência com duas
    threads: quando B completa a varredura do `RESTRICT` antes de A tomar os
    locks das linhas de vínculo, não há inversão e não há deadlock. Não é
    ajustável por sincronização — a barreira já está no ponto certo (o gatilho
    casa com um statement presente nas duas variantes, e sob o mutante ele cai
    colado às escritas de vínculo) —, porque o **sintoma** depende de
    escalonamento. Este teste não tem essa cauda: sem thread, o entrelace é um
    evento entre statements, e a **causa** que ele mede não depende de quem
    chega primeiro.

    O que a reescrita cega faz de errado não é deadlockar — deadlock é a
    consequência, e é ela que depende de escalonamento. É **tomar lock em
    `job_functions`** num `update` que não mexeu no conjunto: ao reinserir os
    vínculos, a transação pega `FOR KEY SHARE` nas linhas de `f1` e `f2`. Por
    diferença ela não emite statement nenhum sobre os vínculos e portanto não
    toca `job_functions`. A pegada de lock é determinística; o deadlock não.

    Aqui isso é observado com a transação do `update` **aberta e não
    commitada** — o entrelace dispara no último statement dela —, tentando
    remover `f2` de outra conexão:

    - **por diferença:** nenhum lock a disputar; a remoção chega ao `RESTRICT` e
      responde `JobFunctionInUseError` (`23503`), que é a resposta de negócio
      correta;
    - **por reescrita cega:** a remoção **bloqueia** no lock que A não deveria
      ter e morre em `lock_timeout` (`55P03`) — um `OperationalError` que escapa
      do tradutor e vira 500 na 3.4.

    Determinístico, sem thread, sem barreira e sem relógio: é a ordem de
    aquisição de lock que decide, e ela é forçada.
    """
    motor_a = motores()
    motor_b = motores()
    _semear(motor_a, funcoes=frozenset({_F1, _F2}))
    observado: dict[str, BaseException] = {}

    def _tentar_remover_f2() -> None:
        """Roda com a transação do `update` de A ainda aberta."""
        try:
            PostgresJobFunctionRepository(motor_b).delete(
                _A, _F2, expected=UnitEnablement.everywhere()
            )
        except BaseException as erro:
            observado["erro"] = erro

    # Último statement do `update` — existe nas duas variantes, e na cega roda
    # **depois** de os locks indevidos já terem sido tomados.
    with _entrelacar(motor_a, "FROM employee_shift_preferences", _tentar_remover_f2) as disparou:
        PostgresEmployeeRepository(motor_a).update(
            _funcionario(funcoes=frozenset({_F1, _F2}), name="Joana")
        )

    assert disparou[0], "o entrelace não disparou — o teste não exercitou nada"
    erro = observado.get("erro")
    assert isinstance(erro, JobFunctionInUseError), (
        f"esperado o `RESTRICT` respondendo em negócio, veio {erro!r}. "
        f"Um `OperationalError` de `lock_timeout` aqui significa que o `update` "
        f"segurava lock em `job_functions` sem ter mexido no conjunto — a "
        f"assinatura da reescrita cega das filhas (§5.20)."
    )


# ---------------------------------------------------------------------------
# CA8b / CA8c — os dois lados da mesma constraint, e o discriminador de conduta
# ---------------------------------------------------------------------------


def test_ca8b_a_mesma_constraint_do_banco_traduz_diferente_conforme_a_operacao(
    motores: Callable[[], Engine],
) -> None:
    """CA8b — a ambiguidade é **real**, medida contra o banco, e não hipótese de ADR.

    As duas operações abaixo violam a **mesma** constraint, com o mesmo
    `sqlstate` e o mesmo `diag.constraint_name`, e significam coisas **opostas**:

    - `INSERT` de vínculo com função inexistente ⇒ L-E4 ⇒ `JobFunctionNotFoundError`
    - `DELETE` da função referenciada ⇒ L-JF3 ⇒ `JobFunctionInUseError`

    Um mapa global por nome — o de identity — responderia errado em metade dos
    casos, e erraria de forma **plausível**: "função não encontrada" ao apagar
    uma função que existe. Erro plausível é pior que erro cru, porque não convida
    a investigar.
    """
    motor = motores()
    _semear(motor)

    with pytest.raises(IntegrityError) as no_insert, motor.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employee_job_functions (employee_id, job_function_id, tenant_id) "
                "VALUES (:e, 'f-que-nao-existe', :t)"
            ),
            {"e": _E1, "t": _A},
        )

    with pytest.raises(IntegrityError) as no_delete, motor.begin() as conexao:
        conexao.execute(text("DELETE FROM job_functions WHERE id = :f"), {"f": _F1})

    assert constraint_name(no_insert.value) == "fk_employee_job_functions_job_function"
    assert constraint_name(no_delete.value) == constraint_name(no_insert.value), (
        "as duas operações têm de violar a MESMA constraint — é isso que torna "
        "a tradução por nome insuficiente"
    )

    na_escrita = translate(no_insert.value, ON_WRITE_EMPLOYEE, "x")
    na_remocao = translate(no_delete.value, ON_DELETE_JOB_FUNCTION, "x")
    assert isinstance(na_escrita, JobFunctionNotFoundError)
    assert isinstance(na_remocao, JobFunctionInUseError)
    # E o cruzado, que é o que um mapa global produziria:
    assert not isinstance(na_escrita, JobFunctionInUseError)


def test_ca8c_o_backstop_de_l_e4_responde_pelo_metodo_publico_e_cita_o_conjunto(
    motores: Callable[[], Engine],
) -> None:
    """CA8c — a corrida real de L-E4, entrando por `update()`, não por `translate()`.

    Entrar pelo **método público** é o ponto. Chamar `translate(...)` direto
    prova que o mapa está certo, mas não que ele está **ligado**: um adapter que
    passasse `ON_DELETE_JOB_FUNCTION` (ou um mapa global) para o `translate` de
    `update` passaria naquele teste e falharia neste.

    O entrelace apaga `f2` **depois** da pré-checagem referencial e **antes** do
    `INSERT` do vínculo — que é exatamente a corrida que a lei prevê e que a FK
    existe para pegar. E a mensagem cita o **conjunto** com `sorted()`, não uma
    id: nessa corrida o adapter não sabe qual sumiu, e chutar seria descrever o
    conflito errado com a confiança de quem sabe.
    """
    motor = motores()
    motor_concorrente = motores()
    _semear(motor)
    repositorio = PostgresEmployeeRepository(motor)

    def _apagar_f2() -> None:
        with motor_concorrente.begin() as conexao:
            conexao.execute(text("DELETE FROM job_functions WHERE id = :f"), {"f": _F2})

    with (
        _entrelacar(motor, "FROM job_functions", _apagar_f2) as disparou,
        pytest.raises(JobFunctionNotFoundError) as excecao,
    ):
        repositorio.update(_funcionario(funcoes=frozenset({_F1, _F2})))

    assert disparou[0], "o entrelace não disparou — a corrida não foi exercitada"
    assert "['f1', 'f2']" in str(excecao.value), (
        "o backstop tem de citar o CONJUNTO; citar uma id sozinha seria afirmar "
        "qual sumiu na corrida, que o adapter não sabe"
    )

    # E nada foi gravado: a transação inteira reverteu.
    gravado = repositorio.find_by_id(_A, _U1, _E1)
    assert gravado is not None
    assert gravado.name == "Maria"
    assert gravado.job_function_ids == frozenset({_F1})


def test_ca8c_o_caminho_comum_cita_a_menor_id_ausente_e_nao_o_conjunto(
    motores: Callable[[], Engine],
) -> None:
    """A outra metade do discriminador — e é o **par** que carrega a informação.

    A pré-checagem sabe qual id falta e cita **uma**, a menor em ordem
    lexicográfica; o backstop cita o **conjunto**. Essa diferença de forma é a
    única evidência observável de qual das duas camadas de guarda respondeu — e
    sem ela um adapter **sem pré-checagem nenhuma**, respondendo tudo pela FK,
    passaria em todo o resto da Stage.
    """
    motor = motores()
    _semear(motor)

    with pytest.raises(JobFunctionNotFoundError) as excecao:
        PostgresEmployeeRepository(motor).update(
            _funcionario(funcoes=frozenset({_F1, JobFunctionId("f97"), JobFunctionId("f99")}))
        )

    assert "'f97'" in str(excecao.value)
    assert "f99" not in str(excecao.value), (
        "citar o conjunto aqui apagaria a distinção entre pré-checagem e backstop"
    )


def test_o_backstop_de_identidade_responde_pelo_metodo_publico_e_cita_a_id(
    motores: Callable[[], Engine],
) -> None:
    """A corrida de L-E1: o id é tomado **entre** a guarda e o `INSERT`.

    Fecha o outro ramo de `_conflict_detail` — o que devolve a id — e a
    outra entrada de `ON_WRITE_EMPLOYEE`. Aqui a mensagem cita a id porque o
    adapter **sabe** qual é: é a que ele tentou gravar, e a constraint violada é
    de identidade, não de referência. É o contraste com o teste do conjunto que
    torna a escolha de `_conflict_detail` observável em vez de estilística.
    """
    motor = motores()
    motor_concorrente = motores()
    repositorio = PostgresJobFunctionRepository(motor)
    repositorio.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))

    def _tomar_o_id() -> None:
        with motor_concorrente.begin() as conexao:
            conexao.execute(
                text(
                    "INSERT INTO employees "
                    "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
                    "VALUES (:e, :t, 'u1', 'Outra', 'fixed', 40, true)"
                ),
                {"e": _E1, "t": _A},
            )

    with (
        _entrelacar(motor, "FROM employees", _tomar_o_id) as disparou,
        pytest.raises(EmployeeAlreadyExistsError) as excecao,
    ):
        PostgresEmployeeRepository(motor).add(_funcionario())

    assert disparou[0], "o entrelace não disparou — a corrida não foi exercitada"
    assert "'e1'" in str(excecao.value)


# ---------------------------------------------------------------------------
# Issue #68 — edição concorrente não apaga o vínculo; vínculo concorrente não o troca
# ---------------------------------------------------------------------------

_LOGIN = UserId("login-do-r17")


def test_issue_68_renomear_concorrente_nao_apaga_o_vinculo_gravado(
    motores: Callable[[], Engine],
) -> None:
    """O cenário da issue, com duas conexões e o use case de verdade.

    O R07 (`RenameEmployeeUseCase` sobre o adapter Postgres) lê o registro; o
    R17 vincula e **comita** exatamente depois dessa leitura, por outra
    conexão; o R07 grava a entidade que leu — com `user_id=None`. Antes da
    #68, o `update` gravava o agregado inteiro e o vínculo sumia: conta órfã,
    e-mail tomado. Agora o `update` não grava o vínculo, e as duas escritas
    sobrevivem.
    """
    motor_r07 = motores()
    motor_r17 = motores()
    _semear(motor_r07)
    renomear = RenameEmployeeUseCase(
        PostgresEmployeeRepository(motor_r07), guard=PermissiveAccessGuard()
    )

    def _r17_vincula() -> None:
        PostgresEmployeeRepository(motor_r17).link_login(_A, _U1, _E1, _LOGIN)

    with _entrelacar(motor_r07, "FROM employees", _r17_vincula) as disparou:
        renomear.execute(
            RenameEmployeeCommand(
                actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, name="Joana"
            )
        )

    assert disparou[0], "o entrelace não disparou — a corrida não foi exercitada"
    relido = PostgresEmployeeRepository(motor_r17).find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert (relido.name, relido.user_id) == ("Joana", _LOGIN), (
        "a edição gravada depois do vínculo apagou o vínculo (ou perdeu o nome)"
    )


def test_issue_68_link_login_bloqueia_no_lookup_e_nao_depois(
    motores: Callable[[], Engine],
) -> None:
    """A guarda de `L-LINK` decide sob o lock — a mesma prova da CA6b para o `update`.

    Com a linha presa por outra transação, `link_login` para no **primeiro**
    statement, o `SELECT … FOR UPDATE`, e nada completa antes. Sem o lock, a
    leitura do vínculo e a montagem do agregado completariam primeiro, e a
    guarda decidiria "sem vínculo" sobre um estado que a transação concorrente
    está mudando.
    """
    motor_adapter = motores()
    motor_bloqueador = motores()
    _semear(motor_adapter)
    repositorio = PostgresEmployeeRepository(motor_adapter)

    with motor_bloqueador.begin() as bloqueador:
        bloqueador.execute(
            text("SELECT unit_id FROM employees WHERE id = :e AND tenant_id = :t FOR UPDATE"),
            {"e": _E1, "t": _A},
        )
        with (
            _statements_de(motor_adapter) as (tentados, concluidos),
            pytest.raises(OperationalError) as excecao,
        ):
            repositorio.link_login(_A, _U1, _E1, _LOGIN)

    assert getattr(excecao.value.orig, "sqlstate", None) == "55P03"
    assert tentados, "o adapter nem chegou a emitir statement"
    assert "FOR UPDATE" in tentados[-1], "o adapter bloqueou em outro statement"
    assert concluidos == [], "algum statement completou antes do lock"


def _esperar_backend_bloqueado(motor: Engine) -> None:
    """Espera até haver um backend **esperando lock** — condição, não relógio.

    É o ponto de sincronização da corrida de dois R17: o primeiro só comita
    depois de o segundo estar de fato parado no lock; senão o teste exercitaria
    a ordem serial, que qualquer implementação acerta, em vez da corrida. A
    pausa entre consultas é recuo de polling, não o mecanismo de sincronia.
    """
    recuo = threading.Event()
    tentativas = int(_TIMEOUT_SINCRONIA / 0.02)
    for _ in range(tentativas):
        with motor.connect() as conexao:
            esperando = conexao.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                )
            ).scalar_one()
        if esperando:
            return
        recuo.wait(0.02)
    raise AssertionError("o segundo R17 nunca ficou esperando o lock")


def test_issue_68_dois_vinculos_concorrentes_o_segundo_e_recusado_e_nao_troca_o_primeiro(
    motores: Callable[[], Engine],
) -> None:
    """Dois R17 ao mesmo tempo: o primeiro a comitar vence, o outro recebe 409.

    O primeiro vínculo está gravado e **não comitado** numa transação aberta; o
    segundo `link_login` roda numa thread e fica parado no lock. Só então o
    primeiro comita. Com a guarda sob o lock, o segundo relê o gravado e
    responde `EmployeeAlreadyHasLoginError`. Sem ela, o segundo teria lido
    "sem vínculo" antes, esperado só no `UPDATE`, e gravado por cima — trocando
    em silêncio o vínculo do primeiro, cuja conta ficaria órfã.
    """
    motor_primeiro = motores()
    motor_segundo = motores()
    motor_observador = motores()
    _semear(motor_primeiro)
    erros: list[BaseException] = []

    def _segundo_r17() -> None:
        try:
            PostgresEmployeeRepository(motor_segundo).link_login(
                _A, _U1, _E1, UserId("login-do-segundo")
            )
        except BaseException as erro:  # o teste inspeciona o tipo
            erros.append(erro)

    with motor_primeiro.begin() as primeiro:
        primeiro.execute(
            text("UPDATE employees SET user_id = :u WHERE id = :e AND tenant_id = :t"),
            {"u": _LOGIN, "e": _E1, "t": _A},
        )
        segundo = threading.Thread(target=_segundo_r17)
        segundo.start()
        _esperar_backend_bloqueado(motor_observador)
    segundo.join(_TIMEOUT_SINCRONIA)

    assert not segundo.is_alive(), "o segundo R17 não terminou"
    assert len(erros) == 1, erros
    assert isinstance(erros[0], EmployeeAlreadyHasLoginError), erros
    relido = PostgresEmployeeRepository(motor_observador).find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == _LOGIN, "o segundo vínculo trocou o primeiro"


# ---------------------------------------------------------------------------
# Issue #108 — remoção concorrente com R17 não apaga o registro vinculado
# ---------------------------------------------------------------------------


def _registro_e_vinculo(motor: Engine) -> tuple[bool, UserId | None]:
    relido = PostgresEmployeeRepository(motor).find_by_id(_A, _U1, _E1)
    return (relido is not None, None if relido is None else relido.user_id)


def test_issue_108_r17_entre_a_leitura_e_o_delete_recusa_a_remocao(
    motores: Callable[[], Engine],
) -> None:
    """O cenário da issue, com duas conexões e o use case de verdade.

    O R15 (`DeleteEmployeeUseCase` sobre o adapter Postgres) lê o registro sem
    vínculo; o R17 vincula e **comita** exatamente depois dessa leitura, por
    outra conexão; o R15 segue para o `delete`. Antes da #108 o `DELETE` não
    olhava o `user_id` gravado: o registro sumia e a conta criada pelo R17
    ficava órfã, com o e-mail tomado. Agora o port relê o vínculo sob o lock e
    recusa — o 409 de `EmployeeHasLoginError`.
    """
    motor_r15 = motores()
    motor_r17 = motores()
    _semear(motor_r15)
    remover = DeleteEmployeeUseCase(
        PostgresEmployeeRepository(motor_r15), guard=PermissiveAccessGuard()
    )

    def _r17_vincula() -> None:
        PostgresEmployeeRepository(motor_r17).link_login(_A, _U1, _E1, _LOGIN)

    with (
        _entrelacar(motor_r15, "FROM employees", _r17_vincula) as disparou,
        pytest.raises(EmployeeHasLoginError),
    ):
        remover.execute(
            DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
        )

    assert disparou[0], "o entrelace não disparou — a corrida não foi exercitada"
    assert _registro_e_vinculo(motor_r17) == (True, _LOGIN), (
        "o registro vinculado foi removido (ou perdeu o vínculo) — conta órfã"
    )


def test_issue_108_delete_bloqueia_no_lookup_e_nao_depois(
    motores: Callable[[], Engine],
) -> None:
    """A guarda de `L-DEL-LINK` decide sob o lock — a mesma prova da CA6b.

    Com a linha presa por outra transação, `delete` para no **primeiro**
    statement, o `SELECT … FOR UPDATE`, e nada completa antes. Sem o lock, a
    leitura do vínculo completaria primeiro e a guarda decidiria "sem vínculo"
    sobre um estado que a transação concorrente está mudando.
    """
    motor_adapter = motores()
    motor_bloqueador = motores()
    _semear(motor_adapter)
    repositorio = PostgresEmployeeRepository(motor_adapter)

    with motor_bloqueador.begin() as bloqueador:
        bloqueador.execute(
            text("SELECT unit_id FROM employees WHERE id = :e AND tenant_id = :t FOR UPDATE"),
            {"e": _E1, "t": _A},
        )
        with (
            _statements_de(motor_adapter) as (tentados, concluidos),
            pytest.raises(OperationalError) as excecao,
        ):
            repositorio.delete(_A, _U1, _E1)

    assert getattr(excecao.value.orig, "sqlstate", None) == "55P03"
    assert tentados, "o adapter nem chegou a emitir statement"
    assert "FOR UPDATE" in tentados[-1], "o adapter bloqueou em outro statement"
    assert concluidos == [], "algum statement completou antes do lock"


def test_issue_108_delete_que_espera_um_vinculo_em_curso_o_rele_e_recusa(
    motores: Callable[[], Engine],
) -> None:
    """O vínculo está gravado e **não comitado**; a remoção espera o lock e relê.

    O `delete` roda numa thread e fica parado no lock da linha. Só então o
    vínculo comita. Com a guarda sob o lock, a remoção relê a linha já
    vinculada e responde `EmployeeHasLoginError`. Uma guarda lida antes do
    lock — ou sob um snapshot anterior ao commit — veria "sem vínculo" e
    apagaria o registro.
    """
    motor_r17 = motores()
    motor_r15 = motores()
    motor_observador = motores()
    _semear(motor_r17)
    erros: list[BaseException] = []

    def _r15_remove() -> None:
        try:
            PostgresEmployeeRepository(motor_r15).delete(_A, _U1, _E1)
        except BaseException as erro:  # o teste inspeciona o tipo
            erros.append(erro)

    with motor_r17.begin() as r17:
        r17.execute(
            text("UPDATE employees SET user_id = :u WHERE id = :e AND tenant_id = :t"),
            {"u": _LOGIN, "e": _E1, "t": _A},
        )
        r15 = threading.Thread(target=_r15_remove)
        r15.start()
        _esperar_backend_bloqueado(motor_observador)
    r15.join(_TIMEOUT_SINCRONIA)

    assert not r15.is_alive(), "a remoção não terminou"
    assert len(erros) == 1, erros
    assert isinstance(erros[0], EmployeeHasLoginError), erros
    assert _registro_e_vinculo(motor_observador) == (True, _LOGIN), (
        "a remoção apagou o registro vinculado por um R17 em curso"
    )


def test_issue_108_delete_escreve_com_o_tenant_no_where(
    motores: Callable[[], Engine],
) -> None:
    """O `DELETE` reescrito na #108 mantém o `tenant_id` no predicado da escrita.

    Tirá-lo não muda resultado nenhum: o `id` é PK global e a linha já foi
    conferida no endereço de três partes sob o lock. Por isso nenhum teste de
    estado o distingue, e a mutação sobrevivia. Mas as escritas de staff no
    registro filtram por tenant mesmo depois do lookup sob lock (o `UPDATE` de
    `link_login` e o de `update` também): se o lookup um dia deixar de preceder
    a escrita, o `DELETE` sem tenant alcançaria a linha de outro tenant. O
    objeto da asserção é o SQL emitido, como na CA6b.
    """
    motor = motores()
    _semear(motor)

    with _statements_de(motor) as (tentados, _):
        PostgresEmployeeRepository(motor).delete(_A, _U1, _E1)

    remocoes = [s for s in tentados if s.lstrip().startswith("DELETE FROM employees ")]
    assert len(remocoes) == 1, tentados
    _, _, predicado = remocoes[0].partition(" WHERE ")
    assert "employees.id = " in predicado, remocoes[0]
    assert "employees.tenant_id = " in predicado, (
        f"o DELETE de employees perdeu o filtro de tenant: {remocoes[0]!r}"
    )


# ---------------------------------------------------------------------------
# Issue #206 — alteração concorrente das unidades de uma função
# ---------------------------------------------------------------------------
#
# `update_enablement` (L-JF7 revisada) só grava se a habilitação gravada ainda for
# a que o chamador leu, e decide isso sob `FOR NO KEY UPDATE`. Sem a condição, o estado
# final de uma corrida é o conjunto do segundo escritor — que nenhum teste de
# estado sem concorrência distingue de uma escrita legítima.

_UA = UnitId("u-a")
_UB = UnitId("u-b")
_SO_A = UnitEnablement.only(frozenset({_UA}))
_A_E_B = UnitEnablement.only(frozenset({_UA, _UB}))


def _semear_funcao_em_a(motor: Engine) -> None:
    PostgresJobFunctionRepository(motor).add(
        JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro", unit_enablement=_SO_A)
    )


def _habilitacao_gravada(motor: Engine) -> UnitEnablement:
    gravada = PostgresJobFunctionRepository(motor).find_by_id(_A, _F1)
    assert gravada is not None
    return gravada.unit_enablement


def test_issue_206_gerente_que_leu_antes_do_alargamento_e_recusado_e_b_fica(
    motores: Callable[[], Engine],
) -> None:
    """O cenário da issue, com duas conexões e o use case de verdade.

    A função vale em `{A}`. O gerente de A (`SetJobFunctionUnitsUseCase` sobre o
    adapter Postgres) lê a função; o dono alarga para `{A, B}` e **comita**, por
    outra conexão, exatamente depois dessa leitura; o gerente segue e reenvia
    `{A}`. Antes da #206 a escrita substituía a habilitação inteira e B saía por
    um ator sem alcance sobre B. Agora o port compara sob o lock a gravada com a
    lida, recusa, e B fica.

    O gatilho é a consulta dos **vínculos**, a última da leitura: disparar na da
    linha deixaria a leitura remontar os vínculos já alterados, e o gerente
    leria `{A, B}` — outra corrida, não a da issue.
    """
    motor_gerente = motores()
    motor_dono = motores()
    _semear_funcao_em_a(motor_gerente)
    guard = InMemoryAccessGuard(credential=TEST_ACTOR)
    guard.grant(PERMISSION_MANAGE_JOB_FUNCTIONS, tenant_id=_A)
    guard.grant(PERMISSION_MANAGE_JOB_FUNCTIONS, tenant_id=_A, unit_id=_UA)
    alterar = SetJobFunctionUnitsUseCase(
        PostgresJobFunctionRepository(motor_gerente),
        PostgresEmployeeRepository(motor_gerente),
        guard=guard,
    )

    def _dono_alarga() -> None:
        PostgresJobFunctionRepository(motor_dono).update_enablement(
            JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro", unit_enablement=_A_E_B),
            expected=_SO_A,
        )

    with (
        _entrelacar(motor_gerente, "FROM job_function_units", _dono_alarga) as disparou,
        pytest.raises(JobFunctionEnablementChangedError),
    ):
        alterar.execute(
            SetJobFunctionUnitsCommand(
                actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F1, unit_ids=frozenset({_UA})
            )
        )

    assert disparou[0], "o entrelace não disparou — a corrida não foi exercitada"
    assert _habilitacao_gravada(motor_dono) == _A_E_B, (
        "a segunda alteração gravou por cima da primeira — B saiu sem alcance sobre B"
    )


def test_issue_206_update_enablement_bloqueia_no_lookup_e_nao_depois(
    motores: Callable[[], Engine],
) -> None:
    """A comparação decide sob o lock — a mesma prova da CA6b e da #68.

    Com a linha da função presa por outra transação, `update_enablement` para no
    **primeiro** statement, o `SELECT … FOR NO KEY UPDATE`, e nada completa antes. Sem o
    lock, a remontagem da habilitação completaria primeiro e a comparação
    decidiria sobre um estado que a transação concorrente está mudando.
    """
    motor_adapter = motores()
    motor_bloqueador = motores()
    _semear_funcao_em_a(motor_adapter)
    repositorio = PostgresJobFunctionRepository(motor_adapter)

    with motor_bloqueador.begin() as bloqueador:
        bloqueador.execute(
            text("SELECT id FROM job_functions WHERE id = :f AND tenant_id = :t FOR UPDATE"),
            {"f": _F1, "t": _A},
        )
        with (
            _statements_de(motor_adapter) as (tentados, concluidos),
            pytest.raises(OperationalError) as excecao,
        ):
            repositorio.update_enablement(
                JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro", unit_enablement=_A_E_B),
                expected=_SO_A,
            )

    assert getattr(excecao.value.orig, "sqlstate", None) == "55P03"
    assert tentados, "o adapter nem chegou a emitir statement"
    assert "FOR NO KEY UPDATE" in tentados[-1], "o adapter bloqueou em outro statement"
    assert concluidos == [], "algum statement completou antes do lock"


def test_issue_206_segunda_alteracao_que_espera_a_primeira_a_rele_e_e_recusada(
    motores: Callable[[], Engine],
) -> None:
    """Duas alterações ao mesmo tempo: a segunda espera o lock, relê e é recusada.

    A primeira conexão prende a linha e acrescenta B **sem comitar**; a segunda,
    numa thread, chama `update_enablement` com a leitura antiga (`{A}`) e fica
    parada no lock. Só então a primeira comita. Com a comparação sob o lock, a
    segunda relê `{A, B}` — a consulta dos vínculos, depois do lock, abre snapshot
    novo em `READ COMMITTED` — e responde `JobFunctionEnablementChangedError`.
    Comparando antes do lock, ou sob o snapshot anterior ao commit, ela veria
    `{A}`, gravaria `{A}` por cima e B sairia.
    """
    motor_primeira = motores()
    motor_segunda = motores()
    motor_observador = motores()
    _semear_funcao_em_a(motor_primeira)
    erros: list[BaseException] = []

    def _segunda_alteracao() -> None:
        try:
            PostgresJobFunctionRepository(motor_segunda).update_enablement(
                JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro", unit_enablement=_SO_A),
                expected=_SO_A,
            )
        except BaseException as erro:  # o teste inspeciona o tipo
            erros.append(erro)

    with motor_primeira.begin() as primeira:
        primeira.execute(
            text("SELECT id FROM job_functions WHERE id = :f AND tenant_id = :t FOR UPDATE"),
            {"f": _F1, "t": _A},
        )
        primeira.execute(
            text(
                "INSERT INTO job_function_units (job_function_id, tenant_id, unit_id) "
                "VALUES (:f, :t, :u)"
            ),
            {"f": _F1, "t": _A, "u": _UB},
        )
        segunda = threading.Thread(target=_segunda_alteracao)
        segunda.start()
        _esperar_backend_bloqueado(motor_observador)
    segunda.join(_TIMEOUT_SINCRONIA)

    assert not segunda.is_alive(), "a segunda alteração não terminou"
    assert len(erros) == 1, erros
    assert isinstance(erros[0], JobFunctionEnablementChangedError), erros
    assert _habilitacao_gravada(motor_observador) == _A_E_B, (
        "a segunda alteração gravou a leitura antiga por cima da primeira"
    )


def test_issue_206_atribuicao_em_curso_da_funcao_nao_bloqueia_a_alteracao_de_unidades(
    motores: Callable[[], Engine],
) -> None:
    """O lock do lookup é `FOR NO KEY UPDATE`, que não conflita com o `KEY SHARE` da FK.

    Atribuir a função a um registro insere em `employee_job_functions`, e a FK
    composta prende a linha da função em `KEY SHARE` até o commit. Com um
    `FOR UPDATE` no lookup, a alteração de unidades passaria a esperar toda
    atribuição em curso da mesma função — bloqueio que a escrita antiga (um
    `UPDATE` de coluna não-chave) não tinha. Aqui o `KEY SHARE` fica preso numa
    transação aberta e a alteração completa mesmo assim, dentro do `lock_timeout`.
    """
    motor_adapter = motores()
    motor_atribuicao = motores()
    _semear_funcao_em_a(motor_adapter)

    with motor_atribuicao.begin() as atribuicao:
        atribuicao.execute(
            text("SELECT id FROM job_functions WHERE id = :f AND tenant_id = :t FOR KEY SHARE"),
            {"f": _F1, "t": _A},
        )
        PostgresJobFunctionRepository(motor_adapter).update_enablement(
            JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro", unit_enablement=_A_E_B),
            expected=_SO_A,
        )

    assert _habilitacao_gravada(motor_adapter) == _A_E_B


# ---------------------------------------------------------------------------
# Issue #225 — a leitura de função vê a habilitação de um instante só
# ---------------------------------------------------------------------------
#
# Cada leitura remonta a habilitação em dois statements: a linha de
# `job_functions` (com a flag) e, depois, os vínculos de `job_function_units`.
# Sob `READ COMMITTED` cada statement abre snapshot próprio, e uma alteração de
# "conjunto" para "todas" que comite entre os dois deixa a leitura com a flag
# antiga (`false`) e os vínculos novos (nenhum): `UnitEnablement` recusa a
# combinação e a leitura levanta `InvalidUnitEnablementError` (422). O
# entrelace aqui é forçado logo depois do primeiro statement sobre a tabela da
# função, e a escrita concorrente passa pelo próprio port, por outra conexão.

_TODAS = UnitEnablement.everywhere()
_SO_B = UnitEnablement.only(frozenset({_UB}))
_F1_NOME = "Cozinheiro"
_F2_NOME = "Chapeiro"

# As cinco leituras do port (lei "Leitura coerente" do módulo do port). Se
# nascer outra, esta tupla é o lugar que reclama.
_LEITURAS_DE_FUNCAO = (
    "find_by_id",
    "find_by_name",
    "find_all_by_ids",
    "list_by_tenant",
    "list_by_unit",
)

# Gatilho do entrelace: o primeiro statement sobre a linha da função. Não casa
# com `FROM job_function_units`, a consulta dos vínculos.
_GATILHO_LINHA_DA_FUNCAO = "FROM job_functions"


def _ler_funcao(repositorio: PostgresJobFunctionRepository, metodo: str) -> JobFunction | None:
    """A função `f1` pela leitura nomeada — a única do tenant semeado."""
    if metodo == "find_by_id":
        return repositorio.find_by_id(_A, _F1)
    if metodo == "find_by_name":
        return repositorio.find_by_name(_A, _F1_NOME)
    if metodo == "find_all_by_ids":
        encontradas = repositorio.find_all_by_ids(_A, frozenset({_F1}))
    elif metodo == "list_by_tenant":
        encontradas = repositorio.list_by_tenant(_A)
    else:
        encontradas = repositorio.list_by_unit(_A, _UA)
    assert len(encontradas) <= 1, encontradas
    return encontradas[0] if encontradas else None


def _alterar(
    motor: Engine, funcao: JobFunctionId, nome: str, de: UnitEnablement, para: UnitEnablement
) -> None:
    """Alteração das unidades pelo port, numa transação própria que comita ao voltar."""
    PostgresJobFunctionRepository(motor).update_enablement(
        JobFunction(id=funcao, tenant_id=_A, name=nome, unit_enablement=para), expected=de
    )


@pytest.mark.parametrize("metodo", _LEITURAS_DE_FUNCAO)
def test_issue_225_conjunto_para_todas_no_meio_da_leitura_devolve_estado_coerente(
    motores: Callable[[], Engine], metodo: str
) -> None:
    """O cenário da issue, para cada leitura: `{A}` → todas comita no meio, e a leitura não rasga.

    A função vale em `{A}`. Logo depois que o leitor lê a linha da função (flag
    `false`), outra conexão troca a habilitação para todas as unidades e comita:
    flag `true` e vínculos apagados. Sob `READ COMMITTED` a consulta seguinte, a
    dos vínculos, já vê zero vínculos, e a leitura levanta
    `InvalidUnitEnablementError`. Com o snapshot único, vem `{A}` (antes) ou
    todas (depois) — o port promete um estado que existiu, não qual dos dois.
    """
    motor_leitor = motores()
    motor_escritor = motores()
    _semear_funcao_em_a(motor_leitor)
    repositorio = PostgresJobFunctionRepository(motor_leitor)

    with _entrelacar(
        motor_leitor,
        _GATILHO_LINHA_DA_FUNCAO,
        lambda: _alterar(motor_escritor, _F1, _F1_NOME, _SO_A, _TODAS),
    ) as disparou:
        lida = _ler_funcao(repositorio, metodo)

    assert disparou[0], "o entrelace não disparou — a leitura não foi exercitada no meio"
    assert _habilitacao_gravada(motor_escritor) == _TODAS, "a alteração concorrente não comitou"
    assert lida is not None
    assert lida.unit_enablement in (_SO_A, _TODAS), (
        "leitura rasgada: a habilitação devolvida nunca esteve gravada"
    )


# As três listagens, cada uma com f1 e f2. O estado esperado depois das
# alterações é por método porque f2 sai da unidade A.
_LISTAGENS = ("find_all_by_ids", "list_by_tenant", "list_by_unit")


def _listar(repositorio: PostgresJobFunctionRepository, metodo: str) -> tuple[JobFunction, ...]:
    if metodo == "find_all_by_ids":
        return repositorio.find_all_by_ids(_A, frozenset({_F1, _F2}))
    if metodo == "list_by_tenant":
        return repositorio.list_by_tenant(_A)
    return repositorio.list_by_unit(_A, _UA)


@pytest.mark.parametrize("metodo", _LISTAGENS)
def test_issue_225_listagem_nao_mistura_funcoes_de_instantes_diferentes(
    motores: Callable[[], Engine], metodo: str
) -> None:
    """Numa listagem, todas as funções vêm do mesmo instante (lei do port).

    f1 vale em todas, f2 em `{A}`. No meio da listagem comitam, pelo port e
    nesta ordem, f1 todas → `{A}` e f2 `{A}` → `{B}`. Os instantes gravados são
    (todas, `{A}`) → (`{A}`, `{A}`) → (`{A}`, `{B}`). Sob `READ COMMITTED` a
    listagem leria f1 pela flag antiga (todas) e f2 pelos vínculos novos (`{B}`)
    — o par (todas, `{B}`), que **nunca** esteve gravado, e sem erro nenhum que
    o denuncie. O entrelace dispara depois do primeiro statement; a listagem tem
    de devolver um dos instantes gravados inteiro (aqui, o primeiro ou o último:
    as duas alterações comitam juntas na janela).
    """
    motor_leitor = motores()
    motor_escritor = motores()
    funcoes = PostgresJobFunctionRepository(motor_leitor)
    funcoes.add(JobFunction(id=_F1, tenant_id=_A, name=_F1_NOME, unit_enablement=_TODAS))
    funcoes.add(JobFunction(id=_F2, tenant_id=_A, name=_F2_NOME, unit_enablement=_SO_A))

    def _duas_alteracoes() -> None:
        _alterar(motor_escritor, _F1, _F1_NOME, _TODAS, _SO_A)
        _alterar(motor_escritor, _F2, _F2_NOME, _SO_A, _SO_B)

    with _entrelacar(motor_leitor, _GATILHO_LINHA_DA_FUNCAO, _duas_alteracoes) as disparou:
        listadas = _listar(funcoes, metodo)

    antes = {_F1: _TODAS, _F2: _SO_A}
    depois = {_F1: _SO_A} if metodo == "list_by_unit" else {_F1: _SO_A, _F2: _SO_B}
    lido = {funcao.id: funcao.unit_enablement for funcao in listadas}
    assert disparou[0], "o entrelace não disparou — a listagem não foi exercitada no meio"
    assert lido in (antes, depois), f"listagem com funções de instantes diferentes: {lido!r}"


# `list_by_unit` fica de fora por definição, não por esquecimento: a única
# incoerência que a remontagem enxerga (flag `false`, zero vínculos) não nomeia
# unidade nenhuma, então o filtro de L-JF6 não a lista — devolve vazio, e não há
# remontagem a recusar.
_LEITURAS_QUE_ALCANCAM_FUNCAO_SEM_VINCULO = tuple(
    metodo for metodo in _LEITURAS_DE_FUNCAO if metodo != "list_by_unit"
)


@pytest.mark.parametrize("metodo", _LEITURAS_QUE_ALCANCAM_FUNCAO_SEM_VINCULO)
def test_issue_225_dado_incoerente_gravado_continua_levantando(
    motores: Callable[[], Engine], metodo: str
) -> None:
    """CA9b da 3.11 contra o banco: incoerência **gravada** continua recusada.

    O controle que impede o conserto de virar engolir o erro: a função fica
    gravada com a flag `false` e sem vínculo nenhum — estado que nenhuma escrita
    do port produz —, e toda leitura que a alcança levanta
    `InvalidUnitEnablementError`.
    """
    motor = motores()
    _semear_funcao_em_a(motor)
    with motor.begin() as conexao:
        conexao.execute(
            text("DELETE FROM job_function_units WHERE job_function_id = :f"), {"f": _F1}
        )

    with pytest.raises(InvalidUnitEnablementError):
        _ler_funcao(PostgresJobFunctionRepository(motor), metodo)


# ---------------------------------------------------------------------------
# Issue #207 — renomear e apagar condicionais à habilitação lida
# ---------------------------------------------------------------------------
#
# Renomear e apagar passam a exigir alcance sobre as unidades em que a função vale,
# autorizado contra a habilitação **lida**; `update` (L-JF2) e `delete` (L-JF3)
# recebem essa leitura e decidem sob o lock da linha, na forma de `update_enablement`.
# O lookup de `delete` agora remonta a habilitação — sob `FOR UPDATE`, onde as duas
# metades não podem vir de instantes diferentes (o que a #225 temia sem lock).

_ESCRITAS_CONDICIONAIS = ("update", "delete")
_LOCK_DO_LOOKUP = {"update": "FOR UPDATE", "delete": "FOR UPDATE"}


def _escrever(
    repositorio: PostgresJobFunctionRepository, metodo: str, lida: UnitEnablement
) -> None:
    """Renomeia ou apaga `f1` com a habilitação `lida` como condição."""
    if metodo == "update":
        repositorio.update(
            JobFunction(id=_F1, tenant_id=_A, name="Chef", unit_enablement=lida), expected=lida
        )
    else:
        repositorio.delete(_A, _F1, expected=lida)


@pytest.mark.parametrize("metodo", _ESCRITAS_CONDICIONAIS)
def test_issue_207_escrita_bloqueia_no_lookup_e_nao_depois(
    motores: Callable[[], Engine], metodo: str
) -> None:
    """A comparação decide sob o lock — a mesma prova da #206 para `update_enablement`."""
    motor_adapter = motores()
    motor_bloqueador = motores()
    _semear_funcao_em_a(motor_adapter)
    repositorio = PostgresJobFunctionRepository(motor_adapter)

    with motor_bloqueador.begin() as bloqueador:
        bloqueador.execute(
            text("SELECT id FROM job_functions WHERE id = :f AND tenant_id = :t FOR UPDATE"),
            {"f": _F1, "t": _A},
        )
        with (
            _statements_de(motor_adapter) as (tentados, concluidos),
            pytest.raises(OperationalError) as excecao,
        ):
            _escrever(repositorio, metodo, _SO_A)

    assert getattr(excecao.value.orig, "sqlstate", None) == "55P03"
    assert tentados, "o adapter nem chegou a emitir statement"
    assert _LOCK_DO_LOOKUP[metodo] in tentados[-1], "o adapter bloqueou em outro statement"
    assert concluidos == [], "algum statement completou antes do lock"


@pytest.mark.parametrize("metodo", _ESCRITAS_CONDICIONAIS)
def test_issue_207_escrita_que_espera_uma_alteracao_de_unidades_a_rele_e_e_recusada(
    motores: Callable[[], Engine], metodo: str
) -> None:
    """O cenário da issue no banco: o gerente de A leu `{A}`; o dono alarga para `{A, B}`.

    A primeira conexão prende a linha e acrescenta B **sem comitar**; a escrita do
    gerente, numa thread, fica parada no lock com a leitura antiga. Só então a
    primeira comita. Com a comparação sob o lock, a escrita relê `{A, B}` e recusa —
    a função não é renomeada nem apagada em B, que o gerente não alcança. Para o
    `delete` é também a prova de que a remontagem sob lock não rasga: a alteração
    comita durante a espera e a leitura vê flag e vínculos do mesmo instante.
    """
    motor_primeira = motores()
    motor_segunda = motores()
    motor_observador = motores()
    _semear_funcao_em_a(motor_primeira)
    erros: list[BaseException] = []

    def _escrita_do_gerente() -> None:
        try:
            _escrever(PostgresJobFunctionRepository(motor_segunda), metodo, _SO_A)
        except BaseException as erro:  # o teste inspeciona o tipo
            erros.append(erro)

    with motor_primeira.begin() as primeira:
        primeira.execute(
            text("SELECT id FROM job_functions WHERE id = :f AND tenant_id = :t FOR UPDATE"),
            {"f": _F1, "t": _A},
        )
        primeira.execute(
            text(
                "INSERT INTO job_function_units (job_function_id, tenant_id, unit_id) "
                "VALUES (:f, :t, :u)"
            ),
            {"f": _F1, "t": _A, "u": _UB},
        )
        segunda = threading.Thread(target=_escrita_do_gerente)
        segunda.start()
        _esperar_backend_bloqueado(motor_observador)
    segunda.join(_TIMEOUT_SINCRONIA)

    assert not segunda.is_alive(), "a escrita do gerente não terminou"
    assert len(erros) == 1, erros
    assert isinstance(erros[0], JobFunctionEnablementChangedError), erros
    gravada = PostgresJobFunctionRepository(motor_observador).find_by_id(_A, _F1)
    assert gravada is not None, "a função foi apagada com a leitura antiga"
    assert (gravada.name, gravada.unit_enablement) == ("Cozinheiro", _A_E_B)


@pytest.mark.parametrize("metodo", _ESCRITAS_CONDICIONAIS)
def test_issue_207_escrita_que_espera_conjunto_para_todas_nao_responde_422_por_corrida(
    motores: Callable[[], Engine], metodo: str
) -> None:
    """A propriedade da #225 na forma nova: a corrida nunca vira 422 espúrio.

    O teste da #225 que este PR trocou provava que o lookup de `delete`, sem lock,
    não levantava `InvalidUnitEnablementError` quando `{A}` → todas comitava entre a
    linha e os vínculos. Com a remontagem de volta, sob o lock, é a transição que
    **muda a flag** que pode rasgar: flag antiga (`false`) com os vínculos novos
    (nenhum). A primeira conexão prende a linha, liga a flag e apaga os vínculos
    **sem comitar**; a escrita, numa thread, para no lock com a leitura `{A}`. Depois
    do commit, o `SELECT … FOR UPDATE` devolve a versão nova da linha (PostgreSQL 16
    §13.3.2: "will then lock and return the updated row"), e a consulta dos vínculos
    abre snapshot novo: a escrita vê todas, coerente, e recusa por mudança — nem
    422, nem renomeação ou remoção sobre a leitura antiga.
    """
    motor_primeira = motores()
    motor_segunda = motores()
    motor_observador = motores()
    _semear_funcao_em_a(motor_primeira)
    erros: list[BaseException] = []

    def _escrita_do_gerente() -> None:
        try:
            _escrever(PostgresJobFunctionRepository(motor_segunda), metodo, _SO_A)
        except BaseException as erro:  # o teste inspeciona o tipo
            erros.append(erro)

    with motor_primeira.begin() as primeira:
        primeira.execute(
            text("SELECT id FROM job_functions WHERE id = :f AND tenant_id = :t FOR UPDATE"),
            {"f": _F1, "t": _A},
        )
        primeira.execute(
            text(
                "UPDATE job_functions SET enabled_in_all_units = true "
                "WHERE id = :f AND tenant_id = :t"
            ),
            {"f": _F1, "t": _A},
        )
        primeira.execute(
            text("DELETE FROM job_function_units WHERE job_function_id = :f AND tenant_id = :t"),
            {"f": _F1, "t": _A},
        )
        segunda = threading.Thread(target=_escrita_do_gerente)
        segunda.start()
        _esperar_backend_bloqueado(motor_observador)
    segunda.join(_TIMEOUT_SINCRONIA)

    assert not segunda.is_alive(), "a escrita do gerente não terminou"
    assert len(erros) == 1, erros
    assert not isinstance(erros[0], InvalidUnitEnablementError), "422 espúrio por corrida"
    assert isinstance(erros[0], JobFunctionEnablementChangedError), erros
    gravada = PostgresJobFunctionRepository(motor_observador).find_by_id(_A, _F1)
    assert gravada is not None, "a função foi apagada com a leitura antiga"
    assert (gravada.name, gravada.unit_enablement) == ("Cozinheiro", _TODAS)


# ---------------------------------------------------------------------------
# Stage 3.10 — as escritas condicionais ao lido decidem sob o lock (CA10)
# ---------------------------------------------------------------------------
#
# A forma da corrida de dois R17 acima, para as três leis novas (ADR 3.10.0001
# §2): outra transação muda o vínculo e **não comita**; a escrita da Stage roda
# numa thread e fica parada no lock; só então a outra comita. Com a guarda sob o
# lock, a escrita rele o gravado e recusa com `EmployeeLoginChangedError`. Sem o
# `FOR UPDATE`, ela leria o estado velho, esperaria só no `UPDATE` e gravaria por
# cima — o contrato sequencial não enxerga essa diferença.

_LOGIN_LIDO = UserId("login-lido")
_LOGIN_CONCORRENTE = UserId("login-concorrente")


def _desligar_conforme_lido(repositorio: PostgresEmployeeRepository) -> None:
    """L-DEACT: o R13 leu o registro **sem** vínculo (a ordem inversa do ADR 0.0.0010)."""
    repositorio.deactivate(_A, _U1, _E1, expected_user_id=None, expected_active=True)


def _trocar_conforme_lido(repositorio: PostgresEmployeeRepository) -> None:
    """L-RELINK: um segundo R19 que leu o login antigo."""
    repositorio.relink_login(
        _A, _U1, _E1, expected_user_id=_LOGIN_LIDO, user_id=UserId("login-do-segundo")
    )


def _desvincular_conforme_lido(repositorio: PostgresEmployeeRepository) -> None:
    """L-UNLINK: um R20 que leu o login antigo, concorrente a uma troca."""
    repositorio.unlink_login(_A, _U1, _E1, expected_user_id=_LOGIN_LIDO, expected_active=True)


@pytest.mark.parametrize(
    ("vinculo_inicial", "escrita"),
    [
        (None, _desligar_conforme_lido),
        (_LOGIN_LIDO, _trocar_conforme_lido),
        (_LOGIN_LIDO, _desvincular_conforme_lido),
    ],
    ids=["l_deact_vinculo_concorrente", "l_relink_troca_concorrente", "l_unlink_troca_concorrente"],
)
def test_stage_3_10_escrita_condicional_rele_o_vinculo_sob_o_lock(
    motores: Callable[[], Engine],
    vinculo_inicial: UserId | None,
    escrita: Callable[[PostgresEmployeeRepository], None],
) -> None:
    """Uma escrita concorrente comita enquanto a da Stage espera o lock: a da Stage recusa.

    O registro termina **ativo** e com o vínculo da escrita concorrente — no caso
    de L-DEACT, ativo **e** vinculado, em vez de desligado e vinculado a um login
    que nenhuma revogação considerou.
    """
    motor_concorrente = motores()
    motor_stage = motores()
    motor_observador = motores()
    _semear(motor_concorrente)
    if vinculo_inicial is not None:
        PostgresEmployeeRepository(motor_concorrente).link_login(_A, _U1, _E1, vinculo_inicial)
    erros: list[BaseException] = []

    def _escrita_da_stage() -> None:
        try:
            escrita(PostgresEmployeeRepository(motor_stage))
        except BaseException as erro:  # o teste inspeciona o tipo
            erros.append(erro)

    with motor_concorrente.begin() as concorrente:
        concorrente.execute(
            text("UPDATE employees SET user_id = :u WHERE id = :e AND tenant_id = :t"),
            {"u": _LOGIN_CONCORRENTE, "e": _E1, "t": _A},
        )
        thread = threading.Thread(target=_escrita_da_stage)
        thread.start()
        _esperar_backend_bloqueado(motor_observador)
    thread.join(_TIMEOUT_SINCRONIA)

    assert not thread.is_alive(), "a escrita da Stage não terminou"
    assert len(erros) == 1, erros
    assert isinstance(erros[0], EmployeeLoginChangedError), erros
    relido = PostgresEmployeeRepository(motor_observador).find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert (relido.user_id, relido.active) == (_LOGIN_CONCORRENTE, True), (
        "a escrita da Stage gravou sobre o vínculo concorrente"
    )
