"""Use cases de função de trabalho: criar, renomear e listar (Task 07).

Toda asserção de efeito é feita **relendo pelo port**, não só sobre o result: o
result é o que o use case diz ter feito; a releitura é o que ele de fato gravou.
Um use case que montasse o result correto e não chamasse `add` passaria em
qualquer suíte que olhasse só para o retorno.

> **E os caminhos de rejeição aserem `store.calls`.** O par de fakes já impõe a
> unicidade de nome por conta própria (L-JF1 no `add`, L-JF2 no `update`), então
> `pytest.raises(JobFunctionNameAlreadyExistsError)` seria verde **mesmo sem a
> checagem no use case** — o erro viria do port, do mesmo tipo. O que separa as
> duas camadas de enforcement é a escrita **nem ser tentada**, e isso só existe
> em `calls`.
"""

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    CreateJobFunctionCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import ListJobFunctionsQuery
from restaurant_hub.features.staff.application.errors import (
    JobFunctionNameAlreadyExistsError,
    JobFunctionNotFoundError,
    StaffApplicationError,
)
from restaurant_hub.features.staff.application.use_cases.create_job_function import (
    CreateJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_job_functions import (
    ListJobFunctionsUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_job_function import (
    RenameJobFunctionUseCase,
)
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    InvalidIdentifierError,
    InvalidNameError,
    InvalidUnitEnablementError,
    StaffError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement
from tests.fakes.features.staff.in_memory_access_guard import InMemoryAccessGuard
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")


def _criar(fakes: StaffFakes, gerador: FakeIdGenerator | None = None) -> CreateJobFunctionUseCase:
    return CreateJobFunctionUseCase(
        fakes.job_functions, gerador or FakeIdGenerator(), guard=PermissiveAccessGuard()
    )


def _renomear(fakes: StaffFakes) -> RenameJobFunctionUseCase:
    return RenameJobFunctionUseCase(fakes.job_functions, guard=PermissiveAccessGuard())


def _listar(fakes: StaffFakes) -> ListJobFunctionsUseCase:
    return ListJobFunctionsUseCase(fakes.job_functions, guard=PermissiveAccessGuard())


# --- criar -------------------------------------------------------------------


def test_cria_funcao_e_grava_o_nome_verbatim() -> None:
    fakes = staff_repositories()
    gerador = FakeIdGenerator()
    resultado = _criar(fakes, gerador).execute(
        CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="  Cozinheiro ")
    )

    # Conversão canônica do id (concept §5.3): str(uuid), não outra coisa.
    assert resultado.id == str(gerador.generated[0])
    assert resultado.name == "  Cozinheiro "
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(resultado.id))
    assert gravada is not None
    assert gravada.name == "  Cozinheiro "  # releitura pelo port, verbatim


def test_criar_com_nome_ja_usado_no_mesmo_tenant_e_conflito_sem_tentar_gravar() -> None:
    """A checagem é do use case: o `add` **nem é chamado**.

    Sem a asserção sobre `calls`, este teste passaria com o `find_by_name`
    removido do use case — o fake levantaria o mesmo erro no `add`, pela L-JF1.
    """
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro"))
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionNameAlreadyExistsError):
        criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro"))

    assert "job_functions.add" not in fakes.store.calls[antes:]
    assert len(fakes.job_functions.list_by_tenant(_A)) == 1


def test_criar_com_o_mesmo_nome_em_outro_tenant_e_aceito() -> None:
    """Unicidade de nome é **por tenant** — dois restaurantes têm cozinheiros."""
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro"))
    criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_B, name="Cozinheiro"))
    assert len(fakes.job_functions.list_by_tenant(_A)) == 1
    assert len(fakes.job_functions.list_by_tenant(_B)) == 1


@pytest.mark.parametrize("variante", ["cozinheiro ", "COZINHEIRO", " Cozinheiro"])
def test_nomes_que_diferem_so_por_espaco_ou_caixa_sao_distintos(variante: str) -> None:
    """Unicidade **verbatim**: o valor tal como o usuário digitou (workforce §3.2)."""
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro"))
    criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name=variante))
    assert {funcao.name for funcao in fakes.job_functions.list_by_tenant(_A)} == {
        "Cozinheiro",
        variante,
    }


@pytest.mark.parametrize("invalido", ["", "   "])
def test_criar_com_nome_vazio_nao_toca_o_port(invalido: str) -> None:
    """O erro é do domínio **e** nenhuma chamada chega ao repositório.

    A asserção sobre `calls` vazio é o ponto: sem ela, o teste passaria mesmo
    que o use case consultasse `find_by_name` antes de descobrir que o nome é
    inválido — uma consulta inútil que a ordem de §5.16 existe para evitar.
    """
    fakes = staff_repositories()
    with pytest.raises(InvalidNameError):
        _criar(fakes).execute(
            CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name=invalido)
        )
    assert fakes.store.calls == []


@pytest.mark.parametrize("invalido", ["", "   "])
def test_criar_com_tenant_vazio_nao_toca_o_port(invalido: str) -> None:
    """`InvalidIdentifierError` estava declarado em §6 e em três `Raises:` sem
    **nenhum** teste na camada application (achado F-03 da auditoria).

    Importa mais que um erro comum: `tenant_id` vazio é o que criaria um balde
    de falso isolamento entre restaurantes — um registro que nenhuma consulta
    escopada encontraria e que apareceria para quem passasse a mesma string
    vazia.
    """
    fakes = staff_repositories()
    with pytest.raises(InvalidIdentifierError):
        _criar(fakes).execute(
            CreateJobFunctionCommand(
                actor=TEST_ACTOR, tenant_id=TenantId(invalido), name="Cozinheiro"
            )
        )
    assert fakes.store.calls == []


def test_criar_com_nome_vazio_consome_e_descarta_o_id() -> None:
    """Comportamento **declarado** do concept §5.16, não desperdício acidental.

    Fixado por teste para que ninguém o "conserte" duplicando a validação de
    nome nesta camada — o que violaria §5.15.
    """
    fakes = staff_repositories()
    gerador = FakeIdGenerator()
    with pytest.raises(InvalidNameError):
        _criar(fakes, gerador).execute(
            CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="")
        )
    assert len(gerador.generated) == 1
    assert fakes.job_functions.list_by_tenant(_A) == ()


# --- renomear ----------------------------------------------------------------


def test_renomear_para_o_proprio_nome_atual_e_aceito() -> None:
    """O caso que um `exists_by_name` booleano quebraria (concept §7)."""
    fakes = staff_repositories()
    criada = _criar(fakes).execute(
        CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro")
    )
    resultado = _renomear(fakes).execute(
        RenameJobFunctionCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            job_function_id=JobFunctionId(criada.id),
            name="Cozinheiro",
        )
    )
    assert resultado.name == "Cozinheiro"
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(criada.id))
    assert gravada is not None
    assert gravada.name == "Cozinheiro"


def test_renomear_grava_o_nome_novo() -> None:
    fakes = staff_repositories()
    criada = _criar(fakes).execute(
        CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro")
    )
    resultado = _renomear(fakes).execute(
        RenameJobFunctionCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            job_function_id=JobFunctionId(criada.id),
            name="Chapeiro",
        )
    )
    assert resultado.name == "Chapeiro"
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(criada.id))
    assert gravada is not None
    assert gravada.name == "Chapeiro"


def test_renomear_para_o_nome_de_outra_funcao_e_conflito_sem_tentar_gravar() -> None:
    """Mesma disciplina do `create`: o `update` **nem é chamado**.

    Sem a asserção sobre `calls`, o teste passaria com a checagem de conflito
    removida do use case — a L-JF2 do port levantaria o mesmo erro no `update`.
    """
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro"))
    outra = criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Chapeiro"))
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionNameAlreadyExistsError):
        _renomear(fakes).execute(
            RenameJobFunctionCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                job_function_id=JobFunctionId(outra.id),
                name="Cozinheiro",
            )
        )

    assert "job_functions.update" not in fakes.store.calls[antes:]
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(outra.id))
    assert gravada is not None
    assert gravada.name == "Chapeiro"  # nome antigo


def test_renomear_funcao_inexistente_e_not_found() -> None:
    fakes = staff_repositories()
    with pytest.raises(JobFunctionNotFoundError):
        _renomear(fakes).execute(
            RenameJobFunctionCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                job_function_id=JobFunctionId("fantasma"),
                name="Chapeiro",
            )
        )


def test_renomear_funcao_de_outro_tenant_e_not_found() -> None:
    """Id alheio é indistinguível de inexistente (concept §5.4)."""
    fakes = staff_repositories()
    criada = _criar(fakes).execute(
        CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro")
    )
    with pytest.raises(JobFunctionNotFoundError):
        _renomear(fakes).execute(
            RenameJobFunctionCommand(
                actor=TEST_ACTOR,
                tenant_id=_B,
                job_function_id=JobFunctionId(criada.id),
                name="Chapeiro",
            )
        )
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(criada.id))
    assert gravada is not None
    assert gravada.name == "Cozinheiro"


def test_precedencia_inexistente_vence_nome_ja_usado() -> None:
    """Par duplo de §5.16: as duas checagens falham; **NotFound vence**.

    Se o conflito vencesse, a resposta confirmaria a quem pediu por um id
    inexistente que aquele nome já existe no tenant — informação que ele não
    obteve por nenhum caminho legítimo. A asserção é sobre o **tipo exato**:
    `pytest.raises(JobFunctionNotFoundError)` sozinho não distingue "acertou a
    precedência" de "levantou outra coisa".
    """
    fakes = staff_repositories()
    _criar(fakes).execute(
        CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro")
    )
    antes = len(fakes.store.calls)

    with pytest.raises((StaffError, StaffApplicationError)) as excecao:
        _renomear(fakes).execute(
            RenameJobFunctionCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                job_function_id=JobFunctionId("fantasma"),
                name="Cozinheiro",
            )
        )
    assert type(excecao.value) is JobFunctionNotFoundError
    # A ordem é observável aqui: a busca por nome nem chegou a acontecer.
    conduta = fakes.store.calls[antes:]
    assert "job_functions.find_by_name" not in conduta
    assert "job_functions.update" not in conduta


# --- listar ------------------------------------------------------------------


def test_listar_devolve_todas_do_tenant_e_nenhuma_de_outro() -> None:
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Cozinheiro"))
    criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Chapeiro"))
    criar.execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_B, name="Garçom"))

    do_a = _listar(fakes).execute(ListJobFunctionsQuery(actor=TEST_ACTOR, tenant_id=_A))
    assert {resultado.name for resultado in do_a} == {"Cozinheiro", "Chapeiro"}
    assert all(resultado.tenant_id == _A for resultado in do_a)

    do_b = _listar(fakes).execute(ListJobFunctionsQuery(actor=TEST_ACTOR, tenant_id=_B))
    assert {resultado.name for resultado in do_b} == {"Garçom"}


def test_listar_tenant_sem_funcoes_devolve_vazio() -> None:
    fakes = staff_repositories()
    assert _listar(fakes).execute(ListJobFunctionsQuery(actor=TEST_ACTOR, tenant_id=_A)) == ()


# --- Stage 3.11 — habilitação por unidade (ADR 3.11.0001) --------------------
#
# O guard aqui é o `InMemoryAccessGuard` — a segunda implementação das leis —,
# porque o que se mede é **quem alcança o quê**: ele concede a tripla exata do
# alvo, então "gerente de u1" é um conjunto de concessões, não um papel.

_U1 = UnitId("u1")
_U2 = UnitId("u2")
_U3 = UnitId("u3")
_JF = "manage_job_functions"
_MT = "manage_tenant"


def _gerente_de(*unidades: UnitId) -> InMemoryAccessGuard:
    """Detém o catálogo no tenant e nas unidades dadas; **não** detém `manage_tenant`."""
    guard = InMemoryAccessGuard(credential=TEST_ACTOR)
    guard.grant(_JF, tenant_id=_A)
    for unidade in unidades:
        guard.grant(_JF, tenant_id=_A, unit_id=unidade)
    return guard


def _dono() -> InMemoryAccessGuard:
    """Alcança o restaurante inteiro: catálogo no tenant e `manage_tenant`."""
    guard = InMemoryAccessGuard(credential=TEST_ACTOR)
    guard.grant(_JF, tenant_id=_A)
    guard.grant(_MT, tenant_id=_A)
    return guard


def _criar_como(
    fakes: StaffFakes, guard: InMemoryAccessGuard, gerador: FakeIdGenerator | None = None
) -> CreateJobFunctionUseCase:
    return CreateJobFunctionUseCase(fakes.job_functions, gerador or FakeIdGenerator(), guard=guard)


def _command(unit_ids: frozenset[UnitId] | None, name: str = "Caixa") -> CreateJobFunctionCommand:
    return CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name=name, unit_ids=unit_ids)


def test_ca1_gerente_cria_funcao_so_para_a_sua_unidade() -> None:
    """A função nasce habilitada em u1 e em mais nenhuma — relida pelo port."""
    fakes = staff_repositories()

    resultado = _criar_como(fakes, _gerente_de(_U1)).execute(_command(frozenset({_U1})))

    assert resultado.all_units is False
    assert resultado.unit_ids == (_U1,)
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(resultado.id))
    assert gravada is not None
    assert gravada.unit_enablement == UnitEnablement.only(frozenset({_U1}))
    assert [f.id for f in fakes.job_functions.list_by_unit(_A, _U1)] == [resultado.id]
    assert fakes.job_functions.list_by_unit(_A, _U2) == ()


def test_ca2_as_unidades_sao_autorizadas_uma_a_uma_em_ordem_estavel() -> None:
    """L-AG4 — um alvo por unidade, depois do tenant, em ordem `sorted`."""
    fakes = staff_repositories()
    guard = _gerente_de(_U1, _U2, _U3)

    _criar_como(fakes, guard).execute(_command(frozenset({_U3, _U1, _U2})))

    assert guard.calls == [
        f"authorize({_JF},{_A},None)",
        f"authorize({_JF},{_A},{_U1})",
        f"authorize({_JF},{_A},{_U2})",
        f"authorize({_JF},{_A},{_U3})",
    ]


def test_ca2_gerente_que_pede_unidade_que_nao_enxerga_e_negado_sem_efeito() -> None:
    """Uma unidade alheia no conjunto nega o pedido inteiro, antes de id e de porta."""
    fakes = staff_repositories()
    guard = _gerente_de(_U1)
    gerador = FakeIdGenerator()
    antes = len(fakes.store.calls)

    with pytest.raises(type(guard.authorization_error)) as excinfo:
        _criar_como(fakes, guard, gerador).execute(_command(frozenset({_U1, _U2})))

    assert excinfo.value is guard.authorization_error  # crua (L-AG2)
    assert guard.calls[-1] == f"authorize({_JF},{_A},{_U2})"
    assert fakes.store.calls[antes:] == []
    assert gerador.generated == []


def test_ca2_gerente_que_pede_todas_as_unidades_e_negado_sem_efeito() -> None:
    """ "Todas" exige `manage_tenant`; deter o catálogo em todas as unidades não basta."""
    fakes = staff_repositories()
    guard = _gerente_de(_U1, _U2, _U3)
    gerador = FakeIdGenerator()
    antes = len(fakes.store.calls)

    with pytest.raises(type(guard.authorization_error)) as excinfo:
        _criar_como(fakes, guard, gerador).execute(_command(None))

    assert excinfo.value is guard.authorization_error
    assert guard.calls == [f"authorize({_JF},{_A},None)", f"authorize({_MT},{_A},None)"]
    assert fakes.store.calls[antes:] == []
    assert gerador.generated == []


def test_ca2_dono_cria_para_todas_e_a_funcao_vale_em_toda_unidade() -> None:
    fakes = staff_repositories()
    guard = _dono()

    resultado = _criar_como(fakes, guard).execute(_command(None))

    assert resultado.all_units is True
    assert resultado.unit_ids == ()
    assert guard.calls == [f"authorize({_JF},{_A},None)", f"authorize({_MT},{_A},None)"]
    for unidade in (_U1, _U2, UnitId("unidade-criada-amanha")):
        assert [f.id for f in fakes.job_functions.list_by_unit(_A, unidade)] == [resultado.id]


def test_manage_tenant_sozinho_nao_cria_sem_o_catalogo() -> None:
    """As duas permissões são exigidas **juntas** — a do catálogo vem primeiro."""
    fakes = staff_repositories()
    guard = InMemoryAccessGuard(credential=TEST_ACTOR)
    guard.grant(_MT, tenant_id=_A)

    with pytest.raises(type(guard.authorization_error)):
        _criar_como(fakes, guard).execute(_command(None))

    assert guard.calls == [f"authorize({_JF},{_A},None)"]


def test_ca9a_conjunto_de_unidades_vazio_e_recusado_sem_tocar_o_port() -> None:
    """Vazio não é "todas": é a habilitação que o domínio recusa (ADR 3.11.0001 §2)."""
    fakes = staff_repositories()
    antes = len(fakes.store.calls)

    with pytest.raises(InvalidUnitEnablementError):
        _criar_como(fakes, _gerente_de(_U1)).execute(_command(frozenset()))

    assert fakes.store.calls[antes:] == []


def test_o_resultado_ordena_as_unidades() -> None:
    fakes = staff_repositories()

    resultado = _criar_como(fakes, _gerente_de(_U1, _U2)).execute(_command(frozenset({_U2, _U1})))

    assert resultado.unit_ids == (_U1, _U2)


def _com_funcoes_em_unidades(fakes: StaffFakes) -> None:
    for id_, nome, habilitacao in (
        ("f-todas", "Cozinheiro", UnitEnablement.everywhere()),
        ("f-u1", "Atendente", UnitEnablement.only(frozenset({_U1}))),
        ("f-u2", "Barman", UnitEnablement.only(frozenset({_U2}))),
    ):
        fakes.job_functions.add(
            JobFunction(id=JobFunctionId(id_), tenant_id=_A, name=nome, unit_enablement=habilitacao)
        )


def test_ca3_listar_uma_unidade_nao_mostra_funcao_nao_habilitada_nela() -> None:
    fakes = staff_repositories()
    _com_funcoes_em_unidades(fakes)
    guard = _gerente_de(_U1)

    resultado = ListJobFunctionsUseCase(fakes.job_functions, guard=guard).execute(
        ListJobFunctionsQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1)
    )

    assert [r.id for r in resultado] == ["f-u1", "f-todas"]  # L-ORD: Atendente, Cozinheiro
    assert guard.calls == [f"authorize({_JF},{_A},{_U1})"]
    assert "job_functions.list_by_tenant" not in fakes.store.calls


def test_ca3_listar_unidade_que_o_ator_nao_enxerga_e_negado_sem_ler() -> None:
    fakes = staff_repositories()
    _com_funcoes_em_unidades(fakes)
    guard = _gerente_de(_U1)
    antes = len(fakes.store.calls)

    with pytest.raises(type(guard.authorization_error)) as excinfo:
        ListJobFunctionsUseCase(fakes.job_functions, guard=guard).execute(
            ListJobFunctionsQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U2)
        )

    assert excinfo.value is guard.authorization_error
    assert fakes.store.calls[antes:] == []


def test_ca11_o_catalogo_traz_a_habilitacao_de_cada_funcao() -> None:
    """Sem unidade, a listagem é o catálogo inteiro — e cada item diz onde vale."""
    fakes = staff_repositories()
    _com_funcoes_em_unidades(fakes)
    guard = _gerente_de(_U1)

    resultado = ListJobFunctionsUseCase(fakes.job_functions, guard=guard).execute(
        ListJobFunctionsQuery(actor=TEST_ACTOR, tenant_id=_A)
    )

    assert {r.id: (r.all_units, r.unit_ids) for r in resultado} == {
        "f-todas": (True, ()),
        "f-u1": (False, (_U1,)),
        "f-u2": (False, (_U2,)),
    }
    assert guard.calls == [f"authorize({_JF},{_A},None)"]
    assert "job_functions.list_by_unit" not in fakes.store.calls
