"""Fake do `IdentityGateway` — a segunda implementação que dá poder às leis.

Mesmo desenho do `InMemoryAccessGuard`: estado configurável, um registro de
chamadas (`calls`) que os testes de use case usam para asserir **ordem** e
**ausência** de chamada (concept 3.5 CA09, CA11, CA30), e sentinelas próprias
para o que o port declara "sobe cru" (L-IG2) — tipos do fake, e não erros de
identity, porque a lei é sobre **não traduzir**, e um fake que levantasse o erro
do outro BC provaria menos, não mais.

**O ledger é o que torna L-IG1 verificável de fora**: cada provisionamento
devolve um `user_id` **novo** e grava `(email, tenant, unit, delivery, link)`;
a suíte de contrato pergunta ao holder se o link redime **aquele** login e se o
papel é o de funcionário — e o fake responde "employee" por definição, porque a
lei diz que o papel é do port, não do chamador.

**`calls` nunca carrega o `setup_link`** (L-IG3): registra-se a chamada, não o
segredo. Um teste que quisesse o link o lê pelo ledger ou por `sent`.

**A linha `_conforms` no fim do arquivo é o gate da conformidade.**
`make typecheck` é `mypy src/ tests/fakes/`, e nenhum outro sítio que o mypy
checa passa este fake como `IdentityGateway` — sem ela, um método divergente do
port (assinatura ou retorno) passaria no gate e só apareceria, se aparecesse, em
runtime (auditoria da Stage 3.8).

**Ordem das recusas**, espelhando o lado real (fachada + use case): e-mail
inválido primeiro (o VO `Email` é construído na fachada, antes de tudo), depois
e-mail já usado (unicidade global é a primeira checagem do use case), depois
tenant, depois unidade. Os testes de use case não dependem da ordem entre as
duas primeiras; a suíte de contrato depende de cada uma existir.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from restaurant_hub.features.staff.application.errors import (
    InvalidLoginEmailError,
    LoginEmailAlreadyInUseError,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    IdentityGateway,
    LoginDelivery,
    ProvisionedLogin,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
    UserId,
)


class FakeTenantUnknown(Exception):
    """Sentinela de L-IG2 — o que o fake levanta para um tenant que "não existe"."""


class FakeUnitUnknown(Exception):
    """Sentinela de L-IG2 — unidade que "não existe"."""


class FakeUnitOfAnotherTenant(Exception):
    """Sentinela de L-IG2 — unidade que "pertence a outro tenant"."""


class FakeEmailAlreadyUsed(Exception):
    """Sentinela de L-IG2 — o que "identity" levanta para e-mail já registrado.

    Existe para que o fake **traduza preservando a causa** (`raise ... from exc`),
    como o gateway real: sem ela, a exceção de staff sairia sem `__cause__` e a
    lei "a tradução não apaga quem recusou" não poderia ser cobrada dos dois
    lados. Foi o buraco que a auditoria de testes mediu — um `from None` no
    gateway real passava na suíte inteira.
    """


class FakeEmailInvalid(Exception):
    """Sentinela de L-IG2 — o que "identity" levanta para e-mail malformado."""


@dataclass(frozen=True)
class ProvisionedLoginRecord:
    """Uma linha do ledger: o que o fake "criou" para um login."""

    email: str
    tenant_id: TenantId
    unit_id: UnitId
    delivery: LoginDelivery
    setup_link: str = field(repr=False)


@dataclass
class InMemoryIdentityGateway:
    """Gateway configurável: ledger, registro de chamadas e os knobs de L-IG2.

    Attributes:
        logins: o ledger, por `user_id` — L-IG1 de fora.
        calls: registro das chamadas recebidas, **sem** o link (L-IG3).
        sent: os convites "enviados", como `(email, setup_link)`.
        revoked: os logins cujas sessões foram revogadas, na ordem.
        used_emails: e-mails "já usados" — provisionar com um deles levanta
            `LoginEmailAlreadyInUseError`. Todo provisionamento bem-sucedido
            acrescenta o seu e-mail aqui, como identity faria.
        invalid_emails: e-mails que "não são e-mail" — levantam
            `InvalidLoginEmailError`.
        raw_errors_by_tenant: tenant ⇒ exceção **crua** a levantar (L-IG2).
        raw_errors_by_unit: unidade ⇒ exceção **crua** a levantar (L-IG2).
        fail_send_with: se definido, `send_login_invitation` levanta **esta
            instância** (L-IG2, metade do envio).
        mirror: se definido, cada chamada registrada em `calls` é espelhada
            também aqui — tipicamente `store.record` de `InMemoryStaffStore`, com
            um prefixo. É o que permite asserir a **ordem** entre uma chamada ao
            gateway e uma ao repositório num ledger só (ex.: "revogar antes de
            gravar", "gravar antes de enviar"): dois ledgers separados não têm
            posição relativa.
        other_role_logins: logins do ledger cujo papel **não** é o de
            funcionário (gerente/dono vinculado a um registro de escala —
            ADR 3.8.0001). É **este** conjunto que faz `is_employee_login`
            responder `False` para um login conhecido; um id fora de `logins` é
            o caso "desconhecido", que também responde `False` (L-IG5). Semear
            por `seed_login_of_other_role`, que grava nos dois.
        fail_role_query_with: se definido, `is_employee_login` levanta **esta
            instância** (L-IG5, metade da falha).
    """

    logins: dict[UserId, ProvisionedLoginRecord] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    sent: list[tuple[str, str]] = field(default_factory=list)
    revoked: list[UserId] = field(default_factory=list)
    used_emails: set[str] = field(default_factory=set)
    invalid_emails: set[str] = field(default_factory=set)
    raw_errors_by_tenant: dict[TenantId, Exception] = field(default_factory=dict)
    raw_errors_by_unit: dict[UnitId, Exception] = field(default_factory=dict)
    fail_send_with: Exception | None = None
    other_role_logins: set[UserId] = field(default_factory=set)
    fail_role_query_with: Exception | None = None
    mirror: Callable[[str], None] | None = None
    _sequence: int = 0

    def record(self, call: str) -> None:
        """Registra uma chamada recebida — e a espelha, se houver espelho."""
        self.calls.append(call)
        if self.mirror is not None:
            self.mirror(call)

    def provision_employee_login(
        self,
        *,
        email: str,
        tenant_id: TenantId,
        unit_id: UnitId,
        delivery: LoginDelivery,
    ) -> ProvisionedLogin:
        """L-IG1 — login novo por chamada; L-IG2 — traduz duas, o resto sobe cru."""
        self.record(
            f"provision_employee_login({email!r}, {tenant_id!r}, {unit_id!r}, {delivery.value!r})"
        )
        if email in self.invalid_emails:
            raise InvalidLoginEmailError(email) from FakeEmailInvalid(email)
        if email in self.used_emails:
            raise LoginEmailAlreadyInUseError(email) from FakeEmailAlreadyUsed(email)
        if tenant_id in self.raw_errors_by_tenant:
            raise self.raw_errors_by_tenant[tenant_id]
        if unit_id in self.raw_errors_by_unit:
            raise self.raw_errors_by_unit[unit_id]

        self._sequence += 1
        user_id = UserId(f"login-{self._sequence}")
        # Determinístico por login e **distinto** entre logins — é o que o holder
        # de contrato usa para responder "este link redime este login".
        setup_link = f"fake://definir-senha?token=token-de-{user_id}"
        self.logins[user_id] = ProvisionedLoginRecord(
            email=email,
            tenant_id=tenant_id,
            unit_id=unit_id,
            delivery=delivery,
            setup_link=setup_link,
        )
        self.used_emails.add(email)
        return ProvisionedLogin(user_id=user_id, setup_link=setup_link)

    def send_login_invitation(self, *, user_id: UserId, email: str, setup_link: str) -> None:
        """Registra o envio — ou levanta a instância configurada, **crua** (L-IG2).

        O `user_id` entra no registro (issue #175): é o que permite asserir que o
        use case entrega o id do login **recém-provisionado**, e não outro.
        """
        self.record(f"send_login_invitation({user_id!r}, {email!r})")
        if self.fail_send_with is not None:
            raise self.fail_send_with
        self.sent.append((email, setup_link))

    def revoke_login_sessions(self, user_id: UserId) -> None:
        """L-IG4 — idempotente e total: registra, nunca levanta."""
        self.record(f"revoke_login_sessions({user_id!r})")
        self.revoked.append(user_id)

    def is_employee_login(self, user_id: UserId) -> bool:
        """L-IG5 — `True` sse o login está no ledger e não é de outro papel."""
        self.record(f"is_employee_login({user_id!r})")
        if self.fail_role_query_with is not None:
            raise self.fail_role_query_with
        return user_id in self.logins and user_id not in self.other_role_logins

    # ---- ganchos de teste (não fazem parte do port) ----

    def seed_employee_login(self, user_id: UserId, *, tenant_id: TenantId, unit_id: UnitId) -> None:
        """Um login **conhecido** de funcionário, com um id escolhido pelo teste.

        Para o arranjo que fixa o `user_id` do registro antes de montar o use case
        (o `provision_employee_login` numera os ids). Sem ele, o login seria o caso
        "desconhecido" de L-IG5 e desligar não revogaria. Não registra em `calls`:
        é arranjo, não chamada recebida.
        """
        self.logins[user_id] = ProvisionedLoginRecord(
            email=f"{user_id}@funcionario.invalid",
            tenant_id=tenant_id,
            unit_id=unit_id,
            delivery=LoginDelivery.EMAIL,
            setup_link="",
        )

    def seed_login_of_other_role(
        self, user_id: UserId, *, tenant_id: TenantId, unit_id: UnitId
    ) -> None:
        """Um login **conhecido** de papel diferente de funcionário.

        Grava no ledger **e** em `other_role_logins`: só assim é o segundo
        conjunto que decide o `False` de L-IG5, e não a ausência do login —
        senão o caso colapsaria no "desconhecido". Não registra em `calls`: é
        arranjo, não chamada recebida.
        """
        self.logins[user_id] = ProvisionedLoginRecord(
            email=f"{user_id}@outro-papel.invalid",
            tenant_id=tenant_id,
            unit_id=unit_id,
            delivery=LoginDelivery.EMAIL,
            setup_link="",
        )
        self.other_role_logins.add(user_id)


_conforms: IdentityGateway = InMemoryIdentityGateway()
