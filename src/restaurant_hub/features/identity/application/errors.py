"""Erros da camada de aplicação do BC identity.

Duas raízes, uma por significado (ADR 3.9.0001, que supera o 2.2.0003):

- `IdentityError` (domínio, Stage 2.1) — uma regra que o produto enuncia foi
  violada. Aqui ficam a unicidade **global** do e-mail (decisão de kickoff #2) e as
  cinco recusas de autorização, que são regra de produto (ADR 2.2.0002).
- `IdentityApplicationError` (abaixo, sobre `ApplicationError`) — o caso de uso não
  pôde ser atendido por motivo que não é regra de negócio: a credencial ou o token não
  autentica, o recurso endereçado não existe, um identificador técnico colide no
  armazenamento (ADR 2.3.0003).

Cada classe tem **uma** base. A resposta que cada erro produz para quem chamou é
decidida pelo adapter de entrada, num mapa explícito e testado por totalidade — a
hierarquia não carrega nem ordena nada para isso.

Erros de invariante do domínio (`CrossTenantError`, `PlatformAdminMembershipError`
etc.) **não** são reembrulhados: sobem como estão, com a raiz `IdentityError`.
"""

from restaurant_hub.features.identity.domain.exceptions.errors import IdentityError
from restaurant_hub.shared.application.errors import ApplicationError


class IdentityApplicationError(ApplicationError):
    """Raiz das falhas de caso de uso de identity que não são regra de negócio.

    Par de `IdentityError` (domínio): todo erro deste BC descende de exatamente uma
    das duas (ADR 3.9.0001 §2).
    """


class EmailAlreadyRegisteredError(IdentityError):
    """E-mail já usado por outro usuário.

    A unicidade é **global**, não escopada por tenant (decisão de kickoff #2):
    o mesmo e-mail não pode existir em dois restaurantes diferentes.
    """

    def __init__(self, email: str) -> None:
        super().__init__(f"e-mail já registrado: {email!r}")


class InvalidCredentialsError(IdentityApplicationError):
    """Credencial inválida — e-mail inexistente **ou** senha incorreta.

    A mensagem é deliberadamente idêntica nos dois casos, e não cita o e-mail
    tentado: distinguir os cenários entregaria um oráculo de enumeração de contas
    (concept §5.14).
    """

    def __init__(self) -> None:
        super().__init__("credenciais inválidas")


class InvalidAccessTokenError(IdentityApplicationError):
    """Access token ausente, malformado, mal assinado ou expirado (Stage 2.4).

    **Uma exceção só para todas as causas, de propósito.** Distinguir "expirado"
    de "assinatura inválida" de "sujeito inexistente" na resposta entregaria ao
    atacante um mapa do que ele acertou. Vale aqui a mesma regra que fez
    `InvalidCredentialsError` ter mensagem única.

    É também o destino da conversão que o guard da borda faz do
    `UserNotFoundError` do **ator**: um token cujo sujeito não existe mais é
    credencial inválida, não recurso ausente — concept 2.4 §6.
    """

    def __init__(self) -> None:
        super().__init__("token de acesso inválido")


class InvalidRefreshTokenError(IdentityApplicationError):
    """Refresh token desconhecido, expirado ou sem usuário correspondente.

    Mensagem genérica pelo mesmo motivo de `InvalidAccessTokenError`. Note que
    **não** cobre o refresh já revogado: aquele é reuso, tem exceção própria, e
    dispara resposta ativa.
    """

    def __init__(self) -> None:
        super().__init__("token de renovação inválido")


class RefreshTokenReuseError(IdentityApplicationError):
    """Refresh token já revogado foi reapresentado — sinal de reuso.

    É o evento que o ADR 2.2.0001 desenhou a sessão para tornar **detectável**:
    `find_by_fingerprint` não filtra justamente para que um token já rotacionado
    volte como sessão revogada, em vez de voltar `None` e ficar indistinguível de
    um token forjado. Quem levanta esta exceção já revogou todas as sessões do
    usuário.

    **A mensagem é idêntica à de `InvalidRefreshTokenError`, e a classe é
    separada mesmo assim.** Para o cliente as duas respostas são a mesma recusa
    genérica — contar ao portador de um token roubado que a detecção disparou só
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


class RestaurantAlreadyExistsError(IdentityApplicationError):
    """Restaurante com o mesmo id já gravado.

    Contraparte de `RestaurantNotFoundError`, e o que a PK da tabela impõe: `add`
    é **inserção, não upsert** (ADR 2.3.0003). Existe para que o fake in-memory e
    o adapter Postgres devolvam a mesma coisa no mesmo cenário — antes desta
    Stage o fake sobrescrevia em silêncio o que o banco rejeita.
    """

    def __init__(self, restaurant_id: str) -> None:
        super().__init__(f"restaurante já existe: {restaurant_id!r}")


class UnitAlreadyExistsError(IdentityApplicationError):
    """Unidade com o mesmo id já gravada (ADR 2.3.0003)."""

    def __init__(self, unit_id: str) -> None:
        super().__init__(f"unidade já existe: {unit_id!r}")


class UserAlreadyExistsError(IdentityApplicationError):
    """Usuário com o mesmo id já gravado.

    Distinto de `EmailAlreadyRegisteredError` de propósito: são violações
    diferentes (id duplicado vs. e-mail tomado por outra conta), e a Stage 2.4
    precisa mapeá-las para respostas diferentes. Colapsar as duas faria a API
    responder "e-mail já registrado" a uma requisição cujo e-mail está livre.
    """

    def __init__(self, user_id: str) -> None:
        super().__init__(f"usuário já existe: {user_id!r}")


class UnitMembershipAlreadyExistsError(IdentityApplicationError):
    """Vínculo usuário↔unidade repetido na mesma escrita.

    A tabela real tem PK composta `(user_id, unit_id)` — vínculo é **relação, não
    multiconjunto** (invariante #15 da 2.2). O use case já deduplica `unit_ids`,
    então este erro sinaliza chamador que passou a lista crua; acumular em
    silêncio, como o fake fazia, esconderia esse defeito até a primeira escrita
    real (ADR 2.3.0003).
    """

    def __init__(self, user_id: str) -> None:
        super().__init__(f"vínculo de unidade repetido para o usuário {user_id!r}")


class SessionAlreadyExistsError(IdentityApplicationError):
    """Sessão com o mesmo id já gravada (ADR 2.3.0003)."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"sessão já existe: {session_id!r}")


class SessionFingerprintAlreadyExistsError(IdentityApplicationError):
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
        safe_prefix = 8
        if len(fingerprint) > safe_prefix:
            visible = f"{fingerprint[:safe_prefix]!r}…"
        else:
            visible = "<redigido>"
        super().__init__(
            f"fingerprint de refresh token já registrado: {visible} ({len(fingerprint)} chars)"
        )


class RestaurantNotFoundError(IdentityApplicationError):
    """Restaurante inexistente."""

    def __init__(self, restaurant_id: str) -> None:
        super().__init__(f"restaurante não encontrado: {restaurant_id!r}")


class UnitNotFoundError(IdentityApplicationError):
    """Unidade inexistente.

    Guarda o `unit_id` procurado: `authorize_at_boundary` traduz esta exceção em
    `UnitNotVisibleError` e nomeia a unidade a partir daqui, não do command, cujo
    `unit_id` é opcional no tipo (issue #155).
    """

    def __init__(self, unit_id: str) -> None:
        super().__init__(f"unidade não encontrada: {unit_id!r}")
        self.unit_id = unit_id


class UserNotFoundError(IdentityApplicationError):
    """Usuário inexistente."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"usuário não encontrado: {user_id!r}")


class InvalidSetupTokenError(IdentityApplicationError):
    """Token de definição de senha ausente, desconhecido, expirado ou já usado.

    **Uma exceção só para todas as causas, e a mensagem é constante.** Distinguir
    "expirado" de "já consumido" de "nunca existiu" de "o usuário sumiu" entregaria
    ao atacante um mapa do que ele acertou — e o pior dos quatro é o último: um
    "não encontrado" falante confirmaria que a string apresentada era um token de verdade, cujo
    dono foi apagado. É a mesma regra que fez `InvalidAccessTokenError` ter causa
    única, aplicada a uma rota que é **pública**.

    A mensagem não interpola valor, fingerprint, id de usuário nem instante de
    expiração. Mensagem de erro acaba em log, e o log de uma rota pública de
    recuperação de conta é exatamente onde um token não pode estar.
    """

    def __init__(self) -> None:
        super().__init__("token de definição de senha inválido")


class InvitationNotSentError(IdentityApplicationError):
    """A conta do convite foi gravada, e o e-mail com o link não saiu (issue #170).

    É de aplicação, e não de domínio: nenhuma regra de produto foi violada — o caso
    de uso não pôde ser concluído porque a entrega por um port de saída falhou. A
    conta, o token e (no provisionamento) o restaurante **já estão comitados**
    quando isto sobe (regra 13 da 2.5); a recuperação é o pedido público de
    redefinição de senha, não repetir o convite, que esbarra no e-mail já usado.

    **Substitui a exceção do `EmailSender`, não a embrulha.** A mensagem e a cadeia
    de causas de uma falha de provedor podem ecoar o destinatário ou o corpo — e o
    corpo leva o link, que é credencial. Por isso quem levanta esta exceção registra
    só o tipo da falha original e a levanta **fora** do bloco que a capturou: sem
    `__cause__` nem `__context__`, não há caminho de volta à mensagem original. A
    mensagem desta classe interpola só o id do usuário, que não é segredo.
    """

    def __init__(self, user_id: str) -> None:
        super().__init__(f"convite não enviado ao usuário {user_id!r}")
        self.user_id = user_id
