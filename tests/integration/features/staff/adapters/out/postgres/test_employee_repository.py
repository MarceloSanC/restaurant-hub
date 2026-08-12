"""`PostgresEmployeeRepository` contra o banco real — L-E1…L-E7, `L-ORD`, CA16 e CA17.

**Por que estes testes existem se a suíte de contrato roda as mesmas leis contra
o mesmo adapter na Task 09.** As duas razões do arquivo irmão
(`test_job_function_repository.py`) valem aqui, e uma terceira entra:

1. **Ordem de descoberta.** A Task 09 é o único lugar onde uma lei pode reprovar
   por divergência fake↔adapter; se o adapter chegasse lá sem nunca ter tocado o
   banco, um vermelho seria ambíguo entre "o adapter está errado" e "a lei está
   errada".
2. **O que só o banco decide.** O `CASCADE` das três filhas, o `rowcount` de um
   `UPDATE`/`DELETE` que não achou linha, a ordem sob a colação real e o
   round-trip de `NUMERIC`/`TIMESTAMP` não têm contrapartida no fake.
3. **O que só existe fora do contrato** (§5.19): CA16 e CA17 gravam linhas por
   **SQL direto**, o que nenhuma implementação do port sabe fazer — CA16 porque
   o ponto é justamente a linha que o port **não** produziria, e CA17 porque o
   sujeito é a coluna, não a lei.

**O que NÃO está aqui, de propósito.** A conduta — `FOR UPDATE`, snapshot único,
a regressão de deadlock da escrita por diferença e a asserção sobre a cláusula
`COLLATE` — é a Task 08, e por uma razão de método: nenhuma delas é distinguível
de sua ausência por asserção sobre **estado final**, que é o que este arquivo
faz. E a ordem `L-E1` antes de `L-E4` (CA5b) é a Task 09, onde vale para as duas
implementações.
"""

import dataclasses
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text

from restaurant_hub.features.staff.adapters.out.postgres.employee_repository import (
    PostgresEmployeeRepository,
)
from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from restaurant_hub.features.staff.application.errors import (
    EmployeeAlreadyExistsError,
    EmployeeNotFoundError,
    EmployeeRelocationError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmptyJobFunctionsError,
    InvalidNameError,
    OverlappingUnavailabilityError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
)

pytestmark = [pytest.mark.integration]

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_E1 = EmployeeId("e1")
_E2 = EmployeeId("e2")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")
_F3 = JobFunctionId("f3")

# Microssegundos "difíceis" de CA17: a coluna é `TIMESTAMP` sem precisão
# declarada, cujo default no Postgres é microssegundo — a mesma do `datetime`.
# Uma precisão reduzida truncaria em silêncio, e o round-trip devolveria outro
# instante sem ninguém notar.
_MICROS_INICIO = 123456
_MICROS_FIM = 999999


@pytest.fixture
def repositorio(banco_limpo: Engine) -> PostgresEmployeeRepository:
    """O adapter sobre o `Engine` de teste, com as tabelas vazias."""
    return PostgresEmployeeRepository(banco_limpo)


@pytest.fixture
def funcoes(banco_limpo: Engine) -> PostgresJobFunctionRepository:
    """Funções semeadas: `f1`/`f2`/`f3` em A, e `f1` **também** em B.

    Usa o adapter de função — não SQL direto — porque ele já existe (Task 06) e é
    o produtor legítimo dessas linhas. A homônima de outro tenant é o que torna
    testável "id que existe, mas em outro restaurante, conta como ausente".
    """
    repositorio = PostgresJobFunctionRepository(banco_limpo)
    repositorio.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    repositorio.add(JobFunction(id=_F2, tenant_id=_A, name="Chapeiro"))
    repositorio.add(JobFunction(id=_F3, tenant_id=_A, name="Garçom"))
    repositorio.add(JobFunction(id=JobFunctionId("fb"), tenant_id=_B, name="Cozinheiro"))
    return repositorio


_BASE = Employee(
    id=_E1,
    tenant_id=_A,
    unit_id=_U1,
    name="Maria",
    workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
    shift_preference=None,
    job_function_ids=frozenset({_F1}),
)


def _funcionario(id_: EmployeeId = _E1, **campos: object) -> Employee:
    """Funcionário-base com os campos pedidos sobrescritos.

    Os `**campos` levam os nomes **reais** dos atributos de `Employee` de
    propósito: uma tabela de tradução (`funcoes=` → `job_function_ids=`) seria um
    lugar a mais onde um campo pode ser esquecido em silêncio quando a entidade
    ganhar outro. E `dataclasses.replace` revalida pelo `__post_init__`, então o
    helper não constrói agregado inválido sem que a construção reclame.
    """
    return dataclasses.replace(_BASE, id=id_, **campos)


def _periodo(dia: int, *, hora_final: int = 12) -> UnavailabilityPeriod:
    return UnavailabilityPeriod(
        start=datetime(2026, 3, dia, 8, 0), end=datetime(2026, 3, dia, hora_final, 0)
    )


def _contar(engine: Engine, tabela: str, employee_id: str) -> int:
    with engine.connect() as conexao:
        return int(
            conexao.execute(
                text(f"SELECT count(*) FROM {tabela} WHERE employee_id = :e"),
                {"e": employee_id},
            ).scalar_one()
        )


# ---------------------------------------------------------------------------
# L-E1 — `add` é inserção, com o agregado inteiro numa transação
# ---------------------------------------------------------------------------


def test_l_e1_add_grava_o_agregado_inteiro_e_e_lido_de_volta(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """As quatro tabelas numa escrita só, e a releitura devolve o mesmo agregado."""
    original = _funcionario(
        job_function_ids=frozenset({_F1, _F2}),
        shift_preference=ShiftPreference(periods=frozenset({DayPeriod.MORNING, DayPeriod.NIGHT})),
        unavailabilities=(_periodo(10), _periodo(12)),
    )
    repositorio.add(original)

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.name == "Maria"
    assert gravado.unit_id == _U1
    assert gravado.job_function_ids == frozenset({_F1, _F2})
    assert gravado.shift_preference == original.shift_preference
    assert gravado.unavailabilities == (_periodo(10), _periodo(12))
    assert gravado.active is True


def test_l_e1_add_sem_preferencia_e_sem_indisponibilidade_reidrata_none_e_vazio(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """Sem linha em `employee_shift_preferences` ⇒ `None`, não preferência vazia.

    "Nenhuma linha" e "preferência vazia" **não** são dois estados
    (ADR 3.1.0004) — e é o único que o schema representa.
    """
    repositorio.add(_funcionario())

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.shift_preference is None
    assert gravado.unavailabilities == ()


def test_l_e1_add_com_jornada_sob_demanda_nao_grava_carga(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """O **iff** da jornada, das duas pontas: `on_demand` volta sem horas."""
    repositorio.add(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=OnDemand(),
            shift_preference=None,
            job_function_ids=frozenset({_F1}),
        )
    )

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.workload_profile == OnDemand()


def test_l_e1_add_com_id_ja_gravado_e_erro_e_nao_altera_o_registro(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """`add` é inserção, nunca upsert — um upsert silencioso passaria em "não explodiu"."""
    repositorio.add(_funcionario())
    with pytest.raises(EmployeeAlreadyExistsError) as excecao:
        repositorio.add(_funcionario(name="Joana", job_function_ids=frozenset({_F2})))
    assert "e1" in str(excecao.value)

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.name == "Maria"
    assert gravado.job_function_ids == frozenset({_F1})


def test_l_e1_add_com_id_gravado_em_outro_tenant_tambem_e_erro(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """A colisão de **id** é global: a PK de `employees` não inclui o tenant.

    Um lookup escopado por tenant na guarda aceitaria esta entrada e só bateria
    na PK depois — com o erro certo, mas fora da ordem que a §5.5 fixa.
    """
    repositorio.add(_funcionario())
    with pytest.raises(EmployeeAlreadyExistsError):
        repositorio.add(
            _funcionario(tenant_id=_B, job_function_ids=frozenset({JobFunctionId("fb")}))
        )


# ---------------------------------------------------------------------------
# L-E4 — validade referencial do conjunto de funções
# ---------------------------------------------------------------------------


def test_l_e4_add_com_funcao_inexistente_nao_grava_nada(
    repositorio: PostgresEmployeeRepository,
    funcoes: PostgresJobFunctionRepository,
    banco_limpo: Engine,
) -> None:
    """E **nada** fica gravado: a transação inteira reverte, filhas inclusive."""
    with pytest.raises(JobFunctionNotFoundError) as excecao:
        repositorio.add(_funcionario(job_function_ids=frozenset({_F1, JobFunctionId("f99")})))
    assert "f99" in str(excecao.value)

    assert repositorio.find_by_id(_A, _E1) is None
    assert _contar(banco_limpo, "employee_job_functions", "e1") == 0


def test_l_e4_funcao_de_outro_tenant_conta_como_ausente(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """`fb` **existe** — em B. Para A é indistinguível de inexistente (§5.4).

    A alternativa (aceitar, ou responder outro erro) vazaria a existência da
    função do restaurante alheio; a FK composta a recusaria de todo jeito, mas
    depois, e com erro não previsto pelo contrato.
    """
    with pytest.raises(JobFunctionNotFoundError) as excecao:
        repositorio.add(_funcionario(job_function_ids=frozenset({JobFunctionId("fb")})))
    assert "fb" in str(excecao.value)


def test_l_e4_reporta_a_menor_id_ausente_de_forma_deterministica(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """§5.15 — com duas ausentes, a mensagem cita `'f97'` em **toda** execução.

    Sem o `sorted()` na pré-checagem, `frozenset` itera por `PYTHONHASHSEED` e
    esta asserção falharia de forma **intermitente** — que é como um requisito
    de determinismo vira "flakiness" e some do radar.
    """
    with pytest.raises(JobFunctionNotFoundError) as excecao:
        repositorio.add(
            _funcionario(
                job_function_ids=frozenset({_F1, JobFunctionId("f99"), JobFunctionId("f97")})
            )
        )
    assert "f97" in str(excecao.value)
    assert "f99" not in str(excecao.value)


def test_l_e4_vale_no_update_e_nao_grava_nada(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    repositorio.add(_funcionario())
    with pytest.raises(JobFunctionNotFoundError):
        repositorio.update(
            _funcionario(name="Joana", job_function_ids=frozenset({JobFunctionId("f99")}))
        )

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.name == "Maria"
    assert gravado.job_function_ids == frozenset({_F1})


# ---------------------------------------------------------------------------
# L-E2 / L-E3 — `update` e a localização imutável
# ---------------------------------------------------------------------------


def test_l_e2_update_grava_o_agregado_inteiro(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """Nome, perfil, preferência, conjunto, períodos **e** estado, de uma vez."""
    repositorio.add(_funcionario(unavailabilities=(_periodo(10),)))
    repositorio.update(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria Silva",
            workload_profile=OnDemand(),
            shift_preference=ShiftPreference(periods=frozenset({DayPeriod.AFTERNOON})),
            job_function_ids=frozenset({_F2, _F3}),
            unavailabilities=(_periodo(12), _periodo(14)),
            active=False,
        )
    )

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.name == "Maria Silva"
    assert gravado.workload_profile == OnDemand()
    assert gravado.shift_preference == ShiftPreference(periods=frozenset({DayPeriod.AFTERNOON}))
    assert gravado.job_function_ids == frozenset({_F2, _F3})
    assert gravado.unavailabilities == (_periodo(12), _periodo(14))
    assert gravado.active is False


def test_update_escreve_as_filhas_por_diferenca_e_o_resultado_e_o_conjunto_pedido(
    repositorio: PostgresEmployeeRepository,
    funcoes: PostgresJobFunctionRepository,
    banco_limpo: Engine,
) -> None:
    """§5.20 — o **estado final** da escrita por diferença, com interseção não-vazia.

    Este teste **não** distingue diferença de reescrita cega (o estado final é o
    mesmo, e é exatamente por isso que a §5.20 precisa da regressão de deadlock
    da Task 08). O que ele trava é que a diferença está **correta**: com `{f1,f2}`
    virando `{f2,f3}`, o `f2` que permanece não pode sumir junto com o `f1` que
    sai, nem duplicar junto com o `f3` que entra — a PK (`employee_id`,
    `job_function_id`) recusaria a duplicata e a suíte veria o erro, mas a perda
    silenciosa do `f2` só aparece aqui.
    """
    repositorio.add(_funcionario(job_function_ids=frozenset({_F1, _F2})))
    repositorio.update(_funcionario(job_function_ids=frozenset({_F2, _F3})))

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.job_function_ids == frozenset({_F2, _F3})
    assert _contar(banco_limpo, "employee_job_functions", "e1") == len(gravado.job_function_ids)


def test_update_que_nao_muda_nada_nas_filhas_preserva_as_filhas(
    repositorio: PostgresEmployeeRepository,
    funcoes: PostgresJobFunctionRepository,
    banco_limpo: Engine,
) -> None:
    """O caminho em que a diferença é **vazia** nas três filhas.

    É o cenário da regressão de deadlock (Task 08): um `update` que só mexe no
    nome não deve tocar vínculo nenhum. Aqui se trava só o resultado — que as
    filhas sobrevivem; que nenhum statement foi emitido é o que a Task 08 mede.
    """
    repositorio.add(
        _funcionario(
            job_function_ids=frozenset({_F1, _F2}),
            shift_preference=ShiftPreference(periods=frozenset({DayPeriod.MORNING})),
            unavailabilities=(_periodo(10),),
        )
    )
    repositorio.update(
        _funcionario(
            name="Maria Silva",
            job_function_ids=frozenset({_F1, _F2}),
            shift_preference=ShiftPreference(periods=frozenset({DayPeriod.MORNING})),
            unavailabilities=(_periodo(10),),
        )
    )

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.name == "Maria Silva"
    assert gravado.job_function_ids == frozenset({_F1, _F2})
    assert gravado.unavailabilities == (_periodo(10),)
    assert _contar(banco_limpo, "employee_job_functions", "e1") == len(gravado.job_function_ids)
    assert _contar(banco_limpo, "employee_shift_preferences", "e1") == 1


def test_update_de_periodo_que_muda_so_o_fim_reescreve_a_linha_da_mesma_pk(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """O caso em que a chave da linha velha e a da nova **coincidem**.

    `start_at` é a PK junto do funcionário. Um período cujo `end` mudou aparece
    como "removido" e "acrescentado" com o **mesmo** `start_at`, e é por isso que
    o `DELETE` precisa vir antes do `INSERT`: na ordem inversa a PK recusaria.
    """
    repositorio.add(_funcionario(unavailabilities=(_periodo(10),)))
    repositorio.update(_funcionario(unavailabilities=(_periodo(10, hora_final=18),)))

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.unavailabilities == (_periodo(10, hora_final=18),)


def test_update_que_limpa_preferencia_e_periodos_apaga_as_filhas(
    repositorio: PostgresEmployeeRepository,
    funcoes: PostgresJobFunctionRepository,
    banco_limpo: Engine,
) -> None:
    """Diferença **só de remoção**: `None` de preferência apaga as linhas."""
    repositorio.add(
        _funcionario(
            shift_preference=ShiftPreference(
                periods=frozenset({DayPeriod.MORNING, DayPeriod.NIGHT})
            ),
            unavailabilities=(_periodo(10), _periodo(12)),
        )
    )
    repositorio.update(_funcionario())

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.shift_preference is None
    assert gravado.unavailabilities == ()
    assert _contar(banco_limpo, "employee_shift_preferences", "e1") == 0
    assert _contar(banco_limpo, "employee_unavailabilities", "e1") == 0


def test_l_e2_update_de_funcionario_inexistente_nao_grava_nada(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    with pytest.raises(EmployeeNotFoundError):
        repositorio.update(_funcionario())
    assert repositorio.find_by_id(_A, _E1) is None


def test_l_e2_update_com_tenant_alheio_nao_grava_nada(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    repositorio.add(_funcionario())
    with pytest.raises(EmployeeNotFoundError):
        repositorio.update(_funcionario(tenant_id=_B, name="Joana"))

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.name == "Maria"


def test_l_e3_update_com_unidade_divergente_no_mesmo_tenant_e_relocacao(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """Erro **nomeado**: sem ele a saída seria mover ou descartar em silêncio."""
    repositorio.add(_funcionario())
    with pytest.raises(EmployeeRelocationError) as excecao:
        repositorio.update(_funcionario(unit_id=_U2, name="Joana"))
    assert "u1" in str(excecao.value)
    assert "u2" in str(excecao.value)

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.unit_id == _U1
    assert gravado.name == "Maria"


def test_l_e3_not_found_vence_relocacao_com_tenant_alheio(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """O caso que discrimina a ordem das duas guardas (§5.4 vence L-E3).

    Tenant **e** unidade divergem. `EmployeeRelocationError` confirmaria que o
    registro existe **e** vazaria a unidade em que ele está — no restaurante do
    outro. Só a ordem "lookup por `(tenant_id, id)` primeiro" evita isso, e este
    é o único caso em que as duas respostas diferem.
    """
    repositorio.add(_funcionario())
    with pytest.raises(EmployeeNotFoundError):
        repositorio.update(_funcionario(tenant_id=_B, unit_id=_U2))


def test_update_nao_move_o_funcionario_de_tenant_nem_de_unidade(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """§5.3 / L-E3 pelo outro lado: depois de um `update` legítimo, os dois ficam.

    Um `SET tenant_id = …, unit_id = …` passaria em **todos** os outros testes
    deste arquivo, porque em todos eles os valores enviados coincidem com os
    gravados. Aqui se confirma que as colunas não entram no `SET`.
    """
    repositorio.add(_funcionario())
    repositorio.update(_funcionario(name="Maria Silva"))

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.tenant_id == _A
    assert gravado.unit_id == _U1
    assert repositorio.find_by_id(_B, _E1) is None


# ---------------------------------------------------------------------------
# L-E5 — remoção definitiva, com as filhas em cascata
# ---------------------------------------------------------------------------


def test_l_e5_delete_remove_o_registro_e_as_tres_filhas_em_cascata(
    repositorio: PostgresEmployeeRepository,
    funcoes: PostgresJobFunctionRepository,
    banco_limpo: Engine,
) -> None:
    """§5.10 — os filhos do agregado somem com o agregado, pelo `CASCADE` do banco."""
    repositorio.add(
        _funcionario(
            job_function_ids=frozenset({_F1, _F2}),
            shift_preference=ShiftPreference(periods=frozenset({DayPeriod.MORNING})),
            unavailabilities=(_periodo(10),),
        )
    )
    repositorio.delete(_A, _E1)

    assert repositorio.find_by_id(_A, _E1) is None
    assert _contar(banco_limpo, "employee_job_functions", "e1") == 0
    assert _contar(banco_limpo, "employee_unavailabilities", "e1") == 0
    assert _contar(banco_limpo, "employee_shift_preferences", "e1") == 0


def test_l_e5_delete_de_funcionario_inexistente_e_not_found(
    repositorio: PostgresEmployeeRepository,
) -> None:
    with pytest.raises(EmployeeNotFoundError):
        repositorio.delete(_A, _E1)


def test_l_e5_delete_com_tenant_alheio_e_not_found_e_nao_remove(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    repositorio.add(_funcionario())
    with pytest.raises(EmployeeNotFoundError):
        repositorio.delete(_B, _E1)
    assert repositorio.find_by_id(_A, _E1) is not None


def test_l_e5_remover_o_funcionario_libera_a_funcao_que_ele_referenciava(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """A outra ponta do `RESTRICT` de L-JF3: sem referência, a função sai.

    Antes do `delete` do funcionário a função está travada; depois, não. É o par
    completo das duas leis contra o banco, que nenhuma das duas suítes vê
    sozinha.
    """
    repositorio.add(_funcionario())
    assert repositorio.exists_by_job_function(_A, _F1) is True

    repositorio.delete(_A, _E1)

    assert repositorio.exists_by_job_function(_A, _F1) is False
    funcoes.delete(_A, _F1)
    assert funcoes.find_by_id(_A, _F1) is None


# ---------------------------------------------------------------------------
# L-E6 — listagem por unidade, e o estado
# ---------------------------------------------------------------------------


def test_l_e6_list_by_unit_devolve_so_a_unidade_pedida_e_so_ativos(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    repositorio.add(_funcionario(_E1, name="Ana"))
    repositorio.add(_funcionario(_E2, unit_id=_U2, name="Bruno"))
    repositorio.add(_funcionario(EmployeeId("e3"), name="Carla", active=False))

    listados = repositorio.list_by_unit(_A, _U1)

    assert [funcionario.id for funcionario in listados] == [_E1]


def test_l_e6_include_inactive_traz_o_desligado_sem_perder_a_historia(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """Desligar não apaga (ADR 3.2.0006): o registro volta com tudo."""
    repositorio.add(
        _funcionario(
            _E2,
            name="Bruno",
            job_function_ids=frozenset({_F1, _F2}),
            unavailabilities=(_periodo(10),),
            active=False,
        )
    )
    repositorio.add(_funcionario(_E1, name="Ana"))

    assert [funcionario.id for funcionario in repositorio.list_by_unit(_A, _U1)] == [_E1]

    com_inativos = repositorio.list_by_unit(_A, _U1, include_inactive=True)
    assert [funcionario.id for funcionario in com_inativos] == [_E1, _E2]
    desligado = com_inativos[1]
    assert desligado.active is False
    assert desligado.job_function_ids == frozenset({_F1, _F2})
    assert desligado.unavailabilities == (_periodo(10),)


def test_l_e6_list_by_unit_nao_atravessa_tenant(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """Mesma unidade, tenant diferente: `unit_id` é opaco e pode coincidir."""
    repositorio.add(_funcionario(_E1, name="Ana"))
    repositorio.add(
        _funcionario(
            _E2, tenant_id=_B, name="Bruno", job_function_ids=frozenset({JobFunctionId("fb")})
        )
    )

    assert [funcionario.id for funcionario in repositorio.list_by_unit(_A, _U1)] == [_E1]
    assert [funcionario.id for funcionario in repositorio.list_by_unit(_B, _U1)] == [_E2]


def test_list_by_unit_sem_ninguem_devolve_vazio(
    repositorio: PostgresEmployeeRepository,
) -> None:
    """O caminho em que não há id para as consultas das filhas resolverem."""
    assert repositorio.list_by_unit(_A, _U1) == ()


# ---------------------------------------------------------------------------
# L-E7 — a consulta que sustenta a guarda de remoção da função
# ---------------------------------------------------------------------------


def test_l_e7_exists_by_job_function_e_tenant_wide_e_ignora_estado_e_unidade(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """§5.16 — desligado em **outra** unidade ainda conta como referência.

    É a combinação que um `JOIN employees … WHERE active AND unit_id = …`
    responderia errado, e responderia errado de forma plausível: a função
    pareceria livre e seria apagada, deixando o cadastro do desligado apontando
    para função inexistente.
    """
    repositorio.add(
        _funcionario(
            _E2, unit_id=_U2, name="Bruno", job_function_ids=frozenset({_F2}), active=False
        )
    )

    assert repositorio.exists_by_job_function(_A, _F2) is True
    assert repositorio.exists_by_job_function(_A, _F3) is False


def test_l_e7_referencia_de_outro_tenant_devolve_false(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    repositorio.add(_funcionario())
    assert repositorio.exists_by_job_function(_A, _F1) is True
    assert repositorio.exists_by_job_function(_B, _F1) is False


# ---------------------------------------------------------------------------
# L-ORD — a ordem total da listagem e a dos períodos dentro do agregado
# ---------------------------------------------------------------------------


def test_l_ord_list_by_unit_ordena_por_codepoint_desempatando_por_id(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """`L-ORD` contra o banco real, com o desempate **alcançável**.

    Ao contrário do port de função — onde o índice único torna homônimos
    irrepresentáveis —, aqui nome não é único (concept 3.1 §5.2): `"Ana"`
    aparece duas vezes e só o `id` decide. Dado adversarial: maiúscula antes de
    minúscula, o acentuado (U+00C1) **depois** de `"ana"` (U+0061), e o espaço à
    direita depois do prefixo.

    Esta asserção **não** reprova a omissão do `COLLATE "C"` nesta imagem (musl,
    cuja colação default já é byte-order); quem reprova é a asserção sobre o SQL
    compilado, na Task 08. Aqui se confirma que o resultado bate com o
    `sorted()` do Python, que é o que permite o corpo único da suíte de contrato.
    """
    for id_, name in (
        ("e5", "Zeus"),
        ("e1", "Álvaro"),
        ("e3", "ana"),
        ("e2", "Ana"),
        ("e4", "Zeus "),
        ("e6", "Ana"),
    ):
        repositorio.add(_funcionario(EmployeeId(id_), name=name))

    listados = repositorio.list_by_unit(_A, _U1)

    assert [(funcionario.name, funcionario.id) for funcionario in listados] == [
        ("Ana", "e2"),
        ("Ana", "e6"),
        ("Zeus", "e5"),
        ("Zeus ", "e4"),
        ("ana", "e3"),
        ("Álvaro", "e1"),
    ]
    assert [(funcionario.name, funcionario.id) for funcionario in listados] == sorted(
        (funcionario.name, funcionario.id) for funcionario in listados
    )


def test_ca11_periodos_inseridos_fora_de_ordem_reidratam_por_start(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """CA11 — `ORDER BY start_at` na reidratação, nos **dois** métodos de agregado.

    O agregado é gravado com os períodos fora de ordem cronológica de propósito:
    `Employee.add_unavailability` concatena e não ordena, então a ordem de
    gravação é a de chegada, e é a leitura que impõe a lei.
    """
    repositorio.add(_funcionario(unavailabilities=(_periodo(14), _periodo(10), _periodo(12))))

    por_id = repositorio.find_by_id(_A, _E1)
    assert por_id is not None
    assert por_id.unavailabilities == (_periodo(10), _periodo(12), _periodo(14))

    (por_listagem,) = repositorio.list_by_unit(_A, _U1)
    assert por_listagem.unavailabilities == (_periodo(10), _periodo(12), _periodo(14))


def test_l_ord_a_listagem_nao_mistura_as_filhas_entre_funcionarios(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """A montagem em lote agrupa por funcionário — e o agrupamento tem de estar certo.

    `list_by_unit` monta N agregados com **quatro** statements, não com `1 + 3N`.
    O ganho vem com um risco próprio: um agrupamento errado devolveria as funções
    de um no agregado do outro, e todo teste de uma linha só passaria.
    """
    repositorio.add(
        _funcionario(
            _E1,
            name="Ana",
            job_function_ids=frozenset({_F1}),
            shift_preference=ShiftPreference(periods=frozenset({DayPeriod.MORNING})),
            unavailabilities=(_periodo(10),),
        )
    )
    repositorio.add(
        _funcionario(
            _E2,
            name="Bruno",
            job_function_ids=frozenset({_F2, _F3}),
            unavailabilities=(_periodo(20), _periodo(22)),
        )
    )

    ana, bruno = repositorio.list_by_unit(_A, _U1)

    assert ana.job_function_ids == frozenset({_F1})
    assert ana.shift_preference == ShiftPreference(periods=frozenset({DayPeriod.MORNING}))
    assert ana.unavailabilities == (_periodo(10),)
    assert bruno.job_function_ids == frozenset({_F2, _F3})
    assert bruno.shift_preference is None
    assert bruno.unavailabilities == (_periodo(20), _periodo(22))


# ---------------------------------------------------------------------------
# CA16 — as três invariantes que o schema NÃO impõe levantam ao serem lidas
# ---------------------------------------------------------------------------


def _gravar_linha_crua(
    engine: Engine,
    *,
    name: str = "Maria",
    com_funcao: bool = True,
    periodos: tuple[tuple[datetime, datetime], ...] = (),
) -> None:
    """Escreve direto nas tabelas, contornando o domínio — o ponto de CA16.

    Nenhuma implementação do port sabe produzir estas linhas; é justamente por
    isso que este teste não pode viver na suíte de contrato.
    """
    with engine.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employees "
                "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
                "VALUES ('e1', 'tenant-a', 'u1', :nome, 'fixed', 44, true)"
            ),
            {"nome": name},
        )
        if com_funcao:
            conexao.execute(
                text(
                    "INSERT INTO job_functions (id, tenant_id, name) "
                    "VALUES ('f1', 'tenant-a', 'Cozinheiro')"
                )
            )
            conexao.execute(
                text(
                    "INSERT INTO employee_job_functions "
                    "(employee_id, job_function_id, tenant_id) "
                    "VALUES ('e1', 'f1', 'tenant-a')"
                )
            )
        for inicio, fim in periodos:
            conexao.execute(
                text(
                    "INSERT INTO employee_unavailabilities (employee_id, start_at, end_at) "
                    "VALUES ('e1', :inicio, :fim)"
                ),
                {"inicio": inicio, "fim": fim},
            )


def test_ca16_funcionario_sem_nenhuma_funcao_levanta_ao_ser_lido(
    repositorio: PostgresEmployeeRepository, banco_limpo: Engine
) -> None:
    """§5.19 — a invariante que nenhuma constraint expressa sem trigger.

    A reidratação passa pelo construtor, e é **só** isso que faz a linha
    corrompida levantar em vez de virar entidade inválida em circulação. Devolver
    um `Employee` sem função aqui seria pior que o erro: o resto do sistema o
    trataria como legítimo.
    """
    _gravar_linha_crua(banco_limpo, com_funcao=False)
    with pytest.raises(EmptyJobFunctionsError):
        repositorio.find_by_id(_A, _E1)


@pytest.mark.parametrize("nome_invalido", ["", "   "])
def test_ca16_nome_vazio_ou_so_espacos_levanta_ao_ser_lido(
    repositorio: PostgresEmployeeRepository, banco_limpo: Engine, nome_invalido: str
) -> None:
    """`TEXT` aceita string vazia; a invariante é do domínio, não do schema."""
    _gravar_linha_crua(banco_limpo, name=nome_invalido)
    with pytest.raises(InvalidNameError):
        repositorio.find_by_id(_A, _E1)


def test_ca16_periodos_sobrepostos_levantam_ao_serem_lidos(
    repositorio: PostgresEmployeeRepository, banco_limpo: Engine
) -> None:
    """A `CHECK` garante `start < end` **por linha**; a não-sobreposição é par a par.

    Expressá-la no schema exigiria `EXCLUDE` com extensão ou trigger — o limite
    declarado em §5.19 —, e é o construtor de `Employee` que a impõe.
    """
    _gravar_linha_crua(
        banco_limpo,
        periodos=(
            (datetime(2026, 3, 10, 8, 0), datetime(2026, 3, 10, 18, 0)),
            (datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 20, 0)),
        ),
    )
    with pytest.raises(OverlappingUnavailabilityError):
        repositorio.find_by_id(_A, _E1)


def test_ca16_a_listagem_tambem_levanta_e_nao_omite_a_linha_corrompida(
    repositorio: PostgresEmployeeRepository, banco_limpo: Engine
) -> None:
    """O outro método que monta agregado. Omitir em silêncio seria pior que levantar.

    Uma listagem que pulasse a linha inválida devolveria uma equipe incompleta
    sem sinal nenhum — e o gerente não tem como saber que falta alguém.
    """
    _gravar_linha_crua(banco_limpo, com_funcao=False)
    with pytest.raises(EmptyJobFunctionsError):
        repositorio.list_by_unit(_A, _U1)


# ---------------------------------------------------------------------------
# CA17 — o round-trip dos dois tipos delicados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("carga", ["22.50", "0.001", "22.555", "44", "168.75"])
def test_ca17_round_trip_preserva_valor_e_escala_do_decimal(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository, carga: str
) -> None:
    """`NUMERIC` **sem precisão declarada** — valor **e** escala voltam intactos.

    Uma `NUMERIC(5,2)` — a escolha "natural" para horas semanais — arredondaria
    em silêncio (`22.555 → 22.56`, `0.001 → 0.00`), e a comparação por igualdade
    de `Decimal` **não** pegaria a mudança de escala (`Decimal("22.5") ==
    Decimal("22.50")` é `True`). Por isso a asserção é sobre a **notação
    posicional**, que é onde a escala aparece.
    """
    repositorio.add(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal(carga)),
            shift_preference=None,
            job_function_ids=frozenset({_F1}),
        )
    )

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    perfil = gravado.workload_profile
    assert isinstance(perfil, FixedSchedule)
    assert format(perfil.weekly_hours, "f") == carga


def test_ca17_round_trip_preserva_datetime_ingenuo_com_microssegundos(
    repositorio: PostgresEmployeeRepository, funcoes: PostgresJobFunctionRepository
) -> None:
    """`TIMESTAMP` sem fuso, e o mapper **não** normaliza — o oposto de identity.

    Um `.astimezone(UTC)` ou `.replace(tzinfo=UTC)` escrito no mapper por
    analogia com identity faria a reidratação levantar
    `InvalidUnavailabilityPeriodError` sobre um dado perfeitamente válido
    (ADR 3.1.0005). E a coluna vai sem precisão declarada porque o default do
    Postgres é microssegundo, a mesma do `datetime`: precisão reduzida truncaria
    em silêncio e o round-trip devolveria outro instante.
    """
    periodo = UnavailabilityPeriod(
        start=datetime(2026, 3, 10, 8, 30, 15, _MICROS_INICIO),
        end=datetime(2026, 3, 10, 18, 45, 59, _MICROS_FIM),
    )
    repositorio.add(_funcionario(unavailabilities=(periodo,)))

    gravado = repositorio.find_by_id(_A, _E1)
    assert gravado is not None
    (voltou,) = gravado.unavailabilities
    assert voltou == periodo
    assert voltou.start.microsecond == _MICROS_INICIO
    assert voltou.end.microsecond == _MICROS_FIM
    assert voltou.start.tzinfo is None
    assert voltou.end.tzinfo is None
