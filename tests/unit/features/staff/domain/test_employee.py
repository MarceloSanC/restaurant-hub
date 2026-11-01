"""Testes da entidade Employee (domain/entities/employee.py)."""

import dataclasses
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeAlreadyHasLoginError,
    EmptyJobFunctionsError,
    InvalidIdentifierError,
    InvalidNameError,
    OverlappingUnavailabilityError,
    TerminatedEmployeeLoginError,
    UnavailabilityNotFoundError,
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

pytestmark = pytest.mark.unit

_FIXA = FixedSchedule(weekly_hours=Decimal("44"))
_PREFERENCIA = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))


def _periodo(start_hour: int, end_hour: int) -> UnavailabilityPeriod:
    return UnavailabilityPeriod(
        start=datetime(2026, 8, 3, start_hour, 0),
        end=datetime(2026, 8, 3, end_hour, 0),
    )


_BASE = Employee(
    id=EmployeeId("e1"),
    tenant_id=TenantId("t1"),
    unit_id=UnitId("u1"),
    name="Maria",
    workload_profile=_FIXA,
    shift_preference=None,
    job_function_ids=frozenset({JobFunctionId("f1")}),
)


def _funcionario(**overrides: object) -> Employee:
    # dataclasses.replace chama o construtor real: cada override passa pelo
    # __post_init__ como uma construção direta passaria.
    return dataclasses.replace(_BASE, **overrides)


# --- construção válida -------------------------------------------------------


def test_cria_funcionario_valido_com_jornada_fixa() -> None:
    funcionario = _funcionario(workload_profile=_FIXA)
    assert funcionario.workload_profile == _FIXA
    assert funcionario.shift_preference is None
    assert funcionario.unavailabilities == ()


def test_cria_funcionario_valido_sob_demanda() -> None:
    funcionario = _funcionario(workload_profile=OnDemand())
    assert funcionario.workload_profile == OnDemand()


def test_jornada_fixa_pode_declarar_preferencia() -> None:
    # ADR 3.1.0004: preferência vale para ambos os perfis.
    funcionario = _funcionario(workload_profile=_FIXA, shift_preference=_PREFERENCIA)
    assert funcionario.shift_preference == _PREFERENCIA


def test_sob_demanda_pode_declarar_preferencia() -> None:
    funcionario = _funcionario(workload_profile=OnDemand(), shift_preference=_PREFERENCIA)
    assert funcionario.shift_preference == _PREFERENCIA


# --- identificadores e nome --------------------------------------------------


@pytest.mark.parametrize("invalido", ["", "   "])
def test_id_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de funcionário"):
        _funcionario(id=invalido)


@pytest.mark.parametrize("invalido", ["", "   "])
def test_tenant_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de tenant do funcionário"):
        _funcionario(tenant_id=invalido)


@pytest.mark.parametrize("invalido", ["", "   "])
def test_unidade_vazia_e_rejeitada(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de unidade do funcionário"):
        _funcionario(unit_id=invalido)


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_rejeitado_na_construcao(invalido: str) -> None:
    with pytest.raises(InvalidNameError, match="nome de funcionário"):
        _funcionario(name=invalido)


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_rejeitado_no_rename(invalido: str) -> None:
    with pytest.raises(InvalidNameError, match="nome de funcionário"):
        _funcionario().rename(invalido)


def test_nome_e_preservado_verbatim_na_construcao() -> None:
    # ADR 3.1.0002: sem trim/case silenciosos.
    assert _funcionario(name="  Cozinheiro ").name == "  Cozinheiro "


def test_nome_e_preservado_verbatim_no_rename() -> None:
    renomeado = _funcionario().rename("  João ")
    assert renomeado.name == "  João "


# --- conjunto de funções (ADR 3.1.0006) --------------------------------------


def test_conjunto_de_funcoes_vazio_e_rejeitado_na_construcao() -> None:
    with pytest.raises(EmptyJobFunctionsError, match="ao menos uma função"):
        _funcionario(job_function_ids=frozenset())


def test_conjunto_de_funcoes_vazio_e_rejeitado_no_assign() -> None:
    with pytest.raises(EmptyJobFunctionsError, match="ao menos uma função"):
        _funcionario().assign_job_functions(frozenset())


def test_uma_funcao_e_aceita() -> None:
    funcionario = _funcionario(job_function_ids=frozenset({JobFunctionId("f1")}))
    assert funcionario.job_function_ids == frozenset({JobFunctionId("f1")})


def test_varias_funcoes_sao_aceitas() -> None:
    varias = frozenset({JobFunctionId("f1"), JobFunctionId("f2"), JobFunctionId("f3")})
    assert _funcionario(job_function_ids=varias).job_function_ids == varias


def test_assign_substitui_o_conjunto_devolvendo_nova_instancia() -> None:
    original = _funcionario()
    novas = frozenset({JobFunctionId("f2"), JobFunctionId("f3")})
    atualizado = original.assign_job_functions(novas)
    assert atualizado.job_function_ids == novas
    assert original.job_function_ids == frozenset({JobFunctionId("f1")})  # original imutado


# --- indisponibilidades ------------------------------------------------------


def test_construcao_com_colecao_inicial_sobreposta_e_rejeitada() -> None:
    # Caminho de reidratação (mapper da 3.3): estado sobreposto é irrepresentável.
    with pytest.raises(OverlappingUnavailabilityError):
        _funcionario(unavailabilities=(_periodo(8, 12), _periodo(10, 14)))


def test_construcao_com_periodos_adjacentes_e_aceita() -> None:
    # Semântica semi-aberta [start, end): fim == início não conflita.
    funcionario = _funcionario(unavailabilities=(_periodo(8, 12), _periodo(12, 14)))
    assert funcionario.unavailabilities == (_periodo(8, 12), _periodo(12, 14))


def test_construcao_rejeita_sobreposicao_entre_par_nao_consecutivo() -> None:
    # Par a par de verdade: 1º-2º e 2º-3º não conflitam; SÓ o par (1º, 3º)
    # sobrepõe — um loop restrito a pares consecutivos deixaria passar.
    with pytest.raises(OverlappingUnavailabilityError):
        _funcionario(unavailabilities=(_periodo(8, 12), _periodo(14, 16), _periodo(10, 13)))


def test_add_rejeita_sobreposicao_parcial() -> None:
    funcionario = _funcionario(unavailabilities=(_periodo(8, 12),))
    with pytest.raises(OverlappingUnavailabilityError):
        funcionario.add_unavailability(_periodo(10, 14))


def test_add_rejeita_continencia_total() -> None:
    funcionario = _funcionario(unavailabilities=(_periodo(8, 16),))
    with pytest.raises(OverlappingUnavailabilityError):
        funcionario.add_unavailability(_periodo(10, 12))


def test_add_rejeita_conflito_com_o_primeiro_de_varios_existentes() -> None:
    # O novo período conflita SÓ com o primeiro da coleção — valida que o add
    # checa contra todos os existentes, não apenas o último.
    funcionario = _funcionario(unavailabilities=(_periodo(8, 10), _periodo(12, 14)))
    with pytest.raises(OverlappingUnavailabilityError):
        funcionario.add_unavailability(_periodo(9, 11))


def test_add_aceita_adjacente_devolvendo_nova_instancia() -> None:
    original = _funcionario(unavailabilities=(_periodo(8, 12),))
    atualizado = original.add_unavailability(_periodo(12, 14))
    assert atualizado.unavailabilities == (_periodo(8, 12), _periodo(12, 14))
    assert original.unavailabilities == (_periodo(8, 12),)  # original imutado


def test_remove_por_valor_devolvendo_nova_instancia() -> None:
    original = _funcionario(unavailabilities=(_periodo(8, 12), _periodo(14, 16)))
    atualizado = original.remove_unavailability(_periodo(8, 12))
    assert atualizado.unavailabilities == (_periodo(14, 16),)
    assert original.unavailabilities == (_periodo(8, 12), _periodo(14, 16))  # original imutado


def test_remove_de_periodo_inexistente_e_erro() -> None:
    with pytest.raises(UnavailabilityNotFoundError, match="não encontrado"):
        _funcionario(unavailabilities=(_periodo(8, 12),)).remove_unavailability(_periodo(14, 16))


# --- preferência e perfil ----------------------------------------------------


def test_declara_preferencia_quando_nao_havia() -> None:
    original = _funcionario(shift_preference=None)
    atualizado = original.declare_shift_preference(_PREFERENCIA)
    assert atualizado.shift_preference == _PREFERENCIA
    assert original.shift_preference is None  # original imutado


def test_substitui_preferencia_existente_por_outra() -> None:
    outra = ShiftPreference(periods=frozenset({DayPeriod.MORNING, DayPeriod.AFTERNOON}))
    atualizado = _funcionario(shift_preference=_PREFERENCIA).declare_shift_preference(outra)
    assert atualizado.shift_preference == outra


def test_declarar_none_limpa_a_preferencia() -> None:
    atualizado = _funcionario(shift_preference=_PREFERENCIA).declare_shift_preference(None)
    assert atualizado.shift_preference is None


def test_troca_perfil_de_fixa_para_sob_demanda_e_volta() -> None:
    fixa = _funcionario(workload_profile=_FIXA)
    sob_demanda = fixa.change_workload_profile(OnDemand())
    assert sob_demanda.workload_profile == OnDemand()
    assert fixa.workload_profile == _FIXA  # original imutado
    de_volta = sob_demanda.change_workload_profile(FixedSchedule(weekly_hours=Decimal("20.5")))
    assert de_volta.workload_profile == FixedSchedule(weekly_hours=Decimal("20.5"))


# --- ciclo de vida (ADR 3.2.0006) --------------------------------------------


def _demais_campos(funcionario: Employee) -> dict[str, object]:
    """Todos os campos **exceto** `active`, para a comparação campo a campo.

    `Employee.__eq__` compara só por id, então `assert copia == original` é
    vacuoso aqui: só a leitura campo a campo prova que a transição não mexeu em
    mais nada.
    """
    return {
        campo.name: getattr(funcionario, campo.name)
        for campo in dataclasses.fields(funcionario)
        if campo.name != "active"
    }


def test_funcionario_nasce_ativo_por_default() -> None:
    # `active` é aditivo: nenhum call-site da 3.1 passa o campo.
    assert _funcionario().active is True


def test_deactivate_devolve_nova_instancia_desligada() -> None:
    original = _funcionario()
    desligado = original.deactivate()
    assert desligado.active is False
    assert original.active is True  # original imutado


def test_reactivate_devolve_nova_instancia_ativa() -> None:
    original = _funcionario(active=False)
    recontratado = original.reactivate()
    assert recontratado.active is True
    assert original.active is False  # original imutado


def test_transicoes_repetidas_sao_idempotentes_no_valor() -> None:
    # ADR 3.2.0006: repetir não é erro — desligar o já desligado preserva o valor.
    assert _funcionario(active=False).deactivate().active is False
    assert _funcionario(active=True).reactivate().active is True


@pytest.mark.parametrize("transicao", ["deactivate", "reactivate"])
def test_transicao_de_ciclo_de_vida_nao_altera_nenhum_outro_campo(transicao: str) -> None:
    # O desligado SOBREVIVE com toda a história: funções, indisponibilidades e
    # preferência ficam onde estavam.
    original = _funcionario(
        shift_preference=_PREFERENCIA,
        job_function_ids=frozenset({JobFunctionId("f1"), JobFunctionId("f2")}),
        unavailabilities=(_periodo(8, 12), _periodo(14, 16)),
    )
    transicionado: Employee = getattr(original, transicao)()
    assert _demais_campos(transicionado) == _demais_campos(original)


def test_estado_de_ciclo_de_vida_nao_e_atribuivel() -> None:
    # O campo novo entra sob a mesma regra frozen do resto: só via transição.
    with pytest.raises(dataclasses.FrozenInstanceError):
        _funcionario().active = False  # type: ignore[misc]


# --- identidade e imutabilidade ----------------------------------------------


def test_entidade_e_imutavel() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _funcionario().name = "Outro"  # type: ignore[misc]


def test_igualdade_por_identidade_ignora_demais_campos() -> None:
    assert _funcionario(name="Maria") == _funcionario(name="Joana")


def test_ids_diferentes_nao_sao_iguais() -> None:
    assert _funcionario(id="e1") != _funcionario(id="e2")


def test_hash_segue_a_identidade() -> None:
    assert len({_funcionario(name="Maria"), _funcionario(name="Joana")}) == 1


def test_comparacao_com_outro_tipo_nao_e_igual() -> None:
    assert _funcionario() != "e1"


class _SempreIgual:
    """Objeto que se declara igual a qualquer coisa, para testar a reflexão."""

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0


def test_eq_delega_ao_outro_operando_quando_o_tipo_e_estranho() -> None:
    # __eq__ devolve NotImplemented para tipo alheio: o outro operando decide.
    assert _funcionario() == _SempreIgual()
    assert _SempreIgual() == _funcionario()


# ---------------------------------------------------------------------------
# CA16 / CA18 — o byte NUL, e só ele
# ---------------------------------------------------------------------------

# Bateria adversarial medida na Stage 3.3: destes cinco, **nenhum** divergia
# entre fake e Postgres — só o byte NUL divergia. Congelá-los aqui é o que
# prova que a restrição da 3.4 é do tamanho da divergência, e não maior (CA18).
_NOMES_ADVERSARIAIS = (
    "José Antônio",
    "\U0001f469\u200d\U0001f373",
    "linha1\nlinha2",
    'Ana "Nana" O\'Brien',
    "a" * 1000,
)
_IDS_ADVERSARIAIS = ["acento", "emoji_zwj", "quebra_de_linha", "aspas", "mil_caracteres"]


@pytest.mark.parametrize("nome", ["a\x00b", "\x00", "Maria\x00"])
def test_ca16_nome_com_byte_nul_e_rejeitado_na_construcao(nome: str) -> None:
    """O `psycopg` recusa o NUL client-side; sem esta regra o fake gravaria o
    que o banco real não aceita — a divergência que a 3.3 mediu
    (ADR 3.4.0003 §1)."""
    with pytest.raises(InvalidNameError, match="nome de funcionário"):
        _funcionario(name=nome)


def test_ca16_nome_com_byte_nul_e_rejeitado_no_rename() -> None:
    """`rename` passa por `dataclasses.replace`, logo pelo mesmo `__post_init__`."""
    with pytest.raises(InvalidNameError, match="nome de funcionário"):
        _funcionario().rename("Ma\x00ria")


def test_ca16_a_mensagem_do_nul_nao_afirma_que_o_nome_esta_vazio() -> None:
    """Recusar por "não pode ser vazio" um nome que tem conteúdo descreveria
    o defeito errado a quem recebe o 422 na Stage 3.6."""
    with pytest.raises(InvalidNameError) as excinfo:
        _funcionario(name="Ma\x00ria")
    assert "byte NUL" in str(excinfo.value)


@pytest.mark.parametrize("nome", _NOMES_ADVERSARIAIS, ids=_IDS_ADVERSARIAIS)
def test_ca18_nomes_adversariais_sem_nul_continuam_aceitos_verbatim(nome: str) -> None:
    """A restrição não cresceu: nada de C0, normalização de espaço ou limite."""
    assert _funcionario(name=nome).name == nome


# --- vínculo de login (Stage 3.5, ADR 3.5.0004; concept CA01) --------------------

_LOGIN = UserId("login-1")


def _campos_exceto(funcionario: Employee, *excluidos: str) -> dict[str, object]:
    return {
        campo.name: getattr(funcionario, campo.name)
        for campo in dataclasses.fields(funcionario)
        if campo.name not in excluidos
    }


def test_funcionario_nasce_sem_login() -> None:
    """`None` é o estado default: login é ato explícito do gerente (workforce §3.8)."""
    assert _BASE.user_id is None


@pytest.mark.parametrize("invalido", ["", "   "])
def test_login_vazio_e_rejeitado_na_construcao(invalido: str) -> None:
    """Presente ⇒ não-vazio. Um `""` reidratado seria vínculo-fantasma."""
    with pytest.raises(InvalidIdentifierError, match="login do funcionário"):
        _funcionario(user_id=UserId(invalido))


@pytest.mark.parametrize("invalido", ["", "   "])
def test_login_vazio_e_rejeitado_no_link_login(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="login do funcionário"):
        _BASE.link_login(UserId(invalido))


def test_link_login_devolve_nova_instancia_com_o_login_e_nada_mais() -> None:
    vinculado = _BASE.link_login(_LOGIN)

    assert vinculado is not _BASE
    assert vinculado.user_id == _LOGIN
    assert _BASE.user_id is None
    assert _campos_exceto(vinculado, "user_id") == _campos_exceto(_BASE, "user_id")


def test_assert_can_link_login_aceita_registro_ativo_sem_login() -> None:
    _BASE.assert_can_link_login()  # não levanta


def test_ja_vinculado_recusa_segundo_login_na_guarda_e_no_link_login() -> None:
    """Definido **uma vez**: não há "trocar o login" nesta Stage (concept §5.5).

    As duas portas são asseridas de propósito — `link_login` chama a guarda por
    dentro, e remover essa chamada interna deixaria a guarda verde e a transição
    aberta (CA28(h)).
    """
    vinculado = _BASE.link_login(_LOGIN)

    with pytest.raises(EmployeeAlreadyHasLoginError, match="e1"):
        vinculado.assert_can_link_login()
    with pytest.raises(EmployeeAlreadyHasLoginError, match="e1"):
        vinculado.link_login(UserId("login-2"))


def test_desligado_recusa_login_na_guarda_e_no_link_login() -> None:
    """Criar login é conceder acesso, e desligar cortou o acesso que o registro concede.

    ADR 3.5.0003; o alcance do corte é o do ADR 3.8.0001.
    """
    desligado = _BASE.deactivate()

    with pytest.raises(TerminatedEmployeeLoginError, match="e1"):
        desligado.assert_can_link_login()
    with pytest.raises(TerminatedEmployeeLoginError, match="e1"):
        desligado.link_login(_LOGIN)


def test_precedencia_vinculado_vence_desligado() -> None:
    """Desligado **e** vinculado ⇒ o erro é o de já-vinculado (CA01).

    A ordem é do domínio, não acidente: o vínculo é o fato mais específico
    sobre o registro, e é o que o chamador precisa saber primeiro.
    """
    desligado_com_login = _BASE.link_login(_LOGIN).deactivate()

    with pytest.raises(EmployeeAlreadyHasLoginError):
        desligado_com_login.assert_can_link_login()


def test_desligar_mantem_o_login_como_historia() -> None:
    """O desligado com login **mantém** o `user_id` (concept §5.5, ADR 3.2.0006)."""
    desligado = _BASE.link_login(_LOGIN).deactivate()

    assert desligado.user_id == _LOGIN
    assert desligado.active is False


def test_recontratar_nao_mexe_no_login() -> None:
    recontratado = _BASE.link_login(_LOGIN).deactivate().reactivate()

    assert recontratado.user_id == _LOGIN


def test_login_nao_e_atribuivel() -> None:
    """A única porta é `link_login` — a entidade é `frozen`."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        _BASE.user_id = _LOGIN  # type: ignore[misc]
