"""Commands — a entrada de cada use case do BC identity.

São DTOs `frozen`: o use case recebe dado, não entidade. Value objects imutáveis
do domínio (`Email`, `Role`, `Permission`) trafegam aqui por licença explícita do
LAYOUT §7 — são valores puros, indistinguíveis de primitivos para o consumidor.
Entidades, não.

A conversão de texto cru para VO (`Role.from_string`, `Email(...)`) é do adapter
que recebe a requisição (Stage 2.4): quando ela falha, o erro já é de domínio e
vira 4xx, em vez de estourar dentro do use case.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role


@dataclass(frozen=True)
class CreateRestaurantCommand:
    """Criação de um restaurante — que é, ele próprio, o tenant."""

    name: str


@dataclass(frozen=True)
class CreateUnitCommand:
    """Criação de uma unidade sob um restaurante existente."""

    restaurant_id: RestaurantId
    name: str


@dataclass(frozen=True)
class CreateUserCommand:
    """Criação de uma conta de acesso.

    Attributes:
        email: e-mail de login; a unicidade é global, não por tenant.
        plain_password: senha em claro — só atravessa o `PasswordHasher`, nunca
            é persistida nem devolvida.
        role: papel fixo de acesso.
        tenant_id: restaurante do usuário; `None` apenas para `platform_admin`.
        unit_ids: unidades a que o usuário fica vinculado (visibilidade).
            Duplicatas são deduplicadas pelo use case.
    """

    email: Email
    # `repr=False` pelo mesmo motivo dos commands de sessão e de
    # `UserCredentials.password_hash`: o `SecretStr` do schema morre no boundary,
    # em `get_secret_value()`. Deste ponto em diante é a senha em claro que
    # atravessa o use case, e ela fica nos locals do frame que levanta
    # `EmailAlreadyRegisteredError` — justamente o frame que alguém inspeciona.
    # Senha é pior que refresh token: o humano a reusa em outros sistemas.
    plain_password: str = field(repr=False)
    role: Role
    tenant_id: RestaurantId | None
    unit_ids: Sequence[UnitId] = ()


@dataclass(frozen=True)
class AuthenticateUserCommand:
    """Tentativa de login por e-mail e senha."""

    email: Email
    # `repr=False` — ver `CreateUserCommand`. Aqui o frame em risco é o que
    # levanta `InvalidCredentialsError`, que é o mais inspecionado do sistema.
    plain_password: str = field(repr=False)


@dataclass(frozen=True)
class RefreshSessionCommand:
    """Pedido de rotação: troca um refresh token por um par novo.

    Carrega o **valor** do token, não o fingerprint: derivá-lo é papel do
    `TokenIssuer`, e exigir que o chamador o derivasse espalharia criptografia
    para fora do port.
    """

    # `repr=False` pelo mesmo motivo que `UserCredentials.password_hash` (2.3):
    # o repr default de uma dataclass imprime o campo inteiro em qualquer
    # traceback com `--showlocals`, captura de locals do Sentry ou log de debug.
    # Aqui pesa mais que lá — um refresh token é credencial bearer VIVA, não um
    # hash. O `SecretStr` do schema morre no boundary; este command atravessa o
    # use case e está nos locals do frame que levanta `RefreshTokenReuseError`,
    # que é justamente o frame que alguém vai querer inspecionar.
    refresh_token: str = field(repr=False)


@dataclass(frozen=True)
class RevokeSessionCommand:
    """Logout: revoga a sessão do refresh token apresentado.

    A autoridade da operação é a **posse** do token — não exige access token.
    """

    refresh_token: str = field(repr=False)


@dataclass(frozen=True)
class AuthorizeActionCommand:
    """Pedido de autorização de uma ação.

    `tenant_id` e `unit_id` descrevem o **alvo** da ação, não o ator. Ambos são
    opcionais no tipo, mas não na regra: o use case exige `tenant_id` de quem
    pertence a um tenant, e `unit_id` de quem é escopado por unidade — omitir não
    é caminho de escalada (concept §5.6).
    """

    actor_id: UserId
    permission: Permission
    tenant_id: RestaurantId | None = None
    unit_id: UnitId | None = None


@dataclass(frozen=True)
class GetAccountRoleCommand:
    """Consulta do papel de uma conta (Stage 3.8, ADR 3.8.0001 §3).

    Consulta com nome de command pelo mesmo motivo de `AuthorizeActionCommand`:
    a entrada de todo use case de identity é um command. Quem pergunta é a
    fachada, a serviço do desligamento em staff, que precisa saber se o login
    vinculado é de funcionário antes de revogar as sessões dele.
    """

    user_id: UserId


@dataclass(frozen=True)
class InviteUserCommand:
    """Convite de uma pessoa que ainda não tem conta.

    É o irmão de `CreateUserCommand` sem o campo mais perigoso: **não há senha**.
    Quem convida não escolhe, não conhece e não transporta a credencial de quem é
    convidado — o convidado a define pelo link que recebe por e-mail.

    Attributes:
        email: e-mail de login e destino do convite; unicidade global.
        role: papel fixo de acesso do convidado.
        tenant_id: restaurante do convidado; vem do **ator**, nunca do corpo da
            requisição (concept §5 regra 12).
        unit_ids: unidades a que o convidado fica vinculado.
    """

    email: Email
    role: Role
    tenant_id: RestaurantId | None
    unit_ids: Sequence[UnitId] = ()


@dataclass(frozen=True)
class SetPasswordWithTokenCommand:
    """Redenção de um token de setup: define a senha da conta.

    **Não carrega `user_id`, e a ausência é a defesa** (concept §5 regra 10). O
    usuário alvo sai de `PasswordSetupToken.user_id`, isto é, do registro que o
    servidor gravou ao emitir o token. Se o campo existisse, alguém acabaria por
    lê-lo — e quem tivesse um token legítimo da própria conta definiria a senha de
    qualquer outra. É a mesma disciplina do `CreateUserRequest` sem `tenant_id`.
    """

    # `repr=False` nos dois: um é credencial bearer viva, o outro é senha em
    # claro. Ambos ficam nos locals do frame que levanta `InvalidSetupTokenError`,
    # que é justamente o frame que alguém inspeciona.
    token: str = field(repr=False)
    plain_password: str = field(repr=False)


@dataclass(frozen=True)
class ProvisionAccountCommand:
    """Provisionamento de uma conta pendente, sem envio (Stage 3.5).

    É `InviteUserCommand` mais a decisão que o convite não precisava tomar: por
    onde o link vai. Quem chama é a fachada de identity a serviço do gateway de
    staff, e o e-mail/`role` já chegam como VO — a conversão de primitivo é da
    fachada, como a do adapter HTTP é dos outros commands.

    Attributes:
        email: e-mail de login da conta; unicidade global.
        role: papel fixo de acesso.
        tenant_id: restaurante da conta; `None` apenas para `platform_admin`.
        unit_ids: unidades a que a conta fica vinculada.
        handed_over: `True` quando o link vai ser entregue em mãos (canal
            `link`) — o token ganha o prazo de `handover_ttl`, mais longo que o
            do e-mail. Sem default: quem provisiona decide o canal.
    """

    email: Email
    role: Role
    tenant_id: RestaurantId | None
    unit_ids: Sequence[UnitId]
    handed_over: bool


@dataclass(frozen=True)
class SendInvitationCommand:
    """Envio do convite para um link já emitido (Stage 3.5).

    Attributes:
        email: destinatário — o mesmo e-mail que é login da conta.
        setup_link: o link completo, com o valor do token. `repr=False` pelo
            mesmo motivo de `RefreshSessionCommand.refresh_token`: é credencial
            bearer viva nos locals do frame que levanta a falha do sender.
    """

    email: Email
    setup_link: str = field(repr=False)


@dataclass(frozen=True)
class RevokeAllSessionsCommand:
    """Revogação de **todas** as sessões de um usuário (Stage 3.5, ADR 3.5.0003).

    Diferente de `RevokeSessionCommand`, a autoridade não é a posse de um token:
    é a identidade do alvo, e quem a exerce é o consumidor (o desligamento em
    staff), já autorizado antes de chegar aqui.
    """

    user_id: UserId


@dataclass(frozen=True)
class RequestPasswordResetCommand:
    """Pedido público de redefinição de senha.

    Carrega só o e-mail: a rota é pública e não autentica ninguém. O que o use
    case faz com um e-mail inexistente é **nada** — e devolver o mesmo que
    devolveria para um e-mail existente é o que impede a enumeração de contas
    (concept §5 regra 7).
    """

    email: Email
