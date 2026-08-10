"""Testes da hierarquia de erros da camada de aplicação do BC staff (concept §11).

Espelho de `tests/unit/features/identity/application/test_errors.py`. A
invariante protegida é de **segurança operacional**, não de estética: um erro
desta camada que escape de `DomainError` vira HTTP 500 na Stage 3.4 em vez de um
4xx (ADR 2.2.0003). O teste percorre o módulo por introspecção, então uma classe
nova que esqueça a base certa quebra a suíte — em vez de falhar em silêncio
meses depois, na API.
"""

import inspect

import pytest

from restaurant_hub.features.staff.application import errors
from restaurant_hub.features.staff.domain.exceptions.errors import (
    StaffError,
    UnavailabilityNotFoundError,
)
from restaurant_hub.shared.domain.exceptions.base import DomainError, NotFoundError

pytestmark = pytest.mark.unit

# Os DOIS erros que representam "recurso inexistente" e, por isso, devem
# alcançar o handler 404 antes do 422 (concept §4).
_NOT_FOUND_ERRORS = (
    errors.JobFunctionNotFoundError,
    errors.EmployeeNotFoundError,
)

# Todo o resto: conflito, uso, relocalização e cópia — nenhum é ausência.
_NON_NOT_FOUND_ERRORS = (
    errors.JobFunctionNameAlreadyExistsError,
    errors.JobFunctionAlreadyExistsError,
    errors.EmployeeAlreadyExistsError,
    errors.JobFunctionInUseError,
    errors.EmployeeInUseError,
    errors.EmployeeRelocationError,
    errors.SameUnitCopyError,
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
        if obj.__module__ == errors.__name__
    ]


def test_modulo_declara_as_nove_excecoes_esperadas() -> None:
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
    }


def test_a_particao_404_x_nao_404_cobre_todos_os_erros_do_modulo() -> None:
    """As duas tuplas literais **particionam** o módulo — nenhum erro fica de fora.

    Sem esta asserção as duas listas são só amostras: um décimo erro futuro
    entraria na lista de nomes esperados (que o teste acima trava) e **escaparia**
    da checagem `not issubclass(..., NotFoundError)`, porque ninguém o teria
    acrescentado à tupla. Um `*AlreadyExistsError` acidentalmente 404 passaria
    verde — que é exatamente o defeito que a partição existe para impedir.

    (O espelho deste teste em identity tem o mesmo flanco aberto; o defeito não
    foi replicado aqui de propósito.)
    """
    particao = set(_NOT_FOUND_ERRORS) | set(_NON_NOT_FOUND_ERRORS)
    assert particao == set(_application_error_classes())
    # E são disjuntas: um erro em ambas as tuplas satisfaria a união acima e
    # tornaria as duas asserções contraditórias sobre a mesma classe.
    assert not set(_NOT_FOUND_ERRORS) & set(_NON_NOT_FOUND_ERRORS)


@pytest.mark.parametrize("error_class", _application_error_classes())
def test_todo_erro_de_aplicacao_e_staff_error_e_domain_error(error_class: type) -> None:
    """Nenhum erro de negócio desta camada pode escapar para 500 na 3.4.

    `BaseException` primeiro: uma classe sem base de exceção não é levantável, e
    `raise` dela dá `TypeError` — 500 garantido, que é exatamente o que o
    ADR 2.2.0003 existe para impedir.
    """
    assert issubclass(error_class, BaseException)
    assert issubclass(error_class, StaffError)
    assert issubclass(error_class, DomainError)


@pytest.mark.parametrize("error_class", _NOT_FOUND_ERRORS)
def test_erros_de_nao_encontrado_ordenam_bc_antes_de_404_antes_de_422(
    error_class: type[Exception],
) -> None:
    """A ORDEM na MRO é o que decide qual handler responde.

    O Starlette resolve o handler percorrendo `type(exc).__mro__` e parando na
    primeira classe registrada. A 3.4 registra um handler para a **raiz do BC**
    (`StaffError`) e a 1.1 já registra `NotFoundError` (404) e `DomainError`
    (422): o do BC precisa ganhar do genérico, e entre os genéricos o 404
    precisa ganhar do 422.

    Asserido por **índice**, não por `issubclass` — que passa nas duas ordens e
    deixaria a inversão silenciosa.
    """
    mro = error_class.__mro__
    assert mro.index(StaffError) < mro.index(NotFoundError) < mro.index(DomainError)


@pytest.mark.parametrize("error_class", _NON_NOT_FOUND_ERRORS)
def test_conflito_uso_e_relocalizacao_nao_sao_not_found(error_class: type) -> None:
    """Conflito e ausência são simétricos no nome e opostos no significado.

    Herdar `NotFoundError` por simetria descuidada faria a 3.4 responder 404 a
    um conflito de chave — ou, pior, a um `EmployeeRelocationError`, que só
    existe quando o registro **foi** encontrado.
    """
    assert issubclass(error_class, StaffError)
    assert not issubclass(error_class, NotFoundError)


def test_indisponibilidade_nao_encontrada_e_422_e_nao_404() -> None:
    """`UnavailabilityNotFoundError` fora de `NotFoundError` é decisão, não esquecimento.

    O nome diz "not found" e mesmo assim ele é 422: fala de um **valor dentro
    do agregado** (um período que aquele registro não tem), não de um recurso
    endereçável — o funcionário existe e foi encontrado (concept §4).
    """
    assert issubclass(UnavailabilityNotFoundError, StaffError)
    assert not issubclass(UnavailabilityNotFoundError, NotFoundError)


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
