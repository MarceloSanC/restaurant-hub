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
            raise InvalidLoginEmailError(email)
        if email in self.used_emails:
            raise LoginEmailAlreadyInUseError(email)
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

    def send_login_invitation(self, *, email: str, setup_link: str) -> None:
        """Registra o envio — ou levanta a instância configurada, **crua** (L-IG2)."""
        self.record(f"send_login_invitation({email!r})")
        if self.fail_send_with is not None:
            raise self.fail_send_with
        self.sent.append((email, setup_link))

    def revoke_login_sessions(self, user_id: UserId) -> None:
        """L-IG4 — idempotente e total: registra, nunca levanta."""
        self.record(f"revoke_login_sessions({user_id!r})")
        self.revoked.append(user_id)
