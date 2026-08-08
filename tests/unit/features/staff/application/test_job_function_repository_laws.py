"""As cinco leis de `JobFunctionRepository`, travadas contra o fake (concept §11).

**Por que uma suíte por lei, e não "testes do fake".** Sem isto, um fake que
virasse upsert em silêncio passa verde enquanto o Postgres da 3.3 rejeita a
mesma escrita — o defeito histórico do BC identity, que a 2.3 teve de retroagir
(ADR 2.3.0003). Cada teste leva o nome da lei para que o teste de contrato da
3.3 possa pareá-los **lei a lei**.

Toda construção passa por `staff_repositories()`: nenhum teste instancia fake
diretamente, porque um par sobre stores diferentes faria L-JF3 passar
**vacuamente** (a remoção não enxergaria referenciador nenhum).
"""

from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.errors import (
    JobFunctionAlreadyExistsError,
    JobFunctionInUseError,
    JobFunctionNameAlreadyExistsError,
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
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")


def _funcao(
    id_: JobFunctionId = _F1, tenant: TenantId = _A, name: str = "Cozinheiro"
) -> JobFunction:
    return JobFunction(id=id_, tenant_id=tenant, name=name)


def _funcionario(
    id_: str = "e1",
    *,
    tenant: TenantId = _A,
    unit: UnitId = _U1,
    funcoes: frozenset[JobFunctionId] = frozenset({_F1}),
    active: bool = True,
) -> Employee:
    return Employee(
        id=EmployeeId(id_),
        tenant_id=tenant,
        unit_id=unit,
        name="Maria",
        workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
        shift_preference=None,
        job_function_ids=funcoes,
        active=active,
    )


def _com_funcao_gravada(name: str = "Cozinheiro") -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(_funcao(name=name))
    return fakes


# --- L-JF1: `add` é inserção, não upsert -------------------------------------


def test_l_jf1_add_com_id_ja_gravado_no_tenant_e_erro_e_nao_altera_o_registro() -> None:
    fakes = _com_funcao_gravada()
    with pytest.raises(JobFunctionAlreadyExistsError):
        fakes.job_functions.add(_funcao(name="Chapeiro"))
    gravada = fakes.job_functions.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"  # campos antigos, não os da tentativa


def test_l_jf1_add_com_id_gravado_em_outro_tenant_tambem_e_erro() -> None:
    """A colisão de **id** é global — a única lei destes ports que não é escopada.

    Na 3.3 o id é a chave primária: um fake que só olhasse dentro do tenant
    aceitaria uma inserção que o Postgres rejeita, e a divergência fake↔adapter
    só apareceria em produção (ADR 2.3.0003).
    """
    fakes = _com_funcao_gravada()
    with pytest.raises(JobFunctionAlreadyExistsError):
        fakes.job_functions.add(_funcao(tenant=_B))


def test_l_jf1_add_com_nome_ja_usado_no_tenant_e_erro_e_nao_altera_o_registro() -> None:
    fakes = _com_funcao_gravada()
    with pytest.raises(JobFunctionNameAlreadyExistsError):
        fakes.job_functions.add(_funcao(id_=_F2))
    assert fakes.job_functions.find_by_id(_A, _F2) is None
    gravada = fakes.job_functions.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"


def test_l_jf1_o_mesmo_nome_em_outro_tenant_e_aceito() -> None:
    """A unicidade de **nome** é por tenant — ao contrário da de id."""
    fakes = _com_funcao_gravada()
    fakes.job_functions.add(_funcao(id_=_F2, tenant=_B))
    gravada = fakes.job_functions.find_by_id(_B, _F2)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"


@pytest.mark.parametrize("variante", ["cozinheiro ", "Cozinheiro ", "COZINHEIRO", " Cozinheiro"])
def test_l_jf1_a_unicidade_de_nome_e_verbatim(variante: str) -> None:
    """Sem trim e sem case-folding: a unicidade é sobre o valor **digitado**.

    Normalizar aqui recusaria em silêncio nomes que o gerente considera
    distintos (workforce §3.2).
    """
    fakes = _com_funcao_gravada()
    fakes.job_functions.add(_funcao(id_=_F2, name=variante))
    gravada = fakes.job_functions.find_by_id(_A, _F2)
    assert gravada is not None
    assert gravada.name == variante


# --- L-JF2: `update` é UPDATE, não upsert ------------------------------------


def test_l_jf2_update_de_funcao_inexistente_no_tenant_nao_grava_nada() -> None:
    fakes = staff_repositories()
    with pytest.raises(JobFunctionNotFoundError):
        fakes.job_functions.update(_funcao())
    assert fakes.job_functions.find_by_id(_A, _F1) is None
    assert fakes.job_functions.list_by_tenant(_A) == ()


def test_l_jf2_update_de_funcao_de_outro_tenant_nao_grava_nada() -> None:
    """ "Inexistente no tenant" inclui "existe, mas é de outro restaurante"."""
    fakes = _com_funcao_gravada()
    with pytest.raises(JobFunctionNotFoundError):
        fakes.job_functions.update(_funcao(tenant=_B, name="Chapeiro"))
    gravada = fakes.job_functions.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"
    assert fakes.job_functions.list_by_tenant(_B) == ()


def test_l_jf2_renomear_para_o_proprio_nome_e_aceito() -> None:
    """O caso que um `exists_by_name` booleano quebraria (concept §7)."""
    fakes = _com_funcao_gravada()
    fakes.job_functions.update(_funcao(name="Cozinheiro"))
    gravada = fakes.job_functions.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"


def test_l_jf2_renomear_para_o_nome_de_outra_funcao_e_erro() -> None:
    fakes = _com_funcao_gravada()
    fakes.job_functions.add(_funcao(id_=_F2, name="Chapeiro"))
    with pytest.raises(JobFunctionNameAlreadyExistsError):
        fakes.job_functions.update(_funcao(id_=_F2, name="Cozinheiro"))
    gravada = fakes.job_functions.find_by_id(_A, _F2)
    assert gravada is not None
    assert gravada.name == "Chapeiro"  # nome antigo


def test_l_jf2_update_grava_o_nome_novo_no_caminho_feliz() -> None:
    fakes = _com_funcao_gravada()
    fakes.job_functions.update(_funcao(name="Chapeiro"))
    gravada = fakes.job_functions.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Chapeiro"


# --- L-JF3: `delete` é remoção definitiva guardada ---------------------------


def test_l_jf3_delete_sem_referencias_remove() -> None:
    fakes = _com_funcao_gravada()
    fakes.job_functions.delete(_A, _F1)
    assert fakes.job_functions.find_by_id(_A, _F1) is None


def test_l_jf3_delete_de_funcao_referenciada_e_erro_e_a_funcao_continua_legivel() -> None:
    fakes = _com_funcao_gravada()
    fakes.employees.add(_funcionario())
    with pytest.raises(JobFunctionInUseError):
        fakes.job_functions.delete(_A, _F1)
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_l_jf3_referenciador_inativo_tambem_bloqueia() -> None:
    """O desligado ainda aponta para a função — apagá-la corromperia o cadastro.

    É a metade da lei que uma implementação "só conta ativos" perderia em
    silêncio, deixando o registro desligado apontando para função inexistente e
    furando a invariante "ao menos uma função" da 3.1.
    """
    fakes = _com_funcao_gravada()
    fakes.employees.add(_funcionario(active=False))
    with pytest.raises(JobFunctionInUseError):
        fakes.job_functions.delete(_A, _F1)
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_l_jf3_referenciador_em_outra_unidade_do_tenant_tambem_bloqueia() -> None:
    """A guarda é tenant-wide porque a **função** é tenant-scoped."""
    fakes = _com_funcao_gravada()
    fakes.employees.add(_funcionario(unit=UnitId("u2")))
    with pytest.raises(JobFunctionInUseError):
        fakes.job_functions.delete(_A, _F1)


def test_l_jf3_delete_de_funcao_inexistente_no_tenant_e_not_found() -> None:
    fakes = staff_repositories()
    with pytest.raises(JobFunctionNotFoundError):
        fakes.job_functions.delete(_A, _F1)


# --- L-JF4 / L-JF5: leitura em lote e listagem -------------------------------


def test_l_jf4_find_all_by_ids_devolve_so_as_encontradas_sem_levantar() -> None:
    """Id ausente **não** é erro aqui: quem compara com o pedido é o chamador."""
    fakes = _com_funcao_gravada()
    encontradas = fakes.job_functions.find_all_by_ids(_A, frozenset({_F1, JobFunctionId("f99")}))
    assert {funcao.id for funcao in encontradas} == {_F1}


def test_l_jf4_find_all_by_ids_ignora_funcao_de_outro_tenant() -> None:
    fakes = _com_funcao_gravada()
    fakes.job_functions.add(_funcao(id_=_F2, tenant=_B, name="Chapeiro"))
    encontradas = fakes.job_functions.find_all_by_ids(_A, frozenset({_F1, _F2}))
    assert {funcao.id for funcao in encontradas} == {_F1}


def test_l_jf4_find_all_by_ids_com_conjunto_vazio_devolve_vazio() -> None:
    """O caminho que `create_employee` percorre com conjunto vazio: nada falta,
    e quem rejeita é o domínio, na construção (concept §5.16)."""
    fakes = _com_funcao_gravada()
    assert fakes.job_functions.find_all_by_ids(_A, frozenset()) == ()


def test_l_jf5_list_by_tenant_devolve_todas_do_tenant_e_nenhuma_de_outro() -> None:
    fakes = _com_funcao_gravada()
    fakes.job_functions.add(_funcao(id_=_F2, name="Chapeiro"))
    fakes.job_functions.add(_funcao(id_=JobFunctionId("f3"), tenant=_B, name="Garçom"))
    assert {funcao.id for funcao in fakes.job_functions.list_by_tenant(_A)} == {_F1, _F2}
    assert {funcao.id for funcao in fakes.job_functions.list_by_tenant(_B)} == {JobFunctionId("f3")}


# --- escopo de tenant (teste dedicado do port) -------------------------------


def test_escopo_de_tenant_funcao_do_a_e_invisivel_e_intocavel_com_tenant_b() -> None:
    """Uma função do tenant A é **indistinguível de inexistente** para o B.

    `add` fica **fora** deste critério de propósito: a colisão de id é global e
    declarada (quadro do concept §4), então inserir com um id alheio levanta
    `JobFunctionAlreadyExistsError` — é a exceção deliberada, não um vazamento.
    O que não pode vazar é leitura, listagem, escrita e remoção.
    """
    fakes = _com_funcao_gravada()
    fakes.employees.add(_funcionario())  # a função está EM USO no tenant A

    # Leitura e listagem: nada vaza.
    assert fakes.job_functions.find_by_id(_B, _F1) is None
    assert fakes.job_functions.find_by_name(_B, "Cozinheiro") is None
    assert fakes.job_functions.list_by_tenant(_B) == ()
    assert fakes.job_functions.find_all_by_ids(_B, frozenset({_F1})) == ()

    # Escrita: NotFound, e nunca NameAlreadyExists (que confirmaria o nome).
    with pytest.raises(JobFunctionNotFoundError):
        fakes.job_functions.update(_funcao(tenant=_B))

    # Remoção: NotFound VENCE InUse. Este é o ponto: a função está de fato
    # referenciada, e responder `JobFunctionInUseError` confirmaria ao tenant B
    # que ela existe **e** que está em uso no restaurante alheio (§5.4).
    with pytest.raises(JobFunctionNotFoundError):
        fakes.job_functions.delete(_B, _F1)
    assert fakes.job_functions.find_by_id(_A, _F1) is not None
