"""Testes do mapa exceção → status HTTP — CA16 e CA26.

O teste que carrega esta Stage é `test_o_mapa_e_total_sobre_identity_error`. Sem
ele, um erro adicionado numa Stage futura cairia no default 422 em silêncio — que
é precisamente como um 403 vira 422 sem ninguém notar, e como uma regra de acesso
deixa de ser observável pela API sem que nenhum teste fique vermelho.
"""

import json

import pytest

from restaurant_hub.features.identity.adapters.inbound.http import error_handlers as handlers
from restaurant_hub.features.identity.application import errors as application_errors
from restaurant_hub.features.identity.application.errors import IdentityApplicationError
from restaurant_hub.features.identity.domain.exceptions import errors as domain_errors
from restaurant_hub.features.identity.domain.exceptions.errors import IdentityError

pytestmark = pytest.mark.unit

# Piso de contagem: 8 concretas no domínio + 19 na aplicação. É tripwire contra a
# enumeração encolher em silêncio — `__subclasses__` só enxerga o que foi
# importado, então um módulo de erro novo que ninguém importasse aqui faria a
# varredura passar sobre um universo menor do que o real.
_TOTAL_MINIMO_DE_ERROS = 27
_TOTAL_DE_MODULOS_DE_ERRO = 2

# Os dois módulos são importados acima de propósito, e não por acaso: é o import
# que popula `__subclasses__`. Referenciá-los aqui impede que um "unused import"
# seja removido por engano, levando o guarda junto.
_MODULOS_DE_ERRO = (domain_errors, application_errors)


def _subclasses_concretas() -> set[type[Exception]]:
    """Todas as subclasses das duas raízes do BC definidas no código de produção.

    As raízes são `IdentityError` (domínio) e `IdentityApplicationError`
    (aplicação) — ADR 3.9.0001 §2.

    **O filtro por `restaurant_hub.` não é cosmético.** `__subclasses__()` é um
    registro global e vivo: a subclasse-cobaia que este arquivo define para
    testar a resolução por MRO entraria na varredura, sem entrada própria no
    mapa, e reprovaria a totalidade de forma determinística. Quem topasse com
    essa falha provavelmente afrouxaria a exigência de "entrada própria" — que é
    justamente o gate.
    """
    encontradas: set[type[Exception]] = set()

    def _descer(classe: type[Exception]) -> None:
        for sub in classe.__subclasses__():
            if sub.__module__.startswith("restaurant_hub."):
                encontradas.add(sub)
            _descer(sub)

    _descer(IdentityError)
    _descer(IdentityApplicationError)
    return encontradas


def test_a_varredura_de_erros_nao_encolheu() -> None:
    """Guarda do guarda — ver o comentário do piso."""
    assert len(_MODULOS_DE_ERRO) == _TOTAL_DE_MODULOS_DE_ERRO
    assert len(_subclasses_concretas()) >= _TOTAL_MINIMO_DE_ERROS


def test_o_mapa_e_total_sobre_identity_error() -> None:
    """CA16 — toda subclasse concreta tem entrada **própria**, não herdada.

    Herdar a entrada do pai não basta: um erro novo tem de ser classificado
    deliberadamente. É a diferença entre "o sistema respondeu alguma coisa" e
    "alguém decidiu o que o sistema responde".
    """
    sem_entrada = sorted(
        classe.__name__
        for classe in _subclasses_concretas()
        if classe not in handlers.IDENTITY_ERROR_STATUS
    )

    assert sem_entrada == [], f"erros sem entrada própria no mapa de status: {sem_entrada}"


def test_o_mapa_nao_tem_entrada_orfa() -> None:
    """O inverso: entrada para classe que não existe mais é lixo que engana."""
    conhecidas = _subclasses_concretas()

    orfas = sorted(c.__name__ for c in handlers.IDENTITY_ERROR_STATUS if c not in conhecidas)

    assert orfas == []


@pytest.mark.parametrize(
    ("excecao", "status_esperado"),
    [
        (application_errors.InvalidCredentialsError(), 401),
        (application_errors.InvalidAccessTokenError(), 401),
        (application_errors.InvalidRefreshTokenError(), 401),
        (application_errors.RefreshTokenReuseError(), 401),
        (application_errors.SessionFingerprintAlreadyExistsError("fp-longo-o-bastante"), 401),
        # Stage 2.5. Sem esta linha, trocar o status para 404 no mapa mantinha a
        # suíte verde: as duas guardas estruturais só perguntam "existe entrada?"
        # e "existe classe?", nunca leem o valor. E a rota que este erro atende é
        # PÚBLICA — um 404 falante ali confirmaria ao atacante que a string
        # apresentada era um token de verdade (concept §5 regra 16).
        (application_errors.InvalidSetupTokenError(), 401),
        (application_errors.PermissionDeniedError("manager", "manage_tenant"), 403),
        (application_errors.TenantScopeRequiredError("owner"), 403),
        (application_errors.TenantNotVisibleError("a", "b"), 403),
        (application_errors.UnitScopeRequiredError("manager"), 403),
        (application_errors.UnitNotVisibleError("u", "un"), 403),
        (application_errors.RestaurantNotFoundError("r"), 404),
        (application_errors.UnitNotFoundError("u"), 404),
        (application_errors.UserNotFoundError("u"), 404),
        (application_errors.EmailAlreadyRegisteredError("a@b.com"), 409),
        (application_errors.RestaurantAlreadyExistsError("r"), 409),
        (application_errors.UnitAlreadyExistsError("u"), 409),
        (application_errors.UserAlreadyExistsError("u"), 409),
        (application_errors.UnitMembershipAlreadyExistsError("u"), 409),
        (application_errors.SessionAlreadyExistsError("s"), 409),
        (domain_errors.InvalidEmailError("x"), 422),
        (domain_errors.InvalidRoleError("x"), 422),
        (domain_errors.InvalidNameError("unidade"), 422),
        (domain_errors.InvalidIdentifierError("usuário"), 422),
        (domain_errors.MissingTenantError("owner"), 422),
        (domain_errors.PlatformAdminTenantError(), 422),
        (domain_errors.PlatformAdminMembershipError(), 422),
        (domain_errors.CrossTenantError("a", "b"), 422),
    ],
)
def test_status_de_cada_excecao(excecao: IdentityError, status_esperado: int) -> None:
    """O mapa inteiro, exceção a exceção — testado, não presumido (issue #24)."""
    assert handlers.resolve_status(excecao) == status_esperado


def test_resolucao_por_mro_para_subclasse_nao_mapeada() -> None:
    """Subclasse futura herda a classificação do pai em vez de virar 500.

    Isto **não** relaxa a totalidade: o teste acima continua exigindo entrada
    própria de toda classe concreta de produção. A herança é a rede de segurança
    de runtime, para o caso de o gate ser burlado.
    """

    class ErroDerivadoDeTeste(application_errors.PermissionDeniedError):
        """Definida no módulo de teste — excluída da varredura pelo filtro."""

    assert (
        handlers.resolve_status(ErroDerivadoDeTeste("hr", "manage_tenant"))
        == handlers.HTTP_FORBIDDEN
    )


def test_identity_error_cru_cai_no_default() -> None:
    assert handlers.resolve_status(IdentityError("qualquer coisa")) == handlers.HTTP_UNPROCESSABLE


# ---------------------------------------------------------------------------
# CA26 — corpo constante por faixa
# ---------------------------------------------------------------------------


def _corpo(excecao: IdentityError) -> bytes:
    return handlers.build_error_response(excecao).body


def test_corpo_das_401_e_identico_entre_excecoes_diferentes() -> None:
    """CA26 — igualar o status não basta; o corpo tem de ser o mesmo.

    O corpo default seria `str(exc)`, e as mensagens deste BC diferem entre si.
    Um cliente que lesse `detail` distinguiria "credencial inválida" de "token
    expirado" de "reuso detectado" — que é exatamente o mapa do que ele acertou.
    """
    corpos = {
        _corpo(application_errors.InvalidCredentialsError()),
        _corpo(application_errors.InvalidAccessTokenError()),
        _corpo(application_errors.InvalidRefreshTokenError()),
        _corpo(application_errors.RefreshTokenReuseError()),
    }

    assert len(corpos) == 1


def test_corpo_das_403_e_identico_entre_excecoes_diferentes() -> None:
    """CA26 — e aqui está o fechamento do oráculo cross-tenant.

    `TenantNotVisibleError` renderiza "ator do tenant 'A' e alvo no tenant 'B'":
    se o corpo saísse, ela diria a um ator de outro tenant **qual** tenant é dono
    do recurso. Com corpo constante, "não existe" e "existe e não é sua" são
    literalmente a mesma resposta.
    """
    corpos = {
        _corpo(application_errors.PermissionDeniedError("manager", "manage_tenant")),
        _corpo(application_errors.TenantNotVisibleError("tenant-a", "tenant-b")),
        _corpo(application_errors.UnitNotVisibleError("user-1", "unit-9")),
        _corpo(application_errors.UnitScopeRequiredError("manager")),
        _corpo(application_errors.TenantScopeRequiredError("owner")),
    }

    assert len(corpos) == 1


def test_corpo_de_403_nao_vaza_id_nem_tenant() -> None:
    corpo = _corpo(application_errors.TenantNotVisibleError("tenant-a", "tenant-b"))

    assert b"tenant-a" not in corpo
    assert b"tenant-b" not in corpo


def test_401_traz_www_authenticate_e_403_nao() -> None:
    """RFC 6750 §3 — e só na faixa que anuncia autenticação."""
    resposta_401 = handlers.build_error_response(application_errors.InvalidCredentialsError())
    resposta_403 = handlers.build_error_response(
        application_errors.PermissionDeniedError("employee", "manage_users")
    )

    assert resposta_401.headers["WWW-Authenticate"] == "Bearer"
    assert "WWW-Authenticate" not in resposta_403.headers


def test_faixas_404_409_422_preservam_a_mensagem() -> None:
    """Ali a mensagem descreve o que o próprio cliente nomeou — e ajuda a depurar."""
    assert b"rest-9" in _corpo(application_errors.RestaurantNotFoundError("rest-9"))
    assert b"a@b.com" in _corpo(application_errors.EmailAlreadyRegisteredError("a@b.com"))
    assert b"papel-x" in _corpo(domain_errors.InvalidRoleError("papel-x"))


# ---------------------------------------------------------------------------
# Corpo exato por faixa, para toda classe das duas raízes (Stage 3.9, CA8)
# ---------------------------------------------------------------------------

# Os corpos esperados são escritos aqui por extenso, e não lidos do módulo: este
# teste é o oráculo de que a troca de raiz (ADR 3.9.0001) não mudou um byte do que
# o cliente recebe, e um oráculo que importasse a constante concordaria com ela
# mesmo que ela mudasse. Os e2e de faixa assertam só o status.
_MENSAGEM_PLANTADA = "detalhe-plantado"
_CORPO_401_ESPERADO = {"detail": "não autenticado", "type": "unauthorized"}
_CORPO_403_ESPERADO = {"detail": "acesso negado", "type": "forbidden"}


def _instancia_com_mensagem(classe: type[Exception]) -> Exception:
    """Instância da classe com mensagem conhecida, sem passar pelo `__init__` dela.

    Os construtores do BC pedem argumentos diferentes (ids, papéis, e-mails); o que
    este teste observa é só o corpo produzido a partir de `str(exc)`, então a
    mensagem é posta direto pela base `Exception`.
    """
    excecao = classe.__new__(classe)
    Exception.__init__(excecao, _MENSAGEM_PLANTADA)
    return excecao


@pytest.mark.parametrize(
    "classe", sorted(_subclasses_concretas(), key=lambda c: c.__name__), ids=lambda c: c.__name__
)
def test_corpo_exato_por_faixa_para_toda_classe_das_duas_raizes(classe: type[Exception]) -> None:
    """401/403 com corpo constante (e `WWW-Authenticate` só no 401); demais com `str(exc)`."""
    excecao = _instancia_com_mensagem(classe)
    assert isinstance(excecao, IdentityError | IdentityApplicationError)
    resposta = handlers.build_error_response(excecao)
    corpo = json.loads(resposta.body)

    status = handlers.IDENTITY_ERROR_STATUS[classe]
    assert resposta.status_code == status
    if status == 401:  # noqa: PLR2004 — o oráculo é o literal da faixa
        assert corpo == _CORPO_401_ESPERADO
        assert resposta.headers["WWW-Authenticate"] == "Bearer"
    elif status == 403:  # noqa: PLR2004
        assert corpo == _CORPO_403_ESPERADO
        assert "WWW-Authenticate" not in resposta.headers
    else:
        assert corpo == {"detail": _MENSAGEM_PLANTADA, "type": "identity_error"}
        assert "WWW-Authenticate" not in resposta.headers
