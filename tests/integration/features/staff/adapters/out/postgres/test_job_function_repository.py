"""`PostgresJobFunctionRepository` contra o banco real — L-JF1…L-JF5 e `L-ORD`.

**Por que estes testes existem se a suíte de contrato vai rodar as mesmas leis
contra o mesmo adapter na Task 09.** Duas razões, e as duas importam:

1. **Ordem de descoberta.** A Task 09 é o único lugar onde uma lei pode reprovar
   por **divergência fake↔adapter**; se o adapter chegasse lá sem nunca ter
   tocado o banco, um vermelho seria ambíguo entre "o adapter está errado" e "a
   lei está errada". Aqui o adapter é verificado sozinho, e um vermelho só pode
   ser dele.
2. **O que só o banco decide.** O `RESTRICT` da FK, o índice único verbatim, a
   ordem sob a colação real e o `rowcount` de um `UPDATE` que não achou linha
   nenhuma não têm contrapartida no fake — são o comportamento que a Stage
   inteira existe para confirmar.

O funcionário referenciador é semeado por **SQL direto**: o adapter de
funcionário só nasce na Task 07, e depender dele aqui inverteria a ordem de
dependência das Tasks.
"""

from decimal import Decimal

import pytest
from sqlalchemy import Engine, text

from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from restaurant_hub.features.staff.application.errors import (
    JobFunctionAlreadyExistsError,
    JobFunctionInUseError,
    JobFunctionNameAlreadyExistsError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
)

pytestmark = [pytest.mark.integration]

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")


@pytest.fixture
def repositorio(banco_limpo: Engine) -> PostgresJobFunctionRepository:
    """O adapter sobre o `Engine` de teste, com as tabelas vazias."""
    return PostgresJobFunctionRepository(banco_limpo)


def _funcao(
    id_: JobFunctionId = _F1, tenant: TenantId = _A, name: str = "Cozinheiro"
) -> JobFunction:
    return JobFunction(id=id_, tenant_id=tenant, name=name)


def _semear_funcionario_referenciando(
    engine: Engine,
    job_function_id: JobFunctionId,
    *,
    tenant: TenantId = _A,
    employee_id: str = "e1",
    active: bool = True,
) -> None:
    """Funcionário + vínculo por SQL direto — o adapter deles é da Task 07."""
    with engine.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employees "
                "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
                "VALUES (:id, :t, 'u1', 'Maria', 'fixed', :horas, :ativo)"
            ),
            {"id": employee_id, "t": tenant, "horas": Decimal("44"), "ativo": active},
        )
        conexao.execute(
            text(
                "INSERT INTO employee_job_functions (employee_id, job_function_id, tenant_id) "
                "VALUES (:e, :f, :t)"
            ),
            {"e": employee_id, "f": job_function_id, "t": tenant},
        )


# ---------------------------------------------------------------------------
# L-JF1 — `add` é inserção, não upsert
# ---------------------------------------------------------------------------


def test_l_jf1_add_grava_e_e_lido_de_volta(repositorio: PostgresJobFunctionRepository) -> None:
    repositorio.add(_funcao())
    gravada = repositorio.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"
    assert gravada.tenant_id == _A


def test_l_jf1_add_com_id_ja_gravado_e_erro_e_nao_altera_o_registro(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """A PK recusa; a tradução por operação transforma em erro tipado.

    Sem `ON CONFLICT` — um upsert silencioso é a dívida exata que a 2.3 pagou
    (ADR 2.3.0003), e ele passaria neste teste se a asserção fosse só "não
    explodiu".
    """
    repositorio.add(_funcao())
    with pytest.raises(JobFunctionAlreadyExistsError) as excecao:
        repositorio.add(_funcao(name="Chapeiro"))
    assert "f1" in str(excecao.value)

    gravada = repositorio.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"  # campos antigos, não os da tentativa


def test_l_jf1_add_com_id_gravado_em_outro_tenant_tambem_e_erro(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """CA5 — a colisão de **id** é global: a PK não inclui o tenant."""
    repositorio.add(_funcao())
    with pytest.raises(JobFunctionAlreadyExistsError):
        repositorio.add(_funcao(tenant=_B))


def test_l_jf1_add_com_nome_ja_usado_no_tenant_e_erro_com_o_nome_na_mensagem(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """O índice único `(tenant_id, name)` recusa — e a mensagem cita o **nome**.

    Citar o id numa mensagem de "nome já usado" descreveria o conflito errado
    com a confiança de quem sabe; é o que `_detalhe_do_conflito` evita.
    """
    repositorio.add(_funcao())
    with pytest.raises(JobFunctionNameAlreadyExistsError) as excecao:
        repositorio.add(_funcao(id_=_F2))
    assert "Cozinheiro" in str(excecao.value)
    assert repositorio.find_by_id(_A, _F2) is None


def test_l_jf1_o_mesmo_nome_em_outro_tenant_e_aceito(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """A unicidade de **nome** é por tenant — ao contrário da de id."""
    repositorio.add(_funcao())
    repositorio.add(_funcao(id_=_F2, tenant=_B))
    gravada = repositorio.find_by_id(_B, _F2)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"


@pytest.mark.parametrize("variante", ["cozinheiro ", "Cozinheiro ", "COZINHEIRO", " Cozinheiro"])
def test_ca9_as_quatro_variantes_verbatim_convivem_com_o_original(
    repositorio: PostgresJobFunctionRepository, variante: str
) -> None:
    """CA9 — contra o banco, que é onde a normalização silenciosa se instalaria.

    Um índice sobre `lower(btrim(name))` — ou um `ILIKE` na guarda — recusaria
    cada uma destas, e a recusa pareceria correta. O nome é **verbatim**
    (workforce §3.2, ADR 3.1.0002): quem digitou a variante quis a variante.
    """
    repositorio.add(_funcao())
    repositorio.add(_funcao(id_=_F2, name=variante))

    gravada = repositorio.find_by_id(_A, _F2)
    assert gravada is not None
    assert gravada.name == variante


def test_find_by_name_e_verbatim_no_banco(repositorio: PostgresJobFunctionRepository) -> None:
    """`=`, nunca `ILIKE`/`lower()` — o método mais fácil de "consertar" errado."""
    repositorio.add(_funcao())

    encontrada = repositorio.find_by_name(_A, "Cozinheiro")
    assert encontrada is not None
    assert encontrada.id == _F1

    for variante in ("cozinheiro ", "COZINHEIRO", " Cozinheiro", "Cozinheiro "):
        assert repositorio.find_by_name(_A, variante) is None
    # E o escopo de tenant vale também aqui.
    assert repositorio.find_by_name(_B, "Cozinheiro") is None


# ---------------------------------------------------------------------------
# L-JF2 — `update` é `UPDATE`, não upsert
# ---------------------------------------------------------------------------


def test_l_jf2_update_grava_o_novo_nome(repositorio: PostgresJobFunctionRepository) -> None:
    repositorio.add(_funcao())
    repositorio.update(_funcao(name="Chapeiro"))
    gravada = repositorio.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Chapeiro"


def test_l_jf2_update_de_funcao_inexistente_nao_grava_nada(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """`rowcount == 0` ⇒ `NotFound`, e **nada** é inserido — não é upsert."""
    with pytest.raises(JobFunctionNotFoundError):
        repositorio.update(_funcao())
    assert repositorio.find_by_id(_A, _F1) is None
    assert repositorio.list_by_tenant(_A) == ()


def test_l_jf2_update_com_tenant_alheio_nao_grava_nada(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """ "Inexistente no tenant" inclui "existe, mas é de outro restaurante".

    O `tenant_id` está no `WHERE`, então o `UPDATE` não acha linha e o
    `rowcount` responde — o registro alheio não é tocado nem confirmado.
    """
    repositorio.add(_funcao())
    with pytest.raises(JobFunctionNotFoundError):
        repositorio.update(_funcao(tenant=_B, name="Chapeiro"))
    gravada = repositorio.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"


def test_l_jf2_renomear_para_o_proprio_nome_nao_e_conflito(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """O índice único resolve sozinho: o `UPDATE` atualiza a própria linha.

    Uma pré-checagem por `find_by_name` teria de reimplementar a exceção de si
    mesma — e ainda seria check-then-act sob concorrência.
    """
    repositorio.add(_funcao())
    repositorio.update(_funcao(name="Cozinheiro"))
    gravada = repositorio.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"


def test_l_jf2_update_para_nome_de_outra_funcao_do_tenant_e_erro(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    repositorio.add(_funcao())
    repositorio.add(_funcao(id_=_F2, name="Chapeiro"))
    with pytest.raises(JobFunctionNameAlreadyExistsError) as excecao:
        repositorio.update(_funcao(id_=_F2, name="Cozinheiro"))
    assert "Cozinheiro" in str(excecao.value)

    gravada = repositorio.find_by_id(_A, _F2)
    assert gravada is not None
    assert gravada.name == "Chapeiro"


def test_update_nao_move_a_funcao_de_tenant(repositorio: PostgresJobFunctionRepository) -> None:
    """§5.3 — `tenant_id` não entra no `SET`, e o banco confirma.

    O `UPDATE` de uma função com `tenant_id` divergente nem acha linha; o que
    este teste fixa é o outro lado: depois de um `update` legítimo, o tenant
    gravado continua o mesmo. Um `SET tenant_id = …` passaria em todos os outros
    testes deste arquivo.
    """
    repositorio.add(_funcao())
    repositorio.update(_funcao(name="Chapeiro"))
    gravada = repositorio.find_by_id(_A, _F1)
    assert gravada is not None
    assert gravada.tenant_id == _A
    assert repositorio.find_by_id(_B, _F1) is None


# ---------------------------------------------------------------------------
# L-JF3 — remoção guardada
# ---------------------------------------------------------------------------


def test_l_jf3_delete_remove_a_funcao_sem_referencias(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    repositorio.add(_funcao())
    repositorio.delete(_A, _F1)
    assert repositorio.find_by_id(_A, _F1) is None


def test_l_jf3_delete_de_funcao_inexistente_no_tenant_e_not_found(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    with pytest.raises(JobFunctionNotFoundError):
        repositorio.delete(_A, _F1)


def test_ca7_delete_de_funcao_referenciada_por_desligado_e_in_use(
    repositorio: PostgresJobFunctionRepository, banco_limpo: Engine
) -> None:
    """CA7 — a referência conta **independentemente do estado** do funcionário.

    A tabela de vínculo não conhece `active`, e é isso que se quer: apagar a
    função deixaria o cadastro do desligado apontando para função inexistente,
    furando a invariante "ao menos uma função" da 3.1 — que ninguém revalidaria,
    porque o registro está fora da listagem default.

    E a função **continua legível** depois do erro: a transação inteira reverteu.
    """
    repositorio.add(_funcao())
    _semear_funcionario_referenciando(banco_limpo, _F1, active=False)

    with pytest.raises(JobFunctionInUseError) as excecao:
        repositorio.delete(_A, _F1)
    assert "f1" in str(excecao.value)

    ainda_la = repositorio.find_by_id(_A, _F1)
    assert ainda_la is not None
    assert ainda_la.name == "Cozinheiro"


def test_l_jf3_delete_de_funcao_referenciada_por_ativo_tambem_e_in_use(
    repositorio: PostgresJobFunctionRepository, banco_limpo: Engine
) -> None:
    repositorio.add(_funcao())
    _semear_funcionario_referenciando(banco_limpo, _F1, active=True)
    with pytest.raises(JobFunctionInUseError):
        repositorio.delete(_A, _F1)


def test_l_jf3_not_found_vence_in_use_com_tenant_alheio(
    repositorio: PostgresJobFunctionRepository, banco_limpo: Engine
) -> None:
    """A ordem de checagem é normativa, e este é o caso que a discrimina.

    A função **está** referenciada. Responder `JobFunctionInUseError` ao tenant
    B confirmaria que ela existe **e** que está em uso no restaurante alheio
    (§5.4). O lookup por `(tenant_id, id)` vem antes, e por isso a resposta é
    `NotFound`.
    """
    repositorio.add(_funcao())
    _semear_funcionario_referenciando(banco_limpo, _F1)

    with pytest.raises(JobFunctionNotFoundError):
        repositorio.delete(_B, _F1)
    assert repositorio.find_by_id(_A, _F1) is not None


# ---------------------------------------------------------------------------
# L-JF4 / L-JF5 / L-ORD — leitura em lote, listagem e ordem
# ---------------------------------------------------------------------------


def test_l_jf4_find_all_by_ids_devolve_so_as_encontradas_sem_levantar(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    repositorio.add(_funcao())
    encontradas = repositorio.find_all_by_ids(_A, frozenset({_F1, JobFunctionId("f99")}))
    assert {funcao.id for funcao in encontradas} == {_F1}


def test_l_jf4_find_all_by_ids_ignora_funcao_de_outro_tenant(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    repositorio.add(_funcao())
    repositorio.add(_funcao(id_=_F2, tenant=_B, name="Chapeiro"))
    encontradas = repositorio.find_all_by_ids(_A, frozenset({_F1, _F2}))
    assert {funcao.id for funcao in encontradas} == {_F1}


def test_l_jf4_find_all_by_ids_com_conjunto_vazio_devolve_vazio(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """L-JF4 exige que **não levante**; o adapter nem vai ao banco.

    É o caminho que `create_employee` percorre com conjunto vazio: nada falta, e
    quem rejeita conjunto vazio é o domínio, na construção.
    """
    repositorio.add(_funcao())
    assert repositorio.find_all_by_ids(_A, frozenset()) == ()


def test_l_jf5_list_by_tenant_devolve_todas_do_tenant_e_nenhuma_de_outro(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    repositorio.add(_funcao())
    repositorio.add(_funcao(id_=_F2, name="Chapeiro"))
    repositorio.add(_funcao(id_=JobFunctionId("f3"), tenant=_B, name="Garçom"))

    assert {funcao.id for funcao in repositorio.list_by_tenant(_A)} == {_F1, _F2}
    assert {funcao.id for funcao in repositorio.list_by_tenant(_B)} == {JobFunctionId("f3")}


def _semear_adversariais(repositorio: PostgresJobFunctionRepository) -> None:
    """Nome acentuado, case misto e espaço à direita — o mesmo dado do contrato.

    **Sem homônimos:** L-JF1 os torna irrepresentáveis no tenant (índice único
    `(tenant_id, name)`), e as duas listagens deste port são tenant-scoped. O
    desempate por `id` é travado onde é alcançável — no port de funcionário — e
    pela asserção sobre o SQL compilado (CA10b, Task 08). Ver a `[deviation]`
    datada na §7 do technical.
    """
    for id_, name in (
        ("f5", "Zeus"),
        ("f1", "Álvaro"),
        ("f3", "ana"),
        ("f2", "Ana"),
        ("f4", "Zeus "),
    ):
        repositorio.add(_funcao(id_=JobFunctionId(id_), name=name))


def test_l_ord_list_by_tenant_ordena_por_codepoint_como_o_sorted_do_python(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """`L-ORD` contra o banco real — a sequência inteira, não monotonicidade.

    Maiúsculas antes de minúsculas, o acentuado (U+00C1) **depois** de `"ana"`
    (U+0061), e o espaço à direita depois do prefixo. Esta asserção **não**
    reprova a omissão do `COLLATE "C"` nesta imagem (musl, cuja colação default
    já é byte-order) — quem reprova é a asserção sobre o SQL compilado, na
    Task 08. Aqui se confirma que o resultado bate com o `sorted()` do Python,
    que é o que permite o corpo único da suíte de contrato.
    """
    _semear_adversariais(repositorio)
    listadas = repositorio.list_by_tenant(_A)

    assert [(funcao.name, funcao.id) for funcao in listadas] == [
        ("Ana", "f2"),
        ("Zeus", "f5"),
        ("Zeus ", "f4"),
        ("ana", "f3"),
        ("Álvaro", "f1"),
    ]
    assert [(funcao.name, funcao.id) for funcao in listadas] == sorted(
        (funcao.name, funcao.id) for funcao in listadas
    )


def test_l_ord_find_all_by_ids_ordena_igual_e_nao_herda_a_ordem_do_pedido(
    repositorio: PostgresJobFunctionRepository,
) -> None:
    """O parâmetro é `frozenset`: não há ordem no pedido para o resultado herdar."""
    _semear_adversariais(repositorio)
    pedidas = frozenset({JobFunctionId("f3"), JobFunctionId("f1"), JobFunctionId("f2")})

    encontradas = repositorio.find_all_by_ids(_A, pedidas)

    assert [(funcao.name, funcao.id) for funcao in encontradas] == [
        ("Ana", "f2"),
        ("ana", "f3"),
        ("Álvaro", "f1"),
    ]
