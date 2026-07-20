"""Erros da camada de aplicação do BC identity.

Todos herdam de `IdentityError` (domínio, Stage 2.1) e, por consequência, de
`DomainError` — **nunca** de `ApplicationError`, que não tem handler HTTP
registrado e viraria 500 (ADR 2.2.0003). O pior caso não-ajustado é 422; a Stage
2.4 refina para 401/403/404 registrando handlers, sem tocar nesta camada.

Os três erros de "não encontrado" herdam também de `NotFoundError`, **nesta
ordem**: a MRO fica `… -> IdentityError -> NotFoundError -> DomainError`, e o
lookup de handler do Starlette (que percorre `type(exc).__mro__`) alcança o
handler 404 antes do 422.

Erros de invariante do domínio (`CrossTenantError`, `PlatformAdminMembershipError`
etc.) **não** são reembrulhados: sobem como estão, com a mesma raiz `IdentityError`.
"""

from restaurant_hub.features.identity.domain.exceptions.errors import IdentityError
from restaurant_hub.shared.domain.exceptions.base import NotFoundError


class EmailAlreadyRegisteredError(IdentityError):
    """E-mail já usado por outro usuário.

    A unicidade é **global**, não escopada por tenant (decisão de kickoff #2):
    o mesmo e-mail não pode existir em dois restaurantes diferentes.
    """

    def __init__(self, email: str) -> None:
        super().__init__(f"e-mail já registrado: {email!r}")


class InvalidCredentialsError(IdentityError):
    """Credencial inválida — e-mail inexistente **ou** senha incorreta.

    A mensagem é deliberadamente idêntica nos dois casos, e não cita o e-mail
    tentado: distinguir os cenários entregaria um oráculo de enumeração de contas
    (concept §5.14).
    """

    def __init__(self) -> None:
        super().__init__("credenciais inválidas")


class InvalidAccessTokenError(IdentityError):
    """Access token ausente, malformado, mal assinado ou expirado (Stage 2.4).

    **Uma exceção só para todas as causas, de propósito.** Distinguir "expirado"
    de "assinatura inválida" de "sujeito inexistente" na resposta entregaria ao
    atacante um mapa do que ele acertou. Vale aqui a mesma regra que fez
    `InvalidCredentialsError` ter mensagem única.

    É também o destino da conversão que o guard HTTP faz do `UserNotFoundError`
    do **ator**: um token cujo sujeito não existe mais é credencial inválida
    (401), não recurso ausente (404) — concept §6.
    """

    def __init__(self) -> None:
        super().__init__("token de acesso inválido")


class InvalidRefreshTokenError(IdentityError):
    """Refresh token desconhecido, expirado ou sem usuário correspondente.

    Mensagem genérica pelo mesmo motivo de `InvalidAccessTokenError`. Note que
    **não** cobre o refresh já revogado: aquele é reuso, tem exceção própria, e
    dispara resposta ativa.
    """

    def __init__(self) -> None:
        super().__init__("token de renovação inválido")


class RefreshTokenReuseError(IdentityError):
    """Refresh token já revogado foi reapresentado — sinal de reuso.

    É o evento que o ADR 2.2.0001 desenhou a sessão para tornar **detectável**:
    `find_by_fingerprint` não filtra justamente para que um token já rotacionado
    volte como sessão revogada, em vez de voltar `None` e ficar indistinguível de
    um token forjado. Quem levanta esta exceção já revogou todas as sessões do
    usuário.

    **A mensagem é idêntica à de `InvalidRefreshTokenError`, e a classe é
    separada mesmo assim.** Para o cliente as duas respostas são o mesmo 401
    genérico — contar ao portador de um token roubado que a detecção disparou só
    o ajuda. Para o teste e para a auditoria, porém, os dois cenários precisam ser
    distinguíveis, e é a classe que os distingue.
    """

    def __init__(self) -> None:
        super().__init__("token de renovação inválido")


class PermissionDeniedError(IdentityError):
    """Eixo RBAC: o papel do ator não concede a permissão exigida."""

    def __init__(self, role: str, permission: str) -> None:
        super().__init__(f"papel {role!r} não concede a permissão {permission!r}")


class TenantScopeRequiredError(IdentityError):
    """O ator pertence a um tenant e não declarou o tenant alvo da ação.

    Exigir a declaração é o que impede que omitir o parâmetro vire caminho de
    escalada — a checagem de tenant não pode ser opcional (ADR 2.2.0002).
    """

    def __init__(self, role: str) -> None:
        super().__init__(f"ação de papel {role!r} exige declarar o tenant alvo")


class TenantNotVisibleError(IdentityError):
    """O ator agiu sobre um tenant que não é o seu, ou com alvo incoerente."""

    def __init__(self, actor_tenant: str | None, target_tenant: str) -> None:
        super().__init__(
            f"isolamento de tenant violado: ator do tenant {actor_tenant!r} "
            f"e alvo no tenant {target_tenant!r}"
        )


class UnitScopeRequiredError(IdentityError):
    """Ator escopado por unidade não declarou a unidade alvo.

    Papéis sem bypass de escopo (`manager`, `hr`, `employee`) não têm autoridade
    tenant-wide: omitir a unidade é negado, não promovido.
    """

    def __init__(self, role: str) -> None:
        super().__init__(f"ação de papel {role!r} exige declarar a unidade alvo")


class UnitNotVisibleError(IdentityError):
    """Eixo de visibilidade: o ator não enxerga a unidade alvo."""

    def __init__(self, user_id: str, unit_id: str) -> None:
        super().__init__(f"usuário {user_id!r} não enxerga a unidade {unit_id!r}")


class RestaurantAlreadyExistsError(IdentityError):
    """Restaurante com o mesmo id já gravado.

    Contraparte de `RestaurantNotFoundError`, e o que a PK da tabela impõe: `add`
    é **inserção, não upsert** (ADR 2.3.0003). Existe para que o fake in-memory e
    o adapter Postgres devolvam a mesma coisa no mesmo cenário — antes desta
    Stage o fake sobrescrevia em silêncio o que o banco rejeita.
    """

    def __init__(self, restaurant_id: str) -> None:
        super().__init__(f"restaurante já existe: {restaurant_id!r}")


class UnitAlreadyExistsError(IdentityError):
    """Unidade com o mesmo id já gravada (ADR 2.3.0003)."""

    def __init__(self, unit_id: str) -> None:
        super().__init__(f"unidade já existe: {unit_id!r}")


class UserAlreadyExistsError(IdentityError):
    """Usuário com o mesmo id já gravado.

    Distinto de `EmailAlreadyRegisteredError` de propósito: são violações
    diferentes (id duplicado vs. e-mail tomado por outra conta), e a Stage 2.4
    precisa mapeá-las para respostas diferentes. Colapsar as duas faria a API
    responder "e-mail já registrado" a uma requisição cujo e-mail está livre.
    """

    def __init__(self, user_id: str) -> None:
        super().__init__(f"usuário já existe: {user_id!r}")


class UnitMembershipAlreadyExistsError(IdentityError):
    """Vínculo usuário↔unidade repetido na mesma escrita.

    A tabela real tem PK composta `(user_id, unit_id)` — vínculo é **relação, não
    multiconjunto** (invariante #15 da 2.2). O use case já deduplica `unit_ids`,
    então este erro sinaliza chamador que passou a lista crua; acumular em
    silêncio, como o fake fazia, esconderia esse defeito até a primeira escrita
    real (ADR 2.3.0003).
    """

    def __init__(self, user_id: str) -> None:
        super().__init__(f"vínculo de unidade repetido para o usuário {user_id!r}")


class SessionAlreadyExistsError(IdentityError):
    """Sessão com o mesmo id já gravada (ADR 2.3.0003)."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"sessão já existe: {session_id!r}")


class SessionFingerprintAlreadyExistsError(IdentityError):
    """Fingerprint de refresh token já associado a outra sessão.

    Separado de `SessionAlreadyExistsError` porque os dois cenários não têm o
    mesmo peso: id repetido é colisão, enquanto **fingerprint repetido é o sinal
    de reuso de refresh token** que o ADR 2.2.0001 desenhou a sessão para tornar
    detectável. Um erro só para os dois entregaria à 2.4 a mesma exceção para uma
    colisão inócua e para um token possivelmente roubado.
    """

    def __init__(self, fingerprint: str) -> None:
        # A mensagem nunca carrega o fingerprint inteiro: é material derivado de
        # segredo, e mensagem de erro acaba em log.
        #
        # O prefixo só é seguro quando sobra fingerprint suficiente para que ele
        # NÃO seja o valor todo. Um `fingerprint[:8]` puro parecia resolver e não
        # resolvia: para qualquer valor de até 8 caracteres a "redação" devolvia o
        # segredo inteiro — e os fingerprints curtos dos próprios testes
        # (`fp::a`, `fp::abc`) caíam exatamente nesse caso.
        prefixo_seguro = 8
        if len(fingerprint) > prefixo_seguro:
            visivel = f"{fingerprint[:prefixo_seguro]!r}…"
        else:
            visivel = "<redigido>"
        super().__init__(
            f"fingerprint de refresh token já registrado: {visivel} ({len(fingerprint)} chars)"
        )


class RestaurantNotFoundError(IdentityError, NotFoundError):
    """Restaurante inexistente."""

    def __init__(self, restaurant_id: str) -> None:
        super().__init__(f"restaurante não encontrado: {restaurant_id!r}")


class UnitNotFoundError(IdentityError, NotFoundError):
    """Unidade inexistente."""

    def __init__(self, unit_id: str) -> None:
        super().__init__(f"unidade não encontrada: {unit_id!r}")


class UserNotFoundError(IdentityError, NotFoundError):
    """Usuário inexistente."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"usuário não encontrado: {user_id!r}")
