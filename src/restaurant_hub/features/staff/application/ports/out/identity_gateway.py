"""Port de saída: o que staff precisa de identity, dito no **vocabulário de staff**.

É a segunda travessia entre os dois bounded contexts — a primeira é o
`AccessGuard` (Stage 3.4) — e a primeira consumida por **use case**, que é o
caso para o qual `ports/out/` foi antecipado (ADR 3.4.0001 §4). Quatro operações:
provisionar o login **pendente** de um funcionário, enviar o convite, revogar
as sessões de um login e — desde a Stage 3.8 — perguntar se um login é de
funcionário. Nada aqui nomeia `User`, `Role`, `Email` ou qualquer
tipo de identity: identificadores atravessam a fronteira como strings opacas
(`identifiers.py`), o e-mail chega como `str` cru e é a implementação quem o
valida do outro lado (concept 3.5 §5.7).

**A implementação de produção mora em `features/staff/adapters/out/identity/`
e importa uma única coisa de identity — a fachada** (`identity.application.facade`),
pela **única** aresta admitida em `bc-independence` (ADR 3.5.0001). A segunda
implementação é `tests/fakes/features/staff/in_memory_identity_gateway.py`, e é
ela que dá às leis o seu poder de refutação: uma lei que só a produção cumpre
não é lei, é descrição.

**Não há parâmetro de papel.** O port só sabe provisionar login de
**funcionário**. É a forma estrutural, do lado de staff, de "não se concede o
que não se detém" (2.4 concept §5 regra 4): nenhum chamador consegue pedir
outro papel, porque não existe onde pedir. Quem responde pela autorização é
o **use case consumidor**, antes de chamar este port (Stage 3.7, ADR 3.7.0001):
o de **provisionar** (`create_login_for_employee`) autoriza `manage_staff` **e**
`manage_users` (concept 3.5 §5.3), e a rota R17 autoriza as mesmas duas antes
dele; o de **revogar sessões** (`deactivate_employee`) autoriza `manage_staff`.
A fachada de identity não autoriza (#49).

**As cinco leis** (concept 3.5 §4; L-IG5 do concept 3.8 §4). Texto normativo
deste módulo, pareado com a suíte de contrato
`tests/contract/features/staff/test_identity_gateway_laws.py`, que roda o
**mesmo** corpo contra as duas implementações:

- **L-IG1 — papel e escopo são do port; o resultado é o login recém-criado.**
  O login nasce com o papel de funcionário, dentro de `tenant_id`, membro de
  **exatamente** `unit_id`; nenhum argumento permite pedir outro papel ou outra
  unidade. O `user_id` devolvido identifica **esse** login — novo, nunca um
  pré-existente — e o `setup_link` devolvido o redime.
- **L-IG2 — duas exceções são traduzidas; o resto sobe cru, inclusive a falha
  do envio.** E-mail já usado ⇒ `LoginEmailAlreadyInUseError`; e-mail malformado
  ⇒ `InvalidLoginEmailError` (as duas de staff). **Qualquer outra falha** —
  tenant desconhecido, unidade desconhecida, cross-tenant, falha do envio em
  `send_login_invitation` — sobe **como a implementação a levantou** (mesma
  instância), pela mesma razão de L-AG1/L-AG2: traduzi-la criaria uma segunda
  faixa de erro para uma condição que já tem handler; engoli-la faria o gateway
  responder sucesso sem entrega — o modo de falha que a regra 13 da 2.5 existe
  para impedir.
- **L-IG3 — `setup_link` é segredo de uso único.** `repr=False`; staff **nunca
  o persiste** (em nenhuma tabela de staff), nunca o loga, nunca o põe em
  mensagem de exceção. Ele existe entre `provision_employee_login` e **um** de
  dois destinos: `send_login_invitation` ou o corpo da resposta 201 no canal
  `link`. É invariante do **consumidor** mais do que do port — e por isso os
  seus critérios são sobre o use case e a borda (CA05, CA14).
- **L-IG4 — `revoke_login_sessions` é idempotente e total.** Login sem sessão,
  ou id **desconhecido**, não é erro. Chamado duas vezes, o efeito é o mesmo.
- **L-IG5 — `is_employee_login` responde se o login é de funcionário; falha sobe
  crua.** `True` se e somente se identity conhece o login **e** o papel dele é o
  de funcionário — o mesmo que L-IG1 fixa para o login provisionado. Login
  desconhecido ⇒ `False`, não erro: não tem sessão a revogar. Qualquer outra
  falha sobe **como a implementação a levantou** (mesma instância): responder
  `False` numa falha seria *fail-open* — o desligamento gravaria e a sessão
  ficaria viva (ADR 3.8.0001 §3). O port responde booleano, nunca o papel: staff
  não nomeia o vocabulário de papéis de identity.

**Por que `delivery` é parâmetro de `provision_employee_login`, e não só do use
case:** o canal decide o **prazo** do segredo (concept D9 — o link entregue em
mãos vive mais do que o convite por e-mail), e o prazo é política de identity.
O port carrega o canal para que a implementação saiba qual aplicar; ele não
entrega nada — a entrega é `send_login_invitation`, chamada pelo use case
**depois** de gravar o vínculo (§5.4).
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
    UserId,
)


class LoginDelivery(StrEnum):
    """Por onde o link de primeiro acesso chega à pessoa (concept 3.5 §4, D2).

    `EMAIL`: identity envia o link para o e-mail informado; a resposta ao
    gerente **não** o carrega. `LINK`: o link volta ao gerente autorizado, uma
    vez, na resposta — para ser entregue em mãos (papel, QR, mensagem); nada é
    enviado. Os dois criam a **mesma** conta pendente; muda o carteiro e o
    prazo do segredo.
    """

    EMAIL = "email"
    LINK = "link"


@dataclass(frozen=True)
class ProvisionedLogin:
    """O que volta de `provision_employee_login`.

    Attributes:
        user_id: o id do login **recém-criado** em identity (L-IG1), tipado por
            staff.
        setup_link: o link de primeiro acesso — segredo de uso único (L-IG3).
            `repr=False` porque este DTO atravessa o use case e fica nos locals
            do frame que levanta a exceção do envio; um `repr` o entregaria a
            qualquer log com `--showlocals`.
    """

    user_id: UserId
    setup_link: str = field(repr=False)


class IdentityGateway(Protocol):
    """Provisiona logins pendentes, envia convites e revoga sessões — em identity.

    E, desde a Stage 3.8, diz se um login é de funcionário (L-IG5).
    """

    def provision_employee_login(
        self,
        *,
        email: str,
        tenant_id: TenantId,
        unit_id: UnitId,
        delivery: LoginDelivery,
    ) -> ProvisionedLogin:
        """Cria em identity o login **pendente** de um funcionário (L-IG1).

        Args:
            email: o e-mail de login, **cru** — a validação é de identity
                (concept §5.7); malformado ⇒ `InvalidLoginEmailError` (L-IG2).
            tenant_id: o restaurante do registro; o login nasce dentro dele.
            unit_id: a unidade do registro; o login nasce membro **só** dela.
            delivery: o canal pelo qual o link será entregue — decide o prazo
                do segredo, não a entrega (ver docstring do módulo).

        Returns:
            O login recém-criado e o link que o redime.

        Raises:
            LoginEmailAlreadyInUseError: o e-mail já é login de alguém, em
                qualquer tenant (L-IG2).
            InvalidLoginEmailError: o e-mail não é um e-mail (L-IG2).
            Exception: qualquer outra falha sobe **crua** — L-IG2.
        """
        ...

    def send_login_invitation(self, *, email: str, setup_link: str) -> None:
        """Envia o convite com o link para o e-mail (canal `EMAIL`).

        Chamada pelo use case **depois** de gravar `user_id` (§5.4): se falhar, a
        conta existe e está vinculada, e a recuperação é o reset público. A
        falha do envio sobe **crua** (L-IG2) — nunca é engolida.
        """
        ...

    def revoke_login_sessions(self, user_id: UserId) -> None:
        """Revoga todas as sessões do login (desligamento, R13 — ADR 3.5.0003).

        **L-IG4** — idempotente e total: sem sessão, ou id desconhecido, não é
        erro. A conta permanece; o que cai é o refresh (o access em curso vive
        até expirar — kickoff #13). **Quando** chamar é decisão do desligamento
        (ADR 3.8.0001 §1), não deste port.
        """
        ...

    def is_employee_login(self, user_id: UserId) -> bool:
        """Diz se o login é de funcionário (L-IG5 — ADR 3.8.0001 §3).

        É uma das condições com que o ADR 3.8.0001 §1 decide se desligar um
        registro corta as sessões do login: login de gerente ou dono vinculado a
        um registro de escala tira a autoridade do papel, e revogar não
        protegeria nada.

        Returns:
            `True` se e somente se identity conhece o login e o papel é o de
            funcionário; `False` para qualquer outro papel **e** para login
            desconhecido.

        Raises:
            Exception: qualquer falha de identity sobe **crua** — L-IG5.
        """
        ...
