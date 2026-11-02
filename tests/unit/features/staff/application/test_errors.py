"""Testes da hierarquia de erros da camada de aplicação do BC staff (concept 3.2 §11; 3.9).

Espelho de `tests/unit/features/identity/application/test_errors.py`. Cada erro
desta camada tem **uma** raiz, escolhida pelo significado (ADR 3.9.0001, que supera
o 2.2.0003): `StaffError` quando nomeia regra do produto, `StaffApplicationError`
quando o caso de uso não pôde ser atendido por motivo que não é regra (lookup,
colisão de id gerado). A partição é travada por **igualdade de conjuntos**.
"""

import inspect

import pytest

from restaurant_hub.features.staff.application import errors
from restaurant_hub.features.staff.application.errors import StaffApplicationError
from restaurant_hub.features.staff.domain.exceptions.errors import (
    StaffError,
    UnavailabilityNotFoundError,
)
from restaurant_hub.shared.application.errors import ApplicationError
from restaurant_hub.shared.domain.exceptions.base import DomainError

pytestmark = pytest.mark.unit

# Falhas que não são regra (concept 3.9 §4): lookup no tenant/unidade e colisão de
# id gerado. O resto do módulo nomeia regra do produto e fica sob `StaffError`.
_DE_APLICACAO = (
    errors.JobFunctionNotFoundError,
    errors.EmployeeNotFoundError,
    errors.JobFunctionAlreadyExistsError,
    errors.EmployeeAlreadyExistsError,
)

# Conflito, uso, relocalização, cópia e — desde a 3.5 — as três recusas de login da
# camada de aplicação: regras do produto.
_DE_DOMINIO = (
    errors.JobFunctionNameAlreadyExistsError,
    errors.JobFunctionInUseError,
    errors.EmployeeInUseError,
    errors.EmployeeRelocationError,
    errors.SameUnitCopyError,
    errors.LoginEmailAlreadyInUseError,
    errors.InvalidLoginEmailError,
    errors.EmployeeHasLoginError,
)


def _application_error_classes() -> list[type]:
    """Todas as classes declaradas em `application/errors.py`.

    O filtro é **só** por módulo de origem, deliberadamente. Filtrar também por
    `issubclass(obj, BaseException)` pareceria mais preciso e seria um falso
    verde: uma classe que esquecesse a base de exceção simplesmente não entraria
    na lista, e a suíte passaria — enquanto `raise` dela explodiria em runtime
    com `TypeError` e viraria 500. A checagem de base é **asserção**, não filtro.
    """
    return [
        obj
        for _, obj in inspect.getmembers(errors, inspect.isclass)
        # A raiz de aplicação (Stage 3.9) não é um erro: é o tipo sobre o qual o
        # handler é registrado, e tem teste próprio abaixo.
        if obj.__module__ == errors.__name__ and obj is not StaffApplicationError
    ]


def test_modulo_declara_as_doze_excecoes_esperadas() -> None:
    """Guarda a lista: classe nova ou removida força revisão consciente do teste."""
    nomes = {cls.__name__ for cls in _application_error_classes()}
    assert nomes == {
        # Ausência — os únicos dois 404 desta camada.
        "JobFunctionNotFoundError",
        "EmployeeNotFoundError",
        # Conflito de nome (verbatim, no tenant) e de id (`add` é inserção,
        # não upsert — L-JF1/L-E1, ADR 2.3.0003).
        "JobFunctionNameAlreadyExistsError",
        "JobFunctionAlreadyExistsError",
        "EmployeeAlreadyExistsError",
        # Guardas de remoção. `EmployeeInUseError` nasce SEM produtor em v1
        # (L-E5): publicada agora para o Step 4 não retroagir o contrato.
        "JobFunctionInUseError",
        "EmployeeInUseError",
        # Localização imutável (L-E3) e destino da cópia igual à origem.
        "EmployeeRelocationError",
        "SameUnitCopyError",
        # Stage 3.5 — o vocabulário de staff para as duas traduções do gateway
        # (L-IG2) e a guarda nova da remoção (ADR 3.5.0003 §1b).
        "LoginEmailAlreadyInUseError",
        "InvalidLoginEmailError",
        "EmployeeHasLoginError",
    }


def test_a_particao_dominio_aplicacao_cobre_todos_os_erros_do_modulo() -> None:
    """As duas tuplas literais **particionam** o módulo — nenhum erro fica de fora.

    Sem esta asserção as duas listas seriam amostras: um erro futuro escaparia da
    checagem de raiz por ninguém o ter acrescentado a uma das tuplas.
    """
    assert set(_DE_DOMINIO) | set(_DE_APLICACAO) == set(_application_error_classes())
    assert not set(_DE_DOMINIO) & set(_DE_APLICACAO)


@pytest.mark.parametrize("error_class", _application_error_classes(), ids=lambda c: c.__name__)
def test_todo_erro_da_camada_e_levantavel(error_class: type) -> None:
    """Uma classe sem base de exceção não é levantável: `raise` dela dá `TypeError`."""
    assert issubclass(error_class, BaseException)


@pytest.mark.parametrize("error_class", _DE_APLICACAO, ids=lambda c: c.__name__)
def test_falhas_que_nao_sao_regra_tem_so_a_raiz_de_aplicacao(error_class: type) -> None:
    """Uma base só, e nenhum caminho até `DomainError` (ADR 3.9.0001 §2)."""
    assert error_class.__bases__ == (StaffApplicationError,)
    assert not issubclass(error_class, DomainError)


@pytest.mark.parametrize("error_class", _DE_DOMINIO, ids=lambda c: c.__name__)
def test_regras_do_produto_tem_so_a_raiz_de_dominio(error_class: type) -> None:
    """Conflito e ausência são opostos no significado — e agora também na raiz."""
    assert error_class.__bases__ == (StaffError,)
    assert not issubclass(error_class, ApplicationError)


def test_a_raiz_de_aplicacao_e_filha_direta_de_application_error() -> None:
    assert StaffApplicationError.__bases__ == (ApplicationError,)


def test_indisponibilidade_nao_encontrada_fica_no_dominio() -> None:
    """`UnavailabilityNotFoundError` no domínio é decisão, não esquecimento.

    O nome diz "not found" e mesmo assim ela fica sob `StaffError`: fala de um
    **valor dentro do agregado** (um período que aquele registro não tem), não de um
    recurso endereçável — o funcionário existe e foi encontrado (concept 3.2 §4;
    ADR 3.9.0001 §3).
    """
    assert UnavailabilityNotFoundError.__bases__ == (StaffError,)
    assert not issubclass(UnavailabilityNotFoundError, ApplicationError)


def test_mensagens_identificam_o_recurso_ou_a_regra_violada() -> None:
    """Cada erro instanciado produz mensagem útil (executa o `__init__`)."""
    assert "f-1" in str(errors.JobFunctionNotFoundError("f-1"))
    assert "e-1" in str(errors.EmployeeNotFoundError("e-1"))
    assert "Cozinheiro" in str(errors.JobFunctionNameAlreadyExistsError("Cozinheiro"))
    assert "f-1" in str(errors.JobFunctionAlreadyExistsError("f-1"))
    assert "e-1" in str(errors.EmployeeAlreadyExistsError("e-1"))
    assert "f-1" in str(errors.JobFunctionInUseError("f-1"))
    assert "e-1" in str(errors.EmployeeInUseError("e-1"))
    assert "u-1" in str(errors.SameUnitCopyError("u-1"))
    assert "'ana@x.com'" in str(errors.LoginEmailAlreadyInUseError("ana@x.com"))
    assert "'nao-e-email'" in str(errors.InvalidLoginEmailError("nao-e-email"))
    assert "e-1" in str(errors.EmployeeHasLoginError("e-1"))


def test_email_em_uso_cita_so_o_email_enviado() -> None:
    """A mensagem não diz **de quem** é o e-mail nem em que tenant (concept 3.5 §6.1).

    É o oráculo de existência global de conta que a 2.5 §13 registrou: a
    resposta 409 já confirma que o e-mail existe em algum tenant, e a mensagem
    não pode acrescentar nada a isso.
    """
    assert str(errors.LoginEmailAlreadyInUseError("ana@x.com")) == (
        "e-mail já usado como login: 'ana@x.com'"
    )


def test_remocao_de_vinculado_aponta_o_caminho() -> None:
    """A guarda diz o que fazer: desligar (ADR 3.5.0003 §1b)."""
    assert "desligue-o" in str(errors.EmployeeHasLoginError("e-1"))


def test_erro_de_relocalizacao_cita_as_duas_unidades_e_nao_o_tenant() -> None:
    """É erro **intra-tenant** (concept §4/L-E3): citar tenant seria ruído.

    Com tenant divergente o erro é `EmployeeNotFoundError` — este só é
    alcançável depois de o registro ter sido encontrado no tenant pedido, então
    a informação que falta ao leitor são as duas unidades, não o tenant.
    """
    mensagem = str(errors.EmployeeRelocationError("e-1", "unidade-gravada", "unidade-enviada"))
    assert "e-1" in mensagem
    assert "unidade-gravada" in mensagem
    assert "unidade-enviada" in mensagem
    assert "tenant" not in mensagem.lower()
