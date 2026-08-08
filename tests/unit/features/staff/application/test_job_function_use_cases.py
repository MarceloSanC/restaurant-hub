"""Use cases de função de trabalho: criar, renomear e listar (Task 07).

Toda asserção de efeito é feita **relendo pelo port**, não só sobre o result: o
result é o que o use case diz ter feito; a releitura é o que ele de fato gravou.
Um use case que montasse o result correto e não chamasse `add` passaria em
qualquer suíte que olhasse só para o retorno.
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
from restaurant_hub.features.staff.domain.exceptions.errors import InvalidNameError, StaffError
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
)
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")


def _criar(fakes: StaffFakes, gerador: FakeIdGenerator | None = None) -> CreateJobFunctionUseCase:
    return CreateJobFunctionUseCase(fakes.job_functions, gerador or FakeIdGenerator())


def _renomear(fakes: StaffFakes) -> RenameJobFunctionUseCase:
    return RenameJobFunctionUseCase(fakes.job_functions)


def _listar(fakes: StaffFakes) -> ListJobFunctionsUseCase:
    return ListJobFunctionsUseCase(fakes.job_functions)


# --- criar -------------------------------------------------------------------


def test_cria_funcao_e_grava_o_nome_verbatim() -> None:
    fakes = staff_repositories()
    gerador = FakeIdGenerator()
    resultado = _criar(fakes, gerador).execute(
        CreateJobFunctionCommand(tenant_id=_A, name="  Cozinheiro ")
    )

    # Conversão canônica do id (concept §5.3): str(uuid), não outra coisa.
    assert resultado.id == str(gerador.generated[0])
    assert resultado.name == "  Cozinheiro "
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(resultado.id))
    assert gravada is not None
    assert gravada.name == "  Cozinheiro "  # releitura pelo port, verbatim


def test_criar_com_nome_ja_usado_no_mesmo_tenant_e_conflito() -> None:
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))
    with pytest.raises(JobFunctionNameAlreadyExistsError):
        criar.execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))
    assert len(fakes.job_functions.list_by_tenant(_A)) == 1


def test_criar_com_o_mesmo_nome_em_outro_tenant_e_aceito() -> None:
    """Unicidade de nome é **por tenant** — dois restaurantes têm cozinheiros."""
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))
    criar.execute(CreateJobFunctionCommand(tenant_id=_B, name="Cozinheiro"))
    assert len(fakes.job_functions.list_by_tenant(_A)) == 1
    assert len(fakes.job_functions.list_by_tenant(_B)) == 1


@pytest.mark.parametrize("variante", ["cozinheiro ", "COZINHEIRO", " Cozinheiro"])
def test_nomes_que_diferem_so_por_espaco_ou_caixa_sao_distintos(variante: str) -> None:
    """Unicidade **verbatim**: o valor tal como o usuário digitou (workforce §3.2)."""
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))
    criar.execute(CreateJobFunctionCommand(tenant_id=_A, name=variante))
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
        _criar(fakes).execute(CreateJobFunctionCommand(tenant_id=_A, name=invalido))
    assert fakes.store.calls == []


def test_criar_com_nome_vazio_consome_e_descarta_o_id() -> None:
    """Comportamento **declarado** do concept §5.16, não desperdício acidental.

    Fixado por teste para que ninguém o "conserte" duplicando a validação de
    nome nesta camada — o que violaria §5.15.
    """
    fakes = staff_repositories()
    gerador = FakeIdGenerator()
    with pytest.raises(InvalidNameError):
        _criar(fakes, gerador).execute(CreateJobFunctionCommand(tenant_id=_A, name=""))
    assert len(gerador.generated) == 1
    assert fakes.job_functions.list_by_tenant(_A) == ()


# --- renomear ----------------------------------------------------------------


def test_renomear_para_o_proprio_nome_atual_e_aceito() -> None:
    """O caso que um `exists_by_name` booleano quebraria (concept §7)."""
    fakes = staff_repositories()
    criada = _criar(fakes).execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))
    resultado = _renomear(fakes).execute(
        RenameJobFunctionCommand(
            tenant_id=_A, job_function_id=JobFunctionId(criada.id), name="Cozinheiro"
        )
    )
    assert resultado.name == "Cozinheiro"
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(criada.id))
    assert gravada is not None
    assert gravada.name == "Cozinheiro"


def test_renomear_grava_o_nome_novo() -> None:
    fakes = staff_repositories()
    criada = _criar(fakes).execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))
    resultado = _renomear(fakes).execute(
        RenameJobFunctionCommand(
            tenant_id=_A, job_function_id=JobFunctionId(criada.id), name="Chapeiro"
        )
    )
    assert resultado.name == "Chapeiro"
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(criada.id))
    assert gravada is not None
    assert gravada.name == "Chapeiro"


def test_renomear_para_o_nome_de_outra_funcao_e_conflito_e_preserva_o_antigo() -> None:
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))
    outra = criar.execute(CreateJobFunctionCommand(tenant_id=_A, name="Chapeiro"))

    with pytest.raises(JobFunctionNameAlreadyExistsError):
        _renomear(fakes).execute(
            RenameJobFunctionCommand(
                tenant_id=_A, job_function_id=JobFunctionId(outra.id), name="Cozinheiro"
            )
        )
    gravada = fakes.job_functions.find_by_id(_A, JobFunctionId(outra.id))
    assert gravada is not None
    assert gravada.name == "Chapeiro"  # nome antigo


def test_renomear_funcao_inexistente_e_not_found() -> None:
    fakes = staff_repositories()
    with pytest.raises(JobFunctionNotFoundError):
        _renomear(fakes).execute(
            RenameJobFunctionCommand(
                tenant_id=_A, job_function_id=JobFunctionId("fantasma"), name="Chapeiro"
            )
        )


def test_renomear_funcao_de_outro_tenant_e_not_found() -> None:
    """Id alheio é indistinguível de inexistente (concept §5.4)."""
    fakes = staff_repositories()
    criada = _criar(fakes).execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))
    with pytest.raises(JobFunctionNotFoundError):
        _renomear(fakes).execute(
            RenameJobFunctionCommand(
                tenant_id=_B, job_function_id=JobFunctionId(criada.id), name="Chapeiro"
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
    _criar(fakes).execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))

    with pytest.raises(StaffError) as excecao:
        _renomear(fakes).execute(
            RenameJobFunctionCommand(
                tenant_id=_A, job_function_id=JobFunctionId("fantasma"), name="Cozinheiro"
            )
        )
    assert type(excecao.value) is JobFunctionNotFoundError


# --- listar ------------------------------------------------------------------


def test_listar_devolve_todas_do_tenant_e_nenhuma_de_outro() -> None:
    fakes = staff_repositories()
    criar = _criar(fakes)
    criar.execute(CreateJobFunctionCommand(tenant_id=_A, name="Cozinheiro"))
    criar.execute(CreateJobFunctionCommand(tenant_id=_A, name="Chapeiro"))
    criar.execute(CreateJobFunctionCommand(tenant_id=_B, name="Garçom"))

    do_a = _listar(fakes).execute(ListJobFunctionsQuery(tenant_id=_A))
    assert {resultado.name for resultado in do_a} == {"Cozinheiro", "Chapeiro"}
    assert all(resultado.tenant_id == _A for resultado in do_a)

    do_b = _listar(fakes).execute(ListJobFunctionsQuery(tenant_id=_B))
    assert {resultado.name for resultado in do_b} == {"Garçom"}


def test_listar_tenant_sem_funcoes_devolve_vazio() -> None:
    fakes = staff_repositories()
    assert _listar(fakes).execute(ListJobFunctionsQuery(tenant_id=_A)) == ()
