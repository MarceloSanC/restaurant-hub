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
from restaurant_hub.features.staff.application.errors import (
    EmployeeAlreadyExistsError,
    JobFunctionInUseError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule

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

# `list_by_tenant` e `find_all_by_ids` — as duas listagens que `L-ORD` governa no
# port de função. Se uma terceira nascer, esta constante é o lugar que reclama.
_LISTAGENS_DO_PORT_DE_FUNCAO = 2


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
        funcionarios.list_by_unit(_A, _U1)

    listagens_de_funcao = [
        statement
        for statement in tentados
        if "FROM job_functions" in statement and "ORDER BY" in statement
    ]
    assert len(listagens_de_funcao) == _LISTAGENS_DO_PORT_DE_FUNCAO, (
        "as duas listagens de função têm de ordenar"
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
    - **sem** cláusula bate também — é o falso verde desta imagem, medido aqui e
      não suposto;
    - `COLLATE "und-x-icu"` **diverge** (`Álvaro` antes de `ana`, minúscula antes
      de maiúscula) — é a prova de que a escolha de colação decide o resultado, e
      de que o dia em que o banco tiver colação linguística a omissão deixa de
      ser inócua.
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

    esperado = sorted(nomes)
    assert _ordenado_por('ORDER BY name COLLATE "C"') == esperado
    assert _ordenado_por("ORDER BY name") == esperado, (
        "o falso verde desta imagem: sem cláusula o resultado é idêntico"
    )
    assert _ordenado_por('ORDER BY name COLLATE "und-x-icu"') != esperado, (
        "se esta colação não divergisse, a cláusula seria de fato inócua"
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
        return repositorio.find_by_id(_A, _E1)
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
    46 de lei — e foi medida contra o banco real produzindo `40P01
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
            PostgresJobFunctionRepository(motor_b).delete(_A, _F2)
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

    gravado = PostgresEmployeeRepository(motor_a).find_by_id(_A, _E1)
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
            PostgresJobFunctionRepository(motor_b).delete(_A, _F2)
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
    gravado = repositorio.find_by_id(_A, _E1)
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

    Fecha o outro ramo de `_detalhe_do_conflito` — o que devolve a id — e a
    outra entrada de `ON_WRITE_EMPLOYEE`. Aqui a mensagem cita a id porque o
    adapter **sabe** qual é: é a que ele tentou gravar, e a constraint violada é
    de identidade, não de referência. É o contraste com o teste do conjunto que
    torna a escolha de `_detalhe_do_conflito` observável em vez de estilística.
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
