"""Testes da hierarquia de erros da camada de aplicação (concept 2.2 CA13; Stage 3.9).

Cada erro desta camada tem **uma** raiz, escolhida pelo significado (ADR 3.9.0001,
que supera o 2.2.0003): `IdentityError` (domínio) quando nomeia regra do produto,
`IdentityApplicationError` quando o caso de uso não pôde ser atendido por motivo que
não é regra. A partição é travada aqui por **igualdade de conjuntos**: uma classe
nova que não entrar numa das duas listas reprova, e uma que mudar de lado também.
"""

import inspect

import pytest

from restaurant_hub.features.identity.application import errors
from restaurant_hub.features.identity.application.errors import IdentityApplicationError
from restaurant_hub.features.identity.domain.exceptions.errors import IdentityError
from restaurant_hub.shared.application.errors import ApplicationError
from restaurant_hub.shared.domain.exceptions.base import DomainError

pytestmark = pytest.mark.unit

# Regras que o produto enuncia (concept 3.9 §4): unicidade global do e-mail
# (kickoff #2) e as cinco recusas de autorização (ADR 2.2.0002).
_DE_DOMINIO = frozenset(
    {
        "EmailAlreadyRegisteredError",
        "PermissionDeniedError",
        "TenantScopeRequiredError",
        "TenantNotVisibleError",
        "UnitScopeRequiredError",
        "UnitNotVisibleError",
    }
)

# Falhas que não são regra: autenticação, lookup, colisão de identificador técnico.
_DE_APLICACAO = frozenset(
    {
        "InvalidCredentialsError",
        "InvalidAccessTokenError",
        "InvalidRefreshTokenError",
        "RefreshTokenReuseError",
        "InvalidSetupTokenError",
        "RestaurantNotFoundError",
        "UnitNotFoundError",
        "UserNotFoundError",
        "RestaurantAlreadyExistsError",
        "UnitAlreadyExistsError",
        "UserAlreadyExistsError",
        "UnitMembershipAlreadyExistsError",
        "SessionAlreadyExistsError",
        "SessionFingerprintAlreadyExistsError",
        # Issue #170 — a entrega por um port de saída falhou depois do commit. Não
        # é regra de produto: é o caso de uso que não pôde ser concluído.
        "InvitationNotSentError",
    }
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
        # A raiz de aplicação (Stage 3.9, ADR 3.9.0001) não é um erro: é o tipo
        # sobre o qual o handler é registrado, e tem testes próprios.
        if obj.__module__ == errors.__name__ and obj is not errors.IdentityApplicationError
    ]


def test_modulo_declara_as_vinte_e_uma_excecoes_esperadas() -> None:
    """Guarda a lista: classe nova ou removida força revisão consciente do teste."""
    nomes = {cls.__name__ for cls in _application_error_classes()}
    assert nomes == {
        "EmailAlreadyRegisteredError",
        "InvalidCredentialsError",
        "PermissionDeniedError",
        "TenantScopeRequiredError",
        "TenantNotVisibleError",
        "UnitScopeRequiredError",
        "UnitNotVisibleError",
        "RestaurantNotFoundError",
        "UnitNotFoundError",
        "UserNotFoundError",
        # Stage 2.3 — "chave já gravada" precisa ser o mesmo resultado no fake e
        # no Postgres, porque `add` é inserção, não upsert (ADR 2.3.0003).
        "RestaurantAlreadyExistsError",
        "UnitAlreadyExistsError",
        "UserAlreadyExistsError",
        "UnitMembershipAlreadyExistsError",
        "SessionAlreadyExistsError",
        "SessionFingerprintAlreadyExistsError",
        # Stage 2.4 — falhas de credencial. As três caem em 401 com corpo
        # genérico: distinguir a causa para o cliente seria oráculo.
        # `RefreshTokenReuseError` é classe separada de `InvalidRefreshTokenError`
        # apesar da mensagem idêntica, porque o teste e a auditoria precisam
        # distinguir "token desconhecido" de "reuso detectado" — o cliente, não.
        "InvalidAccessTokenError",
        "InvalidRefreshTokenError",
        "RefreshTokenReuseError",
        # Stage 2.5 — token de definição de senha. Causa única e mensagem
        # constante pelo mesmo motivo dos três acima, com um agravante: a rota
        # que o levanta é **pública**, então a mensagem é a única superfície de
        # informação que o atacante tem.
        "InvalidSetupTokenError",
        # Issue #170 — o e-mail do convite não saiu, com a conta já gravada. Classe
        # própria para que a falha do provedor seja SUBSTITUÍDA, e não embrulhada:
        # a mensagem dela pode ecoar o destinatário e o link.
        "InvitationNotSentError",
    }


def test_a_particao_dominio_aplicacao_e_exata() -> None:
    """Concept 3.9 CA3 — as duas listas cobrem o módulo, sem sobra nem interseção."""
    nomes = {cls.__name__ for cls in _application_error_classes()}

    assert not _DE_DOMINIO & _DE_APLICACAO
    assert nomes == _DE_DOMINIO | _DE_APLICACAO


@pytest.mark.parametrize("error_class", _application_error_classes(), ids=lambda c: c.__name__)
def test_cada_erro_esta_sob_a_raiz_da_sua_lista_e_so_nela(error_class: type) -> None:
    """Uma raiz só: quem está numa lista não descende da raiz da outra."""
    if error_class.__name__ in _DE_DOMINIO:
        assert issubclass(error_class, IdentityError)
        assert not issubclass(error_class, ApplicationError)
    else:
        assert issubclass(error_class, IdentityApplicationError)
        assert not issubclass(error_class, DomainError)
    assert len(error_class.__bases__) == 1


def test_a_raiz_de_aplicacao_e_filha_direta_de_application_error() -> None:
    assert IdentityApplicationError.__bases__ == (ApplicationError,)


@pytest.mark.parametrize(
    "fingerprint",
    [
        "0123456789abcdef0123456789abcdef",  # tamanho realista
        "fp::a",  # curto — o usado nos próprios testes de sessão
        "12345678",  # exatamente no limite do prefixo
        "",  # degenerado
    ],
)
def test_erro_de_fingerprint_nunca_expoe_o_fingerprint_inteiro(fingerprint: str) -> None:
    """Fingerprint é material derivado de segredo, e mensagem de erro vira log.

    Parametrizado de propósito: a primeira versão truncava com `fingerprint[:8]`
    e passava neste teste com um valor de 32 caracteres, enquanto vazava o
    segredo inteiro para qualquer valor de até 8 — inclusive os fingerprints
    curtos que a suíte de sessão usa. Um caso só teria dado falso verde.
    """
    mensagem = str(errors.SessionFingerprintAlreadyExistsError(fingerprint))
    if fingerprint:
        assert fingerprint not in mensagem


def test_erro_de_fingerprint_mostra_prefixo_quando_ha_o_que_esconder() -> None:
    """Redigir tudo sempre seria seguro e inútil para investigar reuso de token."""
    mensagem = str(errors.SessionFingerprintAlreadyExistsError("0123456789abcdef"))
    assert "01234567" in mensagem
    assert "16 chars" in mensagem


def test_erros_de_chave_duplicada_citam_a_chave() -> None:
    """Mensagem sem a chave violada é inútil para diagnóstico."""
    assert "rest-1" in str(errors.RestaurantAlreadyExistsError("rest-1"))
    assert "unit-1" in str(errors.UnitAlreadyExistsError("unit-1"))
    assert "user-1" in str(errors.UserAlreadyExistsError("user-1"))
    assert "sess-1" in str(errors.SessionAlreadyExistsError("sess-1"))


@pytest.mark.parametrize("error_class", _application_error_classes(), ids=lambda c: c.__name__)
def test_todo_erro_da_camada_e_levantavel(error_class: type) -> None:
    """`BaseException` primeiro: uma classe sem base de exceção não é levantável.

    `raise` dela daria `TypeError`, e nenhum handler do BC a alcançaria.
    """
    assert issubclass(error_class, BaseException)


def test_mensagens_identificam_o_recurso_ou_a_regra_violada() -> None:
    """Cada erro instanciado produz mensagem útil (executa o `__init__`)."""
    assert "rest-1" in str(errors.RestaurantNotFoundError("rest-1"))
    assert "unit-1" in str(errors.UnitNotFoundError("unit-1"))
    assert "user-1" in str(errors.UserNotFoundError("user-1"))
    assert "dono@x.com" in str(errors.EmailAlreadyRegisteredError("dono@x.com"))

    permission_denied = str(errors.PermissionDeniedError("employee", "manage_users"))
    assert "employee" in permission_denied
    assert "manage_users" in permission_denied

    assert "manager" in str(errors.TenantScopeRequiredError("manager"))
    assert "manager" in str(errors.UnitScopeRequiredError("manager"))

    tenant_not_visible = str(errors.TenantNotVisibleError("rest-a", "rest-b"))
    assert "rest-a" in tenant_not_visible
    assert "rest-b" in tenant_not_visible

    unit_not_visible = str(errors.UnitNotVisibleError("user-1", "unit-9"))
    assert "user-1" in unit_not_visible
    assert "unit-9" in unit_not_visible


def test_convite_nao_enviado_cita_o_usuario_e_guarda_o_id() -> None:
    """Issue #170 — o id do usuário é o que a mensagem leva, e nada do envio."""
    erro = errors.InvitationNotSentError("user-7")

    assert str(erro) == "convite não enviado ao usuário 'user-7'"
    assert erro.user_id == "user-7"


def test_credencial_invalida_nao_revela_qual_lado_falhou() -> None:
    """E-mail inexistente e senha errada precisam ser indistinguíveis.

    A mensagem não pode citar e-mail, senha nem "usuário": qualquer uma dessas
    pistas transforma a resposta num oráculo de enumeração de contas
    (concept §5.14).
    """
    mensagem = str(errors.InvalidCredentialsError()).lower()
    assert mensagem == "credenciais inválidas"
    for pista in ("e-mail", "email", "senha", "usuário", "password"):
        assert pista not in mensagem
