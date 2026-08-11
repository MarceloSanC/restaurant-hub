"""As sete leis de `EmployeeRepository`, travadas contra o fake (concept §11).

Cada teste leva o nome da lei para que o teste de contrato da 3.3 possa
pareá-los **lei a lei** — é o que evita a retroação de contrato que a 2.2→2.3
pagou (ADR 2.3.0003).

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
    EmployeeInUseError,
    EmployeeNotFoundError,
    EmployeeRelocationError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import StaffError
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
)
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories

pytestmark = pytest.mark.unit

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


def _com_funcoes_gravadas() -> StaffFakes:
    """Par com `f1` e `f2` no tenant A e `f1` também no tenant B (id `f-b`)."""
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.job_functions.add(JobFunction(id=_F2, tenant_id=_A, name="Chapeiro"))
    fakes.job_functions.add(JobFunction(id=JobFunctionId("f-b"), tenant_id=_B, name="Cozinheiro"))
    return fakes


def _com_funcionario_gravado() -> StaffFakes:
    fakes = _com_funcoes_gravadas()
    fakes.employees.add(_funcionario())
    return fakes


# --- L-E1: `add` é inserção, não upsert --------------------------------------


def test_l_e1_add_com_id_ja_gravado_e_erro_e_nao_altera_o_registro() -> None:
    fakes = _com_funcionario_gravado()
    with pytest.raises(EmployeeAlreadyExistsError):
        fakes.employees.add(_funcionario(name="Joana"))
    gravado = fakes.employees.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.name == "Maria"


def test_l_e1_add_com_id_gravado_em_outro_tenant_tambem_e_erro() -> None:
    """Escopo **global** do id — mesma razão de `JobFunctionRepository.add`."""
    fakes = _com_funcionario_gravado()
    with pytest.raises(EmployeeAlreadyExistsError):
        fakes.employees.add(
            _funcionario(tenant_id=_B, job_function_ids=frozenset({JobFunctionId("f-b")}))
        )


# --- L-E2: `update` é UPDATE, não upsert -------------------------------------


def test_l_e2_update_de_inexistente_no_tenant_nao_grava_nada() -> None:
    fakes = _com_funcoes_gravadas()
    with pytest.raises(EmployeeNotFoundError):
        fakes.employees.update(_funcionario())
    assert fakes.employees.find_by_id(_A, _E1) is None
    assert fakes.employees.list_by_unit(_A, _U1) == ()


def test_l_e2_update_grava_o_agregado_inteiro_no_caminho_feliz() -> None:
    """Nome, perfil, preferência, conjunto, indisponibilidades **e estado**."""
    fakes = _com_funcionario_gravado()
    editado = _funcionario(name="Joana", job_function_ids=frozenset({_F2}), active=False)
    editado = editado.change_workload_profile(OnDemand()).add_unavailability(_PERIODO)
    fakes.employees.update(editado)
    gravado = fakes.employees.find_by_id(_A, _E1)
    assert gravado is not None
    assert (
        gravado.name,
        gravado.workload_profile,
        gravado.job_function_ids,
        gravado.unavailabilities,
        gravado.active,
    ) == ("Joana", OnDemand(), frozenset({_F2}), (_PERIODO,), False)


# --- L-E3: localização imutável ----------------------------------------------


def test_l_e3_update_com_unidade_divergente_no_mesmo_tenant_e_relocation() -> None:
    fakes = _com_funcionario_gravado()
    with pytest.raises(EmployeeRelocationError):
        fakes.employees.update(_funcionario(unit_id=_U2, name="Joana"))
    gravado = fakes.employees.find_by_id(_A, _E1)
    assert gravado is not None
    # Na unidade original E com os campos antigos: nada foi gravado.
    assert (gravado.unit_id, gravado.name) == (_U1, "Maria")


def test_l_e3_update_com_tenant_alheio_e_not_found_mesmo_com_unidade_divergente() -> None:
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
    fakes = _com_funcionario_gravado()
    with pytest.raises(StaffError) as excecao:
        fakes.employees.update(_funcionario(tenant_id=_B, unit_id=_U2, name="Joana"))
    assert type(excecao.value) is EmployeeNotFoundError

    gravado = fakes.employees.find_by_id(_A, _E1)
    assert gravado is not None
    assert (gravado.tenant_id, gravado.unit_id, gravado.name) == (_A, _U1, "Maria")


def test_l_e3_vence_l_e4_quando_unidade_e_conjunto_falham_juntos() -> None:
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
    fakes = _com_funcionario_gravado()
    with pytest.raises(StaffError) as excecao:
        fakes.employees.update(
            _funcionario(unit_id=_U2, job_function_ids=frozenset({JobFunctionId("f99")}))
        )
    assert type(excecao.value) is EmployeeRelocationError


def test_l_e3_update_com_a_mesma_unidade_e_aceito() -> None:
    """O contrapositivo: a lei bloqueia relocalização, não edição."""
    fakes = _com_funcionario_gravado()
    fakes.employees.update(_funcionario(name="Joana"))
    gravado = fakes.employees.find_by_id(_A, _E1)
    assert gravado is not None
    assert gravado.name == "Joana"


# --- L-E4: validade referencial do conjunto ----------------------------------


def test_l_e4_add_com_funcao_inexistente_no_tenant_nao_grava_nada() -> None:
    fakes = _com_funcoes_gravadas()
    with pytest.raises(JobFunctionNotFoundError):
        fakes.employees.add(_funcionario(job_function_ids=frozenset({JobFunctionId("f99")})))
    assert fakes.employees.find_by_id(_A, _E1) is None


def test_l_e4_add_com_funcao_existente_em_outro_tenant_nao_grava_nada() -> None:
    """Id de função alheia conta como **ausente** — a resolução é escopada."""
    fakes = _com_funcoes_gravadas()
    with pytest.raises(JobFunctionNotFoundError):
        fakes.employees.add(_funcionario(job_function_ids=frozenset({JobFunctionId("f-b")})))
    assert fakes.employees.find_by_id(_A, _E1) is None


def test_l_e4_add_rejeita_o_conjunto_quando_so_uma_das_funcoes_falta() -> None:
    """A lei é sobre **toda** id do conjunto, não sobre "alguma existir"."""
    fakes = _com_funcoes_gravadas()
    with pytest.raises(JobFunctionNotFoundError):
        fakes.employees.add(_funcionario(job_function_ids=frozenset({_F1, JobFunctionId("f99")})))
    assert fakes.employees.find_by_id(_A, _E1) is None


def test_l_e4_update_com_funcao_inexistente_nao_grava_nada() -> None:
    fakes = _com_funcionario_gravado()
    with pytest.raises(JobFunctionNotFoundError):
        fakes.employees.update(
            _funcionario(name="Joana", job_function_ids=frozenset({JobFunctionId("f99")}))
        )
    gravado = fakes.employees.find_by_id(_A, _E1)
    assert gravado is not None
    assert (gravado.name, gravado.job_function_ids) == ("Maria", frozenset({_F1}))


# --- L-E5: `delete` é remoção definitiva guardada ----------------------------


def test_l_e5_delete_de_inexistente_no_tenant_e_not_found() -> None:
    fakes = _com_funcoes_gravadas()
    with pytest.raises(EmployeeNotFoundError):
        fakes.employees.delete(_A, _E1)


def test_l_e5_delete_de_existente_remove_o_registro() -> None:
    fakes = _com_funcionario_gravado()
    fakes.employees.delete(_A, _E1)
    assert fakes.employees.find_by_id(_A, _E1) is None


def test_l_e5_nenhum_caminho_de_v1_produz_employee_in_use_error() -> None:
    """A ausência de produtor em v1 é **declarada**, não esquecida.

    Nada no escopo atual referencia o registro de funcionário: o que existe são
    referências **saindo** dele (funções) e valores **dentro** dele
    (indisponibilidades). Por isso o registro mais "conectado" que v1 consegue
    montar — desligado, com duas funções, com indisponibilidade e com um colega
    compartilhando as mesmas funções — ainda é removível.

    Quem passa a produzir o erro é o Step 4 (alocação), pela FK da 3.3. A lei
    está publicada agora para que a 3.4/Step 4 não retroajam o contrato do port.
    """
    fakes = _com_funcoes_gravadas()
    conectado = _funcionario(job_function_ids=frozenset({_F1, _F2}), active=False)
    fakes.employees.add(conectado.add_unavailability(_PERIODO))
    fakes.employees.add(_funcionario(id=EmployeeId("e2"), job_function_ids=frozenset({_F1, _F2})))

    fakes.employees.delete(_A, _E1)  # não levanta EmployeeInUseError
    assert fakes.employees.find_by_id(_A, _E1) is None


def test_l_e5_employee_in_use_error_existe_e_a_lei_esta_documentada_no_port() -> None:
    """Classe instanciável, com mensagem, e lei legível por quem implementa a 3.3."""
    assert "e-1" in str(EmployeeInUseError("e-1"))
    documentacao = EmployeeRepository.delete.__doc__ or ""
    assert "EmployeeInUseError" in documentacao
    assert "Step 4" in documentacao


# --- L-E6: listagem por unidade ----------------------------------------------


def test_l_e4_reporta_a_id_ausente_de_forma_deterministica() -> None:
    """Faltando duas funções, a id reportada é sempre a mesma.

    Mensagem de erro instável é ruído em log e teste intermitente em CI. A
    ordenação do fake existe para isso, e sem este teste um `sorted(...)[-1]`
    passaria despercebido — `frozenset` não tem ordem, então o "acaso" mudaria
    entre execuções.
    """
    fakes = _com_funcoes_gravadas()
    faltantes = frozenset({JobFunctionId("f97"), JobFunctionId("f99")})
    with pytest.raises(JobFunctionNotFoundError) as excecao:
        fakes.employees.add(_funcionario(job_function_ids=faltantes))
    assert "f97" in str(excecao.value)


# A "Nota deliberada" que ficava aqui — declarando que a **ordem** dessas
# leituras NÃO era travada por teste — saiu na Stage 3.3, no commit que
# introduziu `L-ORD`. Ela era verdadeira e virou **falsa** na linha em que o
# primeiro `test_l_ord_*` entrou: hoje o concept declara a ordem (ADR 3.3.0003),
# ela vale para as duas implementações, e é justamente ela que torna o reuso
# desta suíte como contrato possível — o contrário do que a nota dizia. As
# asserções de conjunto dos testes abaixo continuam como estão, porque o que
# elas travam é **pertinência**; a ordem tem testes próprios (`test_l_ord_*`).


def test_l_e6_list_by_unit_devolve_so_a_unidade_pedida() -> None:
    fakes = _com_funcionario_gravado()
    fakes.employees.add(_funcionario(id=EmployeeId("e2"), unit_id=_U2))
    assert {registro.id for registro in fakes.employees.list_by_unit(_A, _U1)} == {_E1}
    assert {registro.id for registro in fakes.employees.list_by_unit(_A, _U2)} == {EmployeeId("e2")}


def test_l_e6_list_by_unit_esconde_desligados_por_default() -> None:
    fakes = _com_funcionario_gravado()
    fakes.employees.add(_funcionario(id=EmployeeId("e2"), active=False))
    assert {registro.id for registro in fakes.employees.list_by_unit(_A, _U1)} == {_E1}


def test_l_e6_list_by_unit_inclui_desligados_com_include_inactive() -> None:
    """O desligado **sobrevive**: some da lista default, não do sistema."""
    fakes = _com_funcionario_gravado()
    fakes.employees.add(_funcionario(id=EmployeeId("e2"), active=False))
    incluindo = fakes.employees.list_by_unit(_A, _U1, include_inactive=True)
    assert {registro.id for registro in incluindo} == {_E1, EmployeeId("e2")}
    # E continua endereçável por id, com ou sem flag.
    assert fakes.employees.find_by_id(_A, EmployeeId("e2")) is not None


# --- L-E7: consulta de referência a função -----------------------------------


def test_l_e7_exists_by_job_function_e_false_sem_referencia() -> None:
    fakes = _com_funcoes_gravadas()
    assert fakes.employees.exists_by_job_function(_A, _F1) is False


def test_l_e7_exists_by_job_function_e_true_em_qualquer_unidade_do_tenant() -> None:
    """Tenant-wide porque a **função** é tenant-scoped: uma referência em
    qualquer unidade impede a remoção."""
    fakes = _com_funcoes_gravadas()
    fakes.employees.add(_funcionario(unit_id=_U2))
    assert fakes.employees.exists_by_job_function(_A, _F1) is True


def test_l_e7_exists_by_job_function_e_true_para_referenciador_desligado() -> None:
    fakes = _com_funcoes_gravadas()
    fakes.employees.add(_funcionario(active=False))
    assert fakes.employees.exists_by_job_function(_A, _F1) is True


def test_l_e7_exists_by_job_function_e_false_para_referencia_de_outro_tenant() -> None:
    """O booleano não pode contar registros do restaurante alheio."""
    fakes = _com_funcoes_gravadas()
    fakes.employees.add(
        _funcionario(tenant_id=_B, job_function_ids=frozenset({JobFunctionId("f-b")}))
    )
    assert fakes.employees.exists_by_job_function(_A, JobFunctionId("f-b")) is False
    assert fakes.employees.exists_by_job_function(_B, JobFunctionId("f-b")) is True


# --- L-ORD: ordem total da listagem e da reidratação (ADR 3.3.0003) ----------


def _com_funcionarios_adversariais() -> StaffFakes:
    """Mesmo dado adversarial do port irmão, e pela mesma razão.

    Nome acentuado, case misto, espaço à direita e **dois homônimos com ids
    diferentes** — sem os homônimos, o desempate por `id` (o cursor da paginação
    da 3.4) é inalcançável. Aqui os homônimos são ainda mais legítimos que lá:
    nome de funcionário **não é único** por declaração (concept 3.1 §5.2).
    """
    fakes = _com_funcoes_gravadas()
    for id_, name in (
        ("e5", "Zeus"),
        ("e9", "Ana"),
        ("e1", "Álvaro"),
        ("e3", "ana"),
        ("e2", "Ana"),
        ("e4", "Zeus "),
    ):
        fakes.employees.add(_funcionario(id=EmployeeId(id_), name=name))
    return fakes


def test_l_ord_list_by_unit_ordena_por_nome_e_desempata_por_id() -> None:
    """CA10, metade `[fake]` — a sequência inteira, não "está ordenado".

    O `sorted()` do Python compara por **codepoint** e foi medido como idêntico
    a `ORDER BY name COLLATE "C", id COLLATE "C"`. Uma asserção de
    monotonicidade passaria com os dois homônimos em ordem arbitrária, que é
    exatamente onde a paginação quebra.
    """
    fakes = _com_funcionarios_adversariais()
    listados = fakes.employees.list_by_unit(_A, _U1)

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


def test_l_ord_o_desempate_e_por_id_entre_homonimos() -> None:
    """Nome de funcionário não é único **por declaração** — o desempate é a lei.

    Isolado do teste acima porque é a metade que a 3.4 usa como cursor: quando
    quebrar, é este nome que aparece no relatório de CI.
    """
    fakes = _com_funcionarios_adversariais()
    homonimos = [
        registro for registro in fakes.employees.list_by_unit(_A, _U1) if registro.name == "Ana"
    ]
    assert [registro.id for registro in homonimos] == ["e2", "e9"]


def test_l_ord_periodos_reidratam_ordenados_por_inicio_no_find_by_id() -> None:
    """CA11 — e a divergência aqui corre na direção **contrária** à habitual.

    `Employee.add_unavailability` **concatena**, não ordena, e o fake guarda o
    agregado inteiro como foi entregue. Sem a reordenação na leitura seria o
    **fake** a reprovar esta lei enquanto o Postgres passaria, porque lá a ordem
    vem do `ORDER BY start_at` do adapter. Inserir fora de ordem cronológica é o
    ponto do teste, não um detalhe do arranjo.
    """
    fakes = _com_funcoes_gravadas()
    tarde = UnavailabilityPeriod(
        start=datetime(2026, 8, 20, 8, 0), end=datetime(2026, 8, 20, 12, 0)
    )
    cedo = UnavailabilityPeriod(start=datetime(2026, 8, 3, 8, 0), end=datetime(2026, 8, 3, 12, 0))
    meio = UnavailabilityPeriod(start=datetime(2026, 8, 10, 8, 0), end=datetime(2026, 8, 10, 12, 0))
    fakes.employees.add(_funcionario(unavailabilities=(tarde, cedo, meio)))

    lido = fakes.employees.find_by_id(_A, _E1)

    assert lido is not None
    assert lido.unavailabilities == (cedo, meio, tarde)


def test_l_ord_periodos_reidratam_ordenados_tambem_no_list_by_unit() -> None:
    """A lei fala dos **dois** métodos que montam agregado, não só do `find_by_id`.

    Travar só um deixaria a listagem — que é justamente a que a 3.4 pagina —
    livre para devolver o agregado em ordem de inserção.
    """
    fakes = _com_funcoes_gravadas()
    tarde = UnavailabilityPeriod(
        start=datetime(2026, 8, 20, 8, 0), end=datetime(2026, 8, 20, 12, 0)
    )
    cedo = UnavailabilityPeriod(start=datetime(2026, 8, 3, 8, 0), end=datetime(2026, 8, 3, 12, 0))
    fakes.employees.add(_funcionario(unavailabilities=(tarde, cedo)))

    listados = fakes.employees.list_by_unit(_A, _U1)

    assert len(listados) == 1
    assert listados[0].unavailabilities == (cedo, tarde)


def test_l_ord_esta_declarada_no_port_com_a_ancora_da_stage_33() -> None:
    """CA12 travado por **teste**, não por revisão.

    Sem a âncora, a lei existe no código e não existe na fonte que o código
    nomeia — referência pendurada. Mesma forma do
    `test_l_e5_employee_in_use_error_existe_e_a_lei_esta_documentada_no_port`.
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


# --- escopo de tenant (teste dedicado do port) -------------------------------


def test_escopo_de_tenant_registro_do_a_e_invisivel_e_intocavel_com_tenant_b() -> None:
    """Um registro do tenant A é **indistinguível de inexistente** para o B.

    `add` fica **fora** deste critério pela mesma razão do port de função: a
    colisão de id é global e declarada (quadro do concept §4).

    A face de escrita desta regra — `update` com tenant alheio devolvendo
    `NotFound` e não `Relocation` — é a mesma vista pelo lado da L-E3, e está
    travada no teste irmão acima. Aqui se trava a face de leitura, listagem e
    remoção.
    """
    fakes = _com_funcionario_gravado()

    assert fakes.employees.find_by_id(_B, _E1) is None
    assert fakes.employees.list_by_unit(_B, _U1) == ()
    assert fakes.employees.list_by_unit(_B, _U1, include_inactive=True) == ()

    with pytest.raises(EmployeeNotFoundError):
        fakes.employees.delete(_B, _E1)
    assert fakes.employees.find_by_id(_A, _E1) is not None
