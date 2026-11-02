"""As sete leis de `EmployeeRepository` — **e `L-ORD`** — como contrato.

Suíte **promovida** da 3.2 (`tests/unit/features/staff/application/`) por
`git mv` na Stage 3.3, ADR 3.3.0007. Os **nomes** e as **asserções** dos testes
não mudaram no movimento: é isso que preserva o pareamento lei a lei — o que
evita a retroação de contrato que a 2.2→2.3 pagou (ADR 2.3.0003). O que mudou
foi a origem do sujeito: antes construído no corpo, agora recebido pela fixture
`repos`, que parametriza a suíte sobre as implementações do port.

O teste mais importante do módulo é
`test_l_e3_update_com_tenant_alheio_e_not_found_mesmo_com_unidade_divergente`:
ele trava a **ordem de checagem** do port, que é a única regra daqui cujo
descumprimento passaria despercebido — todos os outros testes continuariam
verdes enquanto o port confirmasse a existência de registro alheio.
"""

import dataclasses
import sys
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.errors import (
    EmployeeAlreadyExistsError,
    EmployeeHasLoginError,
    EmployeeInUseError,
    EmployeeNotFoundError,
    EmployeeRelocationError,
    JobFunctionNotFoundError,
    StaffApplicationError,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeAlreadyHasLoginError,
    InvalidIdentifierError,
    InvalidNameError,
    StaffError,
    TerminatedEmployeeLoginError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
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
from tests.conftest import _REPO_ROOT
from tests.contract.features.staff.conftest import RepositoriosDeStaff

pytestmark = pytest.mark.contract

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")
_E1 = EmployeeId("e1")
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)


_BASE = Employee(
    id=_E1,
    tenant_id=_A,
    unit_id=_U1,
    name="Maria",
    workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
    shift_preference=None,
    job_function_ids=frozenset({_F1}),
)


def _funcionario(**overrides: object) -> Employee:
    # Mesma forma do helper da suíte de domínio da 3.1: `dataclasses.replace`
    # chama o construtor real, então cada override passa pelo `__post_init__`
    # como uma construção direta passaria.
    return dataclasses.replace(_BASE, **overrides)


def _com_funcoes_gravadas(repos: RepositoriosDeStaff) -> None:
    """Par com `f1` e `f2` no tenant A e `f1` também no tenant B (id `f-b`)."""
    repos.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    repos.job_functions.add(JobFunction(id=_F2, tenant_id=_A, name="Chapeiro"))
    repos.job_functions.add(JobFunction(id=JobFunctionId("f-b"), tenant_id=_B, name="Cozinheiro"))


def _com_funcionario_gravado(repos: RepositoriosDeStaff) -> None:
    _com_funcoes_gravadas(repos)
    repos.employees.add(_funcionario())


# --- isolamento entre agregados: `update` de um não toca as filhas de outro ----
#
# **Por que estes três testes existem, e por que aqui.** A escrita das filhas por
# diferença (§5.20) emite `DELETE` nas três tabelas-filhas. Se algum deles
# esquecer o predicado de `employee_id`, o `update` de A apaga a linha
# correspondente de **todo mundo** — e nenhuma asserção sobre o agregado de A
# percebe, porque o de A fica exatamente como deveria.
#
# É propriedade de **port**, não de adapter: "gravar um agregado não altera
# outro" vale para qualquer implementação. O fake a satisfaz por construção (o
# `update` troca uma entrada de dicionário); o adapter precisa escopar cada
# `DELETE`. Um teste de contrato é o único lugar onde a propriedade fica
# afirmada para as duas — e onde o fake serve de oráculo do que o real deve
# fazer.
#
# O setup é o que dá o poder de discriminação, e é o que faltava: **B compartilha
# com A uma linha em cada tabela-filha** — a mesma função, um período de mesmo
# `start_at` (que é a chave usada no `DELETE`) e o mesmo `period` de preferência.
# Todo teste de `update` anterior usava um funcionário só, ou dois sem filha em
# comum, e por isso passava com os três predicados removidos.

_E2 = EmployeeId("e2")
_PERIODO_COMPARTILHADO = UnavailabilityPeriod(
    start=datetime(2026, 8, 5, 8, 0),
    end=datetime(2026, 8, 5, 12, 0),
)


def _com_dois_funcionarios_com_filhas_em_comum(repos: RepositoriosDeStaff) -> None:
    """A e B lado a lado, cada tabela-filha com uma linha em comum."""
    _com_funcoes_gravadas(repos)
    repos.employees.add(
        _funcionario(
            job_function_ids=frozenset({_F1, _F2}),
            unavailabilities=(_PERIODO, _PERIODO_COMPARTILHADO),
            shift_preference=ShiftPreference(
                periods=frozenset({DayPeriod.MORNING, DayPeriod.NIGHT})
            ),
        )
    )
    repos.employees.add(
        _funcionario(
            id=_E2,
            name="Bruno",
            job_function_ids=frozenset({_F1, _F2}),
            unavailabilities=(_PERIODO_COMPARTILHADO,),
            shift_preference=ShiftPreference(periods=frozenset({DayPeriod.NIGHT})),
        )
    )


def _a_sem_uma_filha_de_cada_tabela() -> Employee:
    """A perdendo exatamente a linha que compartilhava com B, nas três tabelas."""
    return _funcionario(
        job_function_ids=frozenset({_F1}),
        unavailabilities=(_PERIODO,),
        shift_preference=ShiftPreference(periods=frozenset({DayPeriod.MORNING})),
    )


def test_update_de_um_funcionario_nao_remove_as_funcoes_de_outro(
    repos: RepositoriosDeStaff,
) -> None:
    """A remoção de `f2` em A não pode alcançar o vínculo `f2` de B.

    Com o `DELETE` desescopado, B perde a função e o estrago **não é reportado**:
    a escrita de A responde sucesso. Pior, o dano é cross-tenant — o `DELETE`
    também não filtra `tenant_id` —, e um B que ficasse sem nenhuma função
    passaria a levantar `EmptyJobFunctionsError` na leitura, num caminho que o
    port (`find_by_id -> Employee | None`) não prevê.
    """
    _com_dois_funcionarios_com_filhas_em_comum(repos)

    repos.employees.update(_a_sem_uma_filha_de_cada_tabela())

    vizinho = repos.employees.find_by_id(_A, _U1, _E2)
    assert vizinho is not None
    assert vizinho.job_function_ids == frozenset({_F1, _F2})


def test_update_de_um_funcionario_nao_remove_as_indisponibilidades_de_outro(
    repos: RepositoriosDeStaff,
) -> None:
    """O `DELETE` de períodos é por `start_at`, que **não** é único entre funcionários.

    A PK é `(employee_id, start_at)`: dois funcionários podem — e é comum —
    ter indisponibilidade começando no mesmo instante. Sem o predicado de
    `employee_id`, apagar o período de A apaga o de todos os colegas que
    começavam junto.
    """
    _com_dois_funcionarios_com_filhas_em_comum(repos)

    repos.employees.update(_a_sem_uma_filha_de_cada_tabela())

    vizinho = repos.employees.find_by_id(_A, _U1, _E2)
    assert vizinho is not None
    assert vizinho.unavailabilities == (_PERIODO_COMPARTILHADO,)


def test_update_de_um_funcionario_nao_remove_a_preferencia_de_outro(
    repos: RepositoriosDeStaff,
) -> None:
    """`period` é um dos quatro valores do enum — colisão entre funcionários é a regra.

    Com o `DELETE` desescopado, A deixar de preferir a noite apaga a preferência
    noturna de **todo** funcionário que a tivesse.
    """
    _com_dois_funcionarios_com_filhas_em_comum(repos)

    repos.employees.update(_a_sem_uma_filha_de_cada_tabela())

    vizinho = repos.employees.find_by_id(_A, _U1, _E2)
    assert vizinho is not None
    assert vizinho.shift_preference == ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))


# --- L-E1: `add` é inserção, não upsert --------------------------------------


def test_l_e1_add_com_id_ja_gravado_e_erro_e_nao_altera_o_registro(
    repos: RepositoriosDeStaff,
) -> None:
    _com_funcionario_gravado(repos)
    with pytest.raises(EmployeeAlreadyExistsError):
        repos.employees.add(_funcionario(name="Joana"))
    gravado = repos.employees.find_by_id(_A, _U1, _E1)
    assert gravado is not None
    assert gravado.name == "Maria"


def test_l_e1_add_com_id_gravado_em_outro_tenant_tambem_e_erro(repos: RepositoriosDeStaff) -> None:
    """Escopo **global** do id — mesma razão de `JobFunctionRepository.add`."""
    _com_funcionario_gravado(repos)
    with pytest.raises(EmployeeAlreadyExistsError):
        repos.employees.add(
            _funcionario(tenant_id=_B, job_function_ids=frozenset({JobFunctionId("f-b")}))
        )


def test_ca5b_l_e1_precede_l_e4_quando_id_e_conjunto_falham_juntos(
    repos: RepositoriosDeStaff,
) -> None:
    """CA5b — a entrada viola **as duas** leis, e a resposta é a de L-E1 (§5.5).

    **É o único caso que discrimina a ordem das duas guardas, e nenhum dos 46
    testes herdados o alcança** — todos violam uma lei de cada vez, e sob uma
    violação só as duas ordens respondem igual.

    A ordem não é preferência: ela é a do fake
    (`in_memory_employee_repository.py`), e o adapter tem de replicá-la
    **contra a ordem natural do SQL**. Num `INSERT` puro a colisão de id só
    apareceria ao gravar — isto é, **depois** da pré-checagem referencial —, e
    esta entrada responderia `JobFunctionNotFoundError` no Postgres e
    `EmployeeAlreadyExistsError` no fake. Duas implementações do mesmo port
    respondendo erros diferentes para a mesma entrada é exatamente a divergência
    que esta suíte existe para revelar, e ela só é revelada aqui.

    Por isso o adapter faz um `SELECT` de id explícito antes da pré-checagem: é
    trabalho que o SQL não pediria, feito para honrar o contrato.
    """
    _com_funcionario_gravado(repos)

    with pytest.raises(EmployeeAlreadyExistsError):
        repos.employees.add(
            _funcionario(name="Joana", job_function_ids=frozenset({JobFunctionId("f-inexistente")}))
        )

    gravado = repos.employees.find_by_id(_A, _U1, _E1)
    assert gravado is not None
    assert gravado.name == "Maria"


# --- L-E2: `update` é UPDATE, não upsert -------------------------------------


def test_l_e2_update_de_inexistente_no_tenant_nao_grava_nada(repos: RepositoriosDeStaff) -> None:
    _com_funcoes_gravadas(repos)
    with pytest.raises(EmployeeNotFoundError):
        repos.employees.update(_funcionario())
    assert repos.employees.find_by_id(_A, _U1, _E1) is None
    assert repos.employees.list_by_unit(_A, _U1) == ()


def test_l_e2_update_grava_o_agregado_inteiro_no_caminho_feliz(repos: RepositoriosDeStaff) -> None:
    """Nome, perfil, preferência, conjunto, indisponibilidades e estado.

    O vínculo de login **não** entra: tem escrita própria (`L-LINK`, issue #68),
    e o teste irmão abaixo trava que o `update` o ignora.
    """
    _com_funcionario_gravado(repos)
    editado = _funcionario(name="Joana", job_function_ids=frozenset({_F2}), active=False)
    editado = editado.change_workload_profile(OnDemand()).add_unavailability(_PERIODO)
    repos.employees.update(editado)
    gravado = repos.employees.find_by_id(_A, _U1, _E1)
    assert gravado is not None
    assert (
        gravado.name,
        gravado.workload_profile,
        gravado.job_function_ids,
        gravado.unavailabilities,
        gravado.active,
    ) == ("Joana", OnDemand(), frozenset({_F2}), (_PERIODO,), False)


def test_l_e2_update_nao_grava_o_vinculo_que_a_entidade_traz(repos: RepositoriosDeStaff) -> None:
    """`update` ignora o `user_id` da entidade: o vínculo só nasce por `link_login`.

    É a metade "um só escritor" da issue #68. Se o `update` gravasse o vínculo
    quando o gravado é `NULL`, a metade concorrente (dois R17) voltaria a ter um
    caminho que não passa pela checagem atômica de `L-LINK`.
    """
    _com_funcionario_gravado(repos)
    gravado = repos.employees.find_by_id(_A, _U1, _E1)
    assert gravado is not None

    repos.employees.update(gravado.link_login(UserId("login-1")).rename("Joana"))

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert (relido.name, relido.user_id) == ("Joana", None)


def test_l_e2_update_com_entidade_lida_antes_do_vinculo_nao_o_apaga(
    repos: RepositoriosDeStaff,
) -> None:
    """O cenário da issue #68, serializado: R07 lê, R17 vincula, R07 grava.

    A entidade do R07 foi lida **antes** do vínculo e carrega `user_id=None`.
    Gravá-la não pode apagar o vínculo — antes da #68, "última escrita vence"
    (ADR 3.3.0006) apagava, e a conta criada ficava órfã. A versão com duas
    conexões de verdade, entrelaçadas, é conduta e vive em `test_staff_conduct.py`.
    """
    _com_funcionario_gravado(repos)
    lido_antes = repos.employees.find_by_id(_A, _U1, _E1)
    assert lido_antes is not None
    repos.employees.link_login(_A, _U1, _E1, UserId("login-1"))

    repos.employees.update(lido_antes.rename("Joana"))

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert (relido.name, relido.user_id) == ("Joana", UserId("login-1"))


def test_l_e2_update_de_outro_campo_preserva_o_login_gravado(repos: RepositoriosDeStaff) -> None:
    """Renomear um registro vinculado, pela entidade **relida**, não apaga o login."""
    _com_funcionario_gravado(repos)
    repos.employees.link_login(_A, _U1, _E1, UserId("login-1"))

    vinculado = repos.employees.find_by_id(_A, _U1, _E1)
    assert vinculado is not None
    repos.employees.update(vinculado.rename("Joana"))

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert (relido.name, relido.user_id) == ("Joana", UserId("login-1"))


# --- L-E3: localização imutável ----------------------------------------------


def test_l_e3_update_com_unidade_divergente_no_mesmo_tenant_e_relocation(
    repos: RepositoriosDeStaff,
) -> None:
    _com_funcionario_gravado(repos)
    with pytest.raises(EmployeeRelocationError):
        repos.employees.update(_funcionario(unit_id=_U2, name="Joana"))
    gravado = repos.employees.find_by_id(_A, _U1, _E1)
    assert gravado is not None
    # Na unidade original E com os campos antigos: nada foi gravado.
    assert (gravado.unit_id, gravado.name) == (_U1, "Maria")


def test_l_e3_update_com_tenant_alheio_e_not_found_mesmo_com_unidade_divergente(
    repos: RepositoriosDeStaff,
) -> None:
    """**Teste irmão obrigatório da ordem de checagem** (concept §4/L-E3, §5.4).

    Este é o cenário perigoso: o registro existe, mas no tenant A; a tentativa
    vem com `tenant_id` do B **e** unidade divergente. Uma implementação que
    comparasse a unidade primeiro responderia `EmployeeRelocationError` — e esse
    erro, sozinho, **confirma ao tenant B que o registro existe** e em que
    unidade não está. A regra normativa de §5.4 é mais alta e vence a L-E3.

    A asserção é sobre o **tipo exato**, não `pytest.raises(EmployeeNotFoundError)`
    puro: a comparação exata é o que distingue "o port acertou" de "o port
    levantou outra coisa que por acaso também não é `Relocation`".

    De quebra, isto fixa L-E4 **depois** do lookup: o conjunto `{f1}` não existe
    no tenant B, então uma ordem que resolvesse as funções primeiro devolveria
    `JobFunctionNotFoundError` — e também vazaria, dizendo ao B algo sobre o
    catálogo do A.
    """
    _com_funcionario_gravado(repos)
    with pytest.raises((StaffError, StaffApplicationError)) as excecao:
        repos.employees.update(_funcionario(tenant_id=_B, unit_id=_U2, name="Joana"))
    assert type(excecao.value) is EmployeeNotFoundError

    gravado = repos.employees.find_by_id(_A, _U1, _E1)
    assert gravado is not None
    assert (gravado.tenant_id, gravado.unit_id, gravado.name) == (_A, _U1, "Maria")


def test_l_e3_vence_l_e4_quando_unidade_e_conjunto_falham_juntos(
    repos: RepositoriosDeStaff,
) -> None:
    """A ordem **interna** das guardas do `update`, depois do lookup de tenant.

    O docstring do fake afirma que a ordem das três é o contrato — existência,
    unidade, conjunto de funções. As duas primeiras estavam travadas; a terceira
    não: inverter L-E3 ↔ L-E4 não derrubava nada, porque nenhum cenário fazia as
    duas falharem juntas.

    Fica travada aqui, e não removida do docstring, porque a 3.3 herda este
    método como **especificação executável**: lá as duas checagens têm custo e
    forma diferentes (comparação de coluna vs. FK `RESTRICT`), e um adapter que
    as ordenasse ao contrário responderia `JobFunctionNotFoundError` a uma
    tentativa de relocalização — trocando um erro sobre o **registro** por um
    erro sobre o **catálogo**.
    """
    _com_funcionario_gravado(repos)
    with pytest.raises(StaffError) as excecao:
        repos.employees.update(
            _funcionario(unit_id=_U2, job_function_ids=frozenset({JobFunctionId("f99")}))
        )
    assert type(excecao.value) is EmployeeRelocationError


def test_l_e3_update_com_a_mesma_unidade_e_aceito(repos: RepositoriosDeStaff) -> None:
    """O contrapositivo: a lei bloqueia relocalização, não edição."""
    _com_funcionario_gravado(repos)
    repos.employees.update(_funcionario(name="Joana"))
    gravado = repos.employees.find_by_id(_A, _U1, _E1)
    assert gravado is not None
    assert gravado.name == "Joana"


# --- L-E4: validade referencial do conjunto ----------------------------------


def test_l_e4_add_com_funcao_inexistente_no_tenant_nao_grava_nada(
    repos: RepositoriosDeStaff,
) -> None:
    _com_funcoes_gravadas(repos)
    with pytest.raises(JobFunctionNotFoundError):
        repos.employees.add(_funcionario(job_function_ids=frozenset({JobFunctionId("f99")})))
    assert repos.employees.find_by_id(_A, _U1, _E1) is None


def test_l_e4_add_com_funcao_existente_em_outro_tenant_nao_grava_nada(
    repos: RepositoriosDeStaff,
) -> None:
    """Id de função alheia conta como **ausente** — a resolução é escopada."""
    _com_funcoes_gravadas(repos)
    with pytest.raises(JobFunctionNotFoundError):
        repos.employees.add(_funcionario(job_function_ids=frozenset({JobFunctionId("f-b")})))
    assert repos.employees.find_by_id(_A, _U1, _E1) is None


def test_l_e4_add_rejeita_o_conjunto_quando_so_uma_das_funcoes_falta(
    repos: RepositoriosDeStaff,
) -> None:
    """A lei é sobre **toda** id do conjunto, não sobre "alguma existir"."""
    _com_funcoes_gravadas(repos)
    with pytest.raises(JobFunctionNotFoundError):
        repos.employees.add(_funcionario(job_function_ids=frozenset({_F1, JobFunctionId("f99")})))
    assert repos.employees.find_by_id(_A, _U1, _E1) is None


def test_l_e4_update_com_funcao_inexistente_nao_grava_nada(repos: RepositoriosDeStaff) -> None:
    _com_funcionario_gravado(repos)
    with pytest.raises(JobFunctionNotFoundError):
        repos.employees.update(
            _funcionario(name="Joana", job_function_ids=frozenset({JobFunctionId("f99")}))
        )
    gravado = repos.employees.find_by_id(_A, _U1, _E1)
    assert gravado is not None
    assert (gravado.name, gravado.job_function_ids) == ("Maria", frozenset({_F1}))


# --- L-E5: `delete` é remoção definitiva guardada ----------------------------


def test_l_e5_delete_de_inexistente_no_tenant_e_not_found(repos: RepositoriosDeStaff) -> None:
    _com_funcoes_gravadas(repos)
    with pytest.raises(EmployeeNotFoundError):
        repos.employees.delete(_A, _U1, _E1)


def test_l_e5_delete_de_existente_remove_o_registro(repos: RepositoriosDeStaff) -> None:
    _com_funcionario_gravado(repos)
    repos.employees.delete(_A, _U1, _E1)
    assert repos.employees.find_by_id(_A, _U1, _E1) is None


def test_l_e5_nenhum_caminho_de_v1_produz_employee_in_use_error(repos: RepositoriosDeStaff) -> None:
    """A ausência de produtor em v1 é **declarada**, não esquecida.

    Nada no escopo atual referencia o registro de funcionário: o que existe são
    referências **saindo** dele (funções) e valores **dentro** dele
    (indisponibilidades). Por isso o registro mais "conectado" que v1 consegue
    montar — desligado, com duas funções, com indisponibilidade e com um colega
    compartilhando as mesmas funções — ainda é removível.

    Quem passa a produzir o erro é o Step 4 (alocação), pela FK da 3.3. A lei
    está publicada agora para que a 3.4/Step 4 não retroajam o contrato do port.
    """
    _com_funcoes_gravadas(repos)
    conectado = _funcionario(job_function_ids=frozenset({_F1, _F2}), active=False)
    repos.employees.add(conectado.add_unavailability(_PERIODO))
    repos.employees.add(_funcionario(id=EmployeeId("e2"), job_function_ids=frozenset({_F1, _F2})))

    repos.employees.delete(_A, _U1, _E1)  # não levanta EmployeeInUseError
    assert repos.employees.find_by_id(_A, _U1, _E1) is None


def test_l_e5_employee_in_use_error_existe_e_a_lei_esta_documentada_no_port(
    repos: RepositoriosDeStaff,
) -> None:
    """Classe instanciável, com mensagem, e lei legível por quem implementa a 3.3."""
    assert "e-1" in str(EmployeeInUseError("e-1"))
    documentacao = EmployeeRepository.delete.__doc__ or ""
    assert "EmployeeInUseError" in documentacao
    assert "Step 4" in documentacao


# --- L-E6: listagem por unidade ----------------------------------------------


def test_l_e4_reporta_a_id_ausente_de_forma_deterministica(repos: RepositoriosDeStaff) -> None:
    """Faltando duas funções, a id reportada é sempre a mesma.

    Mensagem de erro instável é ruído em log e teste intermitente em CI. A
    ordenação do fake existe para isso, e sem este teste um `sorted(...)[-1]`
    passaria despercebido — `frozenset` não tem ordem, então o "acaso" mudaria
    entre execuções.
    """
    _com_funcoes_gravadas(repos)
    faltantes = frozenset({JobFunctionId("f97"), JobFunctionId("f99")})
    with pytest.raises(JobFunctionNotFoundError) as excecao:
        repos.employees.add(_funcionario(job_function_ids=faltantes))
    assert "f97" in str(excecao.value)


# A "Nota deliberada" que ficava aqui — declarando que a **ordem** dessas
# leituras NÃO era travada por teste — saiu na Stage 3.3, no commit que
# introduziu `L-ORD`. Ela era verdadeira e virou **falsa** na linha em que o
# primeiro `test_l_ord_*` entrou: hoje o concept declara a ordem (ADR 3.3.0003),
# ela vale para as duas implementações, e é justamente ela que torna o reuso
# desta suíte como contrato possível — o contrário do que a nota dizia. As
# asserções de conjunto dos testes abaixo continuam como estão, porque o que
# elas travam é **pertinência**; a ordem tem testes próprios (`test_l_ord_*`).


def test_l_e6_list_by_unit_devolve_so_a_unidade_pedida(repos: RepositoriosDeStaff) -> None:
    _com_funcionario_gravado(repos)
    repos.employees.add(_funcionario(id=EmployeeId("e2"), unit_id=_U2))
    assert {registro.id for registro in repos.employees.list_by_unit(_A, _U1)} == {_E1}
    assert {registro.id for registro in repos.employees.list_by_unit(_A, _U2)} == {EmployeeId("e2")}


def test_l_e6_list_by_unit_esconde_desligados_por_default(repos: RepositoriosDeStaff) -> None:
    _com_funcionario_gravado(repos)
    repos.employees.add(_funcionario(id=EmployeeId("e2"), active=False))
    assert {registro.id for registro in repos.employees.list_by_unit(_A, _U1)} == {_E1}


def test_l_e6_list_by_unit_inclui_desligados_com_include_inactive(
    repos: RepositoriosDeStaff,
) -> None:
    """O desligado **sobrevive**: some da lista default, não do sistema."""
    _com_funcionario_gravado(repos)
    repos.employees.add(_funcionario(id=EmployeeId("e2"), active=False))
    incluindo = repos.employees.list_by_unit(_A, _U1, include_inactive=True)
    assert {registro.id for registro in incluindo} == {_E1, EmployeeId("e2")}
    # E continua endereçável por id, com ou sem flag.
    assert repos.employees.find_by_id(_A, _U1, EmployeeId("e2")) is not None


# --- L-E7: consulta de referência a função -----------------------------------


def test_l_e7_exists_by_job_function_e_false_sem_referencia(repos: RepositoriosDeStaff) -> None:
    _com_funcoes_gravadas(repos)
    assert repos.employees.exists_by_job_function(_A, _F1) is False


def test_l_e7_exists_by_job_function_e_true_em_qualquer_unidade_do_tenant(
    repos: RepositoriosDeStaff,
) -> None:
    """Tenant-wide porque a **função** é tenant-scoped: uma referência em
    qualquer unidade impede a remoção."""
    _com_funcoes_gravadas(repos)
    repos.employees.add(_funcionario(unit_id=_U2))
    assert repos.employees.exists_by_job_function(_A, _F1) is True


def test_l_e7_exists_by_job_function_e_true_para_referenciador_desligado(
    repos: RepositoriosDeStaff,
) -> None:
    _com_funcoes_gravadas(repos)
    repos.employees.add(_funcionario(active=False))
    assert repos.employees.exists_by_job_function(_A, _F1) is True


def test_l_e7_exists_by_job_function_e_false_para_referencia_de_outro_tenant(
    repos: RepositoriosDeStaff,
) -> None:
    """O booleano não pode contar registros do restaurante alheio."""
    _com_funcoes_gravadas(repos)
    repos.employees.add(
        _funcionario(tenant_id=_B, job_function_ids=frozenset({JobFunctionId("f-b")}))
    )
    assert repos.employees.exists_by_job_function(_A, JobFunctionId("f-b")) is False
    assert repos.employees.exists_by_job_function(_B, JobFunctionId("f-b")) is True


# --- L-ORD: ordem total da listagem e da reidratação (ADR 3.3.0003) ----------


def _com_funcionarios_adversariais(repos: RepositoriosDeStaff) -> None:
    """Mesmo dado adversarial do port irmão, e pela mesma razão.

    Nome acentuado, case misto, espaço à direita e **dois homônimos com ids
    diferentes** — sem os homônimos, o desempate por `id` (o cursor da paginação
    da 3.4) é inalcançável. Aqui os homônimos são ainda mais legítimos que lá:
    nome de funcionário **não é único** por declaração (concept 3.1 §5.2).
    """
    _com_funcoes_gravadas(repos)
    for id_, name in (
        ("e5", "Zeus"),
        ("e9", "Ana"),
        ("e1", "Álvaro"),
        ("e3", "ana"),
        ("e2", "Ana"),
        ("e4", "Zeus "),
    ):
        repos.employees.add(_funcionario(id=EmployeeId(id_), name=name))


def test_l_ord_list_by_unit_ordena_por_nome_e_desempata_por_id(repos: RepositoriosDeStaff) -> None:
    """CA10, metade `[fake]` — a sequência inteira, não "está ordenado".

    O `sorted()` do Python compara por **codepoint** e foi medido como idêntico
    a `ORDER BY name COLLATE "C", id COLLATE "C"`. Uma asserção de
    monotonicidade passaria com os dois homônimos em ordem arbitrária, que é
    exatamente onde a paginação quebra.
    """
    _com_funcionarios_adversariais(repos)
    listados = repos.employees.list_by_unit(_A, _U1)

    # A sequência **literal**, com o que a ordem por codepoint tem de
    # contraintuitivo escrito por extenso: maiúsculas antes de minúsculas
    # (`"Ana"` antes de `"ana"`), o acentuado **depois** de tudo
    # (`"Álvaro"` = U+00C1, depois de `"ana"` = U+0061), e o espaço à direita
    # depois do prefixo (`"Zeus"` < `"Zeus "`). É o limite honesto que o
    # ADR 3.3.0003 declara — ordem de cursor, não ordem de exibição.
    assert [(registro.name, registro.id) for registro in listados] == [
        ("Ana", "e2"),
        ("Ana", "e9"),
        ("Zeus", "e5"),
        ("Zeus ", "e4"),
        ("ana", "e3"),
        ("Álvaro", "e1"),
    ]


def test_l_ord_o_desempate_e_por_id_entre_homonimos(repos: RepositoriosDeStaff) -> None:
    """Nome de funcionário não é único **por declaração** — o desempate é a lei.

    Isolado do teste acima porque é a metade que a 3.4 usa como cursor: quando
    quebrar, é este nome que aparece no relatório de CI.
    """
    _com_funcionarios_adversariais(repos)
    homonimos = [
        registro for registro in repos.employees.list_by_unit(_A, _U1) if registro.name == "Ana"
    ]
    assert [registro.id for registro in homonimos] == ["e2", "e9"]


def test_l_ord_periodos_reidratam_ordenados_por_inicio_no_find_by_id(
    repos: RepositoriosDeStaff,
) -> None:
    """CA11 — e a divergência aqui corre na direção **contrária** à habitual.

    `Employee.add_unavailability` **concatena**, não ordena, e o fake guarda o
    agregado inteiro como foi entregue. Sem a reordenação na leitura seria o
    **fake** a reprovar esta lei enquanto o Postgres passaria, porque lá a ordem
    vem do `ORDER BY start_at` do adapter. Inserir fora de ordem cronológica é o
    ponto do teste, não um detalhe do arranjo.
    """
    _com_funcoes_gravadas(repos)
    tarde = UnavailabilityPeriod(
        start=datetime(2026, 8, 20, 8, 0), end=datetime(2026, 8, 20, 12, 0)
    )
    cedo = UnavailabilityPeriod(start=datetime(2026, 8, 3, 8, 0), end=datetime(2026, 8, 3, 12, 0))
    meio = UnavailabilityPeriod(start=datetime(2026, 8, 10, 8, 0), end=datetime(2026, 8, 10, 12, 0))
    repos.employees.add(_funcionario(unavailabilities=(tarde, cedo, meio)))

    lido = repos.employees.find_by_id(_A, _U1, _E1)

    assert lido is not None
    assert lido.unavailabilities == (cedo, meio, tarde)


def test_l_ord_periodos_reidratam_ordenados_tambem_no_list_by_unit(
    repos: RepositoriosDeStaff,
) -> None:
    """A lei fala dos **dois** métodos que montam agregado, não só do `find_by_id`.

    Travar só um deixaria a listagem — que é justamente a que a 3.4 pagina —
    livre para devolver o agregado em ordem de inserção.
    """
    _com_funcoes_gravadas(repos)
    tarde = UnavailabilityPeriod(
        start=datetime(2026, 8, 20, 8, 0), end=datetime(2026, 8, 20, 12, 0)
    )
    cedo = UnavailabilityPeriod(start=datetime(2026, 8, 3, 8, 0), end=datetime(2026, 8, 3, 12, 0))
    repos.employees.add(_funcionario(unavailabilities=(tarde, cedo)))

    listados = repos.employees.list_by_unit(_A, _U1)

    assert len(listados) == 1
    assert listados[0].unavailabilities == (cedo, tarde)


def test_l_ord_esta_declarada_no_port_com_a_ancora_da_stage_33(repos: RepositoriosDeStaff) -> None:
    """CA12 travado por **teste**, não por revisão — nas **duas** pontas.

    Sem a âncora, a lei existe no código e não existe na fonte que o código
    nomeia — referência pendurada. Mesma forma do
    `test_l_e5_employee_in_use_error_existe_e_a_lei_esta_documentada_no_port`.

    **A segunda ponta não é zelo.** Asserir só que a docstring **diz** "concept
    §4 da Stage 3.2" trava a citação e não o citado: apagar a seção datada do
    concept da 3.2 deixaria esta suíte verde e restauraria exatamente a
    referência pendurada que a D11 existe para eliminar.
    """
    documentacao = EmployeeRepository.__doc__ or ""
    modulo = sys.modules[EmployeeRepository.__module__].__doc__ or ""
    texto = documentacao + modulo

    assert "L-ORD" in texto
    assert "ADR 3.3.0003" in texto
    assert "concept §4 da Stage 3.2" in texto
    assert 'COLLATE "C"' in texto
    # A cláusula do agregado é distinta da cláusula da listagem, e as duas
    # precisam estar declaradas: são ordens sobre coisas diferentes.
    assert "start" in texto
    assert "frozenset" in texto  # `shift_preference`/`job_function_ids`: sem ordem, sem lei
    for metodo in (EmployeeRepository.list_by_unit, EmployeeRepository.find_by_id):
        assert "L-ORD" in (metodo.__doc__ or ""), metodo.__name__

    # A outra ponta: a fonte citada **contém** a lei. Caminho derivado de
    # `_REPO_ROOT` (e não do cwd) para que o resultado não dependa do diretório
    # de onde o pytest foi invocado; `encoding` explícito porque o default do
    # Windows não é UTF-8 e o arquivo tem acento.
    concept_da_32 = _REPO_ROOT / "docs" / "stages" / "3.2-staff-application" / "concept.md"
    fonte = concept_da_32.read_text(encoding="utf-8")
    assert "L-ORD" in fonte, f"a âncora citada pelo port não declara a lei: {concept_da_32}"
    assert "ADR 3.3.0003" in fonte


# --- escopo de tenant (teste dedicado do port) -------------------------------


def test_escopo_de_tenant_registro_do_a_e_invisivel_e_intocavel_com_tenant_b(
    repos: RepositoriosDeStaff,
) -> None:
    """Um registro do tenant A é **indistinguível de inexistente** para o B.

    `add` fica **fora** deste critério pela mesma razão do port de função: a
    colisão de id é global e declarada (quadro do concept §4).

    A face de escrita desta regra — `update` com tenant alheio devolvendo
    `NotFound` e não `Relocation` — é a mesma vista pelo lado da L-E3, e está
    travada no teste irmão acima. Aqui se trava a face de leitura, listagem e
    remoção.
    """
    _com_funcionario_gravado(repos)

    assert repos.employees.find_by_id(_B, _U1, _E1) is None
    assert repos.employees.list_by_unit(_B, _U1) == ()
    assert repos.employees.list_by_unit(_B, _U1, include_inactive=True) == ()

    with pytest.raises(EmployeeNotFoundError):
        repos.employees.delete(_B, _U1, _E1)
    assert repos.employees.find_by_id(_A, _U1, _E1) is not None


# --- escopo de UNIDADE: o endereço de três partes (Stage 3.4, ADR 3.4.0007) --
#
# **Por que estes testes vivem no contrato, e não numa suíte de adapter.** A
# unidade entra na **assinatura** do port, não no `WHERE` do Postgres — é a
# decisão do ADR 3.4.0007 §2. Posta só no adapter, a regra valeria em produção e
# não valeria nos testes de unidade, que rodam contra o fake; e esta suíte, que
# roda **um corpo de teste só** contra `[fake]` e `[postgres]`, não teria como
# expressá-la, porque a assinatura não carregaria a unidade. É a mesma
# divergência fake ≢ real que o byte NUL custou a este Step — agora sobre um
# invariante de **segurança**, onde ela é estritamente pior.
#
# O defeito fechado aqui é concreto (concept §3): com o lookup por
# `(tenant, id)`, um gerente da unidade A alcançava **qualquer** funcionário do
# mesmo restaurante pondo a própria unidade no path — lendo o cadastro alheio
# pela resposta de qualquer rota de mutação, e exfiltrando-o pela cópia.


def test_ca9_find_by_id_com_unidade_alheia_nao_encontra_o_registro(
    repos: RepositoriosDeStaff,
) -> None:
    """Registro criado na unidade A é `None` quando endereçado pela B.

    A segunda asserção não é redundante: sem ela, uma implementação que
    devolvesse `None` para **tudo** passaria. O que se trava é a discriminação —
    invisível no endereço errado, alcançável no certo.
    """
    _com_funcionario_gravado(repos)

    assert repos.employees.find_by_id(_A, _U2, _E1) is None
    assert repos.employees.find_by_id(_A, _U1, _E1) is not None


def test_ca9_delete_com_unidade_alheia_e_not_found_e_nao_remove(
    repos: RepositoriosDeStaff,
) -> None:
    """A metade de **escrita** da lei — e a que fecha a remoção cross-unidade.

    A asserção é sobre o **tipo exato**, e não `pytest.raises(...)` puro: o que
    distingue "o port acertou" de "levantou outra coisa que por acaso também não
    é sucesso" é a comparação exata. E a releitura no endereço certo prova que a
    recusa **não** apagou nada pelo caminho.
    """
    _com_funcionario_gravado(repos)

    with pytest.raises((StaffError, StaffApplicationError)) as excecao:
        repos.employees.delete(_A, _U2, _E1)
    assert type(excecao.value) is EmployeeNotFoundError

    assert repos.employees.find_by_id(_A, _U1, _E1) is not None


def test_ca9_a_recusa_por_unidade_e_indistinguivel_da_recusa_por_tenant(
    repos: RepositoriosDeStaff,
) -> None:
    """Nenhum erro confirma a existência de registro que o chamador não endereça.

    É a regra de §5.4 estendida à unidade pelo ADR 3.4.0007 §4. Um
    `EmployeeUnitMismatchError` — ou qualquer mensagem que diferisse da de
    tenant alheio — devolveria ao atacante exatamente a informação que a lei
    existe para reter: *este id existe neste restaurante, só não aqui*. Por isso
    a asserção é sobre o **tipo e a mensagem**, não só sobre o tipo.
    """
    _com_funcionario_gravado(repos)

    with pytest.raises(EmployeeNotFoundError) as por_unidade:
        repos.employees.delete(_A, _U2, _E1)
    with pytest.raises(EmployeeNotFoundError) as por_tenant:
        repos.employees.delete(_B, _U1, _E1)

    assert type(por_unidade.value) is type(por_tenant.value)
    assert str(por_unidade.value) == str(por_tenant.value)


def test_ca9_o_desligado_tambem_esta_sob_a_lei_de_unidade(repos: RepositoriosDeStaff) -> None:
    """O escopo de unidade **não** se relaxa para o registro inativo.

    `find_by_id` não filtra por estado (ADR 3.2.0006), e é justamente por isso
    que o desligado precisa de asserção própria: uma implementação que aplicasse
    a unidade só no caminho do ativo deixaria o cadastro do desligado alheio
    legível, e nenhum outro teste desta suíte perceberia.
    """
    _com_funcoes_gravadas(repos)
    repos.employees.add(_funcionario(active=False))

    assert repos.employees.find_by_id(_A, _U2, _E1) is None
    assert repos.employees.find_by_id(_A, _U1, _E1) is not None


def test_ca9_a_lei_de_unidade_esta_declarada_no_port_com_a_ancora_do_adr(
    repos: RepositoriosDeStaff,
) -> None:
    """A lei nasce na docstring do `Protocol`, não no SQL — travado por teste.

    Mesma forma de `test_l_ord_esta_declarada_no_port_com_a_ancora_da_stage_33`:
    sem esta asserção, alguém poderia mover a filtragem de volta para o adapter
    e deixar o contrato mudo sobre ela, com a suíte inteira verde — e o próximo
    implementador do port não teria onde ler a regra que precisa cumprir.
    """
    modulo = sys.modules[EmployeeRepository.__module__].__doc__ or ""

    assert "ADR 3.4.0007" in modulo
    assert "(tenant_id, unit_id, id)" in modulo
    for metodo in (EmployeeRepository.find_by_id, EmployeeRepository.delete):
        assert "ADR 3.4.0007" in (metodo.__doc__ or ""), metodo.__name__
    # E a L-E3 continua declarada, com o gatilho estreitado — não removida.
    assert "EmployeeRelocationError" in (EmployeeRepository.update.__doc__ or "")


# --- o byte NUL: a divergência fake ≢ real que a 3.4 fecha ------------------
#
# Esta é a asserção que **reprovaria em `[postgres]`** antes da Stage 3.4: o
# fake gravava o nome com NUL verbatim e o `psycopg` o recusava client-side com
# `DataError` (sem `sqlstate`, fora do alcance do tradutor de integridade da
# 3.3). Com a regra no domínio os dois parâmetros concordam **por construção** —
# e é isso que distingue este conserto de apenas esconder o 500
# (ADR 3.4.0003 §4).
_NOMES_ADVERSARIAIS = (
    "José Antônio",
    "\U0001f469\u200d\U0001f373",
    "linha1\nlinha2",
    'Ana "Nana" O\'Brien',
    "a" * 1000,
)
_IDS_ADVERSARIAIS = ["acento", "emoji_zwj", "quebra_de_linha", "aspas", "mil_caracteres"]


def test_ca17_nome_com_byte_nul_e_recusado_antes_de_alcancar_o_port(
    repos: RepositoriosDeStaff,
) -> None:
    """A recusa acontece na **construção da entidade**, não no port.

    Por isso `[fake]` e `[postgres]` passam pela mesma razão, e não por duas
    razões que casualmente coincidem hoje.
    """
    _com_funcoes_gravadas(repos)

    with pytest.raises(InvalidNameError):
        repos.employees.add(_funcionario(name="Mar\x00ia"))

    # Nada chegou ao store, nos dois parâmetros.
    assert repos.employees.find_by_id(_A, _U1, _E1) is None


@pytest.mark.parametrize("nome", _NOMES_ADVERSARIAIS, ids=_IDS_ADVERSARIAIS)
def test_ca18_nome_adversarial_sem_nul_faz_round_trip_verbatim(
    repos: RepositoriosDeStaff, nome: str
) -> None:
    """CA18 — a restrição é do tamanho da divergência, não maior.

    Sem este teste nada impede que a regra do NUL cresça depois para o C0
    inteiro, normalização de espaço ou limite de tamanho — normalização
    silenciosa por outro nome, contra o ADR 2.3.0005.
    """
    _com_funcoes_gravadas(repos)
    repos.employees.add(_funcionario(name=nome))

    lido = repos.employees.find_by_id(_A, _U1, _E1)

    assert lido is not None
    assert lido.name == nome


# --- L-LINK: escrita própria e condicional do vínculo (issue #68) ------------
#
# O vínculo tem método próprio no port para que a regra "definido uma vez" valha
# sobre o **gravado**, numa operação só. Os testes daqui travam a lei como o port
# a descreve, nas duas implementações: o caminho feliz grava **só** `user_id`, e
# cada recusa — endereço, já vinculado, desligado, id vazio — deixa o gravado
# exatamente como estava. A metade concorrente (dois escritores ao mesmo tempo)
# é conduta, e vive em `test_staff_conduct.py`.

_LOGIN = UserId("login-1")


def _campos(employee: Employee) -> tuple[object, ...]:
    """Todos os campos, e não `==`: a igualdade de `Employee` é só por id."""
    return dataclasses.astuple(employee)


def _registro_completo() -> Employee:
    """Um agregado com todas as filhas preenchidas — o que o vínculo não pode tocar."""
    return _funcionario(
        job_function_ids=frozenset({_F1, _F2}),
        unavailabilities=(_PERIODO,),
        shift_preference=ShiftPreference(periods=frozenset({DayPeriod.MORNING})),
    )


def test_l_link_grava_o_vinculo_e_nenhum_outro_campo(repos: RepositoriosDeStaff) -> None:
    _com_funcoes_gravadas(repos)
    repos.employees.add(_registro_completo())

    repos.employees.link_login(_A, _U1, _E1, _LOGIN)

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == _LOGIN
    assert _campos(dataclasses.replace(relido, user_id=None)) == _campos(_registro_completo())


@pytest.mark.parametrize(
    ("tenant", "unidade", "funcionario"),
    [(_A, _U1, EmployeeId("fantasma")), (_A, _U2, _E1), (_B, _U1, _E1)],
    ids=["inexistente", "outra_unidade", "outro_tenant"],
)
def test_l_link_fora_do_endereco_e_not_found_e_nao_grava(
    repos: RepositoriosDeStaff, tenant: TenantId, unidade: UnitId, funcionario: EmployeeId
) -> None:
    """Endereço de três partes (ADR 3.4.0007): outra unidade e outro tenant são inexistentes."""
    _com_funcionario_gravado(repos)

    with pytest.raises(EmployeeNotFoundError):
        repos.employees.link_login(tenant, unidade, funcionario, _LOGIN)

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id is None


def test_l_link_registro_ja_vinculado_e_recusado_e_o_vinculo_gravado_fica(
    repos: RepositoriosDeStaff,
) -> None:
    """O coração da issue #68: um segundo vínculo não troca o primeiro."""
    _com_funcionario_gravado(repos)
    repos.employees.link_login(_A, _U1, _E1, _LOGIN)

    with pytest.raises(EmployeeAlreadyHasLoginError):
        repos.employees.link_login(_A, _U1, _E1, UserId("login-2"))

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == _LOGIN


def test_l_link_registro_desligado_e_recusado_e_nada_e_gravado(repos: RepositoriosDeStaff) -> None:
    _com_funcoes_gravadas(repos)
    repos.employees.add(_funcionario(active=False))

    with pytest.raises(TerminatedEmployeeLoginError):
        repos.employees.link_login(_A, _U1, _E1, _LOGIN)

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert (relido.active, relido.user_id) == (False, None)


def test_l_link_vinculado_vence_desligado_na_precedencia(repos: RepositoriosDeStaff) -> None:
    """A precedência do domínio (concept 3.5 CA01), agora sobre o **gravado**."""
    _com_funcoes_gravadas(repos)
    repos.employees.add(_funcionario(active=False, user_id=_LOGIN))

    with pytest.raises(EmployeeAlreadyHasLoginError):
        repos.employees.link_login(_A, _U1, _E1, UserId("login-2"))

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == _LOGIN


@pytest.mark.parametrize("vazio", ["", "   "], ids=["vazio", "so_espacos"])
def test_l_link_user_id_vazio_e_recusado_e_nada_e_gravado(
    repos: RepositoriosDeStaff, vazio: str
) -> None:
    """A revalidação da entidade vale para a escrita própria do vínculo também."""
    _com_funcionario_gravado(repos)

    with pytest.raises(InvalidIdentifierError):
        repos.employees.link_login(_A, _U1, _E1, UserId(vazio))

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id is None


def _com_vizinhos_do_e1(
    repos: RepositoriosDeStaff,
) -> tuple[tuple[TenantId, UnitId, EmployeeId], ...]:
    """`e1` e três vizinhos sem vínculo: mesma unidade, outra unidade, outro tenant."""
    _com_funcoes_gravadas(repos)
    repos.employees.add(_funcionario())
    repos.employees.add(_funcionario(id=_E2, name="Bruno"))
    repos.employees.add(_funcionario(id=EmployeeId("e-u2"), unit_id=_U2))
    repos.employees.add(
        _funcionario(
            id=EmployeeId("e-b"), tenant_id=_B, job_function_ids=frozenset({JobFunctionId("f-b")})
        )
    )
    return ((_A, _U1, _E2), (_A, _U2, EmployeeId("e-u2")), (_B, _U1, EmployeeId("e-b")))


def test_l_link_vincula_so_o_registro_do_endereco_e_nenhum_vizinho(
    repos: RepositoriosDeStaff,
) -> None:
    """Uma linha só: o vínculo não vaza para outro registro (auditoria de testes da #68).

    `employees.user_id` não tem UNIQUE (ADR 3.5.0004 §3), então um `UPDATE` que
    perdesse o predicado de id vincularia a **mesma** conta a todo registro do
    tenant — ou do banco — sem erro nenhum. Os demais testes de `L-LINK` gravam
    um registro só e não enxergariam isso.
    """
    vizinhos = _com_vizinhos_do_e1(repos)

    repos.employees.link_login(_A, _U1, _E1, _LOGIN)
    with pytest.raises(EmployeeAlreadyHasLoginError):
        repos.employees.link_login(_A, _U1, _E1, UserId("login-2"))

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == _LOGIN
    for tenant, unidade, funcionario in vizinhos:
        vizinho = repos.employees.find_by_id(tenant, unidade, funcionario)
        assert vizinho is not None
        assert vizinho.user_id is None, f"o vínculo vazou para {funcionario!r}"


# --- L-DEL-LINK: registro com login não se apaga, no gravado (issue #108) ----
#
# A recusa "registro com login não é removido" (ADR 3.5.0003 §1b) era só do use
# case, sobre a entidade que ele leu. Estes testes a travam no port, sobre o
# **gravado**, nas duas implementações: o vinculado — ativo ou desligado — é
# recusado e fica intacto; o endereço vem antes da guarda; e a remoção do
# registro sem vínculo continua levando só ele. A metade concorrente (R17 entre
# a leitura e o `DELETE`) é conduta, e vive em `test_staff_conduct.py`.


@pytest.mark.parametrize("active", [True, False], ids=["ativo", "desligado"])
def test_l_del_link_registro_vinculado_e_recusado_e_fica_intacto(
    repos: RepositoriosDeStaff, active: bool
) -> None:
    """Vale para ativo **e** desligado: o vínculo permanece no desligamento."""
    _com_funcoes_gravadas(repos)
    repos.employees.add(_registro_completo())
    repos.employees.link_login(_A, _U1, _E1, _LOGIN)
    if not active:
        vinculado = repos.employees.find_by_id(_A, _U1, _E1)
        assert vinculado is not None
        repos.employees.update(vinculado.deactivate())

    with pytest.raises(EmployeeHasLoginError):
        repos.employees.delete(_A, _U1, _E1)

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None, "o registro vinculado foi removido"
    assert relido.user_id == _LOGIN
    esperado = dataclasses.replace(_registro_completo(), user_id=_LOGIN, active=active)
    assert _campos(relido) == _campos(esperado), "a recusa tocou as filhas do registro"


@pytest.mark.parametrize(
    ("tenant", "unidade", "funcionario"),
    [(_A, _U1, EmployeeId("fantasma")), (_A, _U2, _E1), (_B, _U1, _E1)],
    ids=["inexistente", "outra_unidade", "outro_tenant"],
)
def test_l_del_link_endereco_precede_a_guarda_do_vinculo(
    repos: RepositoriosDeStaff, tenant: TenantId, unidade: UnitId, funcionario: EmployeeId
) -> None:
    """Fora do endereço é `EmployeeNotFoundError` mesmo com o registro vinculado.

    Responder `EmployeeHasLoginError` aqui confirmaria a existência — e o
    vínculo — de um registro que o chamador não pode endereçar (ADR 3.4.0007 §4).
    """
    _com_funcionario_gravado(repos)
    repos.employees.link_login(_A, _U1, _E1, _LOGIN)

    with pytest.raises(EmployeeNotFoundError):
        repos.employees.delete(tenant, unidade, funcionario)

    relido = repos.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == _LOGIN


def test_l_del_link_vizinho_vinculado_nao_bloqueia_a_remocao_do_registro_sem_vinculo(
    repos: RepositoriosDeStaff,
) -> None:
    """A guarda lê o vínculo do registro **do endereço**, não o de outro."""
    vizinhos = _com_vizinhos_do_e1(repos)
    for tenant, unidade, funcionario in vizinhos:
        repos.employees.link_login(tenant, unidade, funcionario, _LOGIN)

    repos.employees.delete(_A, _U1, _E1)

    assert repos.employees.find_by_id(_A, _U1, _E1) is None
    for tenant, unidade, funcionario in vizinhos:
        vizinho = repos.employees.find_by_id(tenant, unidade, funcionario)
        assert vizinho is not None, f"a remoção levou junto {funcionario!r}"
        assert vizinho.user_id == _LOGIN


def test_l_del_link_remocao_sem_vinculo_leva_so_o_registro_do_endereco(
    repos: RepositoriosDeStaff,
) -> None:
    """Uma linha só: o `DELETE` reescrito na #108 não perde o predicado de id."""
    vizinhos = _com_vizinhos_do_e1(repos)

    repos.employees.delete(_A, _U1, _E1)

    assert repos.employees.find_by_id(_A, _U1, _E1) is None
    for tenant, unidade, funcionario in vizinhos:
        assert repos.employees.find_by_id(tenant, unidade, funcionario) is not None, (
            f"a remoção levou junto {funcionario!r}"
        )


def test_l_del_link_esta_declarada_no_port_com_a_ancora_da_issue(
    repos: RepositoriosDeStaff,
) -> None:
    documentacao = EmployeeRepository.delete.__doc__ or ""
    assert "L-DEL-LINK" in documentacao
    assert "EmployeeHasLoginError" in documentacao
    assert "ADR 0.0.0013" in documentacao
