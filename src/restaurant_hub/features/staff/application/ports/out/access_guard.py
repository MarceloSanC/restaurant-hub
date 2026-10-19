"""Port de saída: autorização de acesso, dita no **vocabulário de staff**.

**O port nomeia o que staff precisa, nunca como identity decide.** Nenhum módulo
sob `features/staff/` importa `features/identity/`: o contrato `bc-independence`
do `.importlinter` é de **independência** — proíbe as duas direções — e vale
**sem nenhum `ignore_imports`**. Quem traduz este vocabulário para o de identity
é o `composition_root`, o único módulo que já importa os dois bounded contexts
por desenho (ADR 3.4.0001 §3).

**Identificadores atravessam a fronteira entre BCs como strings opacas** — regra
literal do `identifiers.py` deste BC. Por isso as **entradas** de `authorize` são
`str` nua, e é só a **saída** (`AuthorizedScope`) que carrega os `NewType` de
staff: o que entra veio de fora e não é nosso; o que sai é endereço deste BC, e
os use cases o consomem tipado.

**O nome da permissão é `str`** porque o vocabulário fechado mora do outro lado
da fronteira. Os dois valores que o Step 3 usa são `"manage_staff"` e
`"manage_job_functions"` — citados aqui como **valores**, jamais importados como
enum. O preço está declarado no ADR 3.4.0001: um erro de digitação não é pego
pelo type-checker; é pego pelos testes por papel e por rota da Stage 3.6.

**As quatro leis** (ADR 3.4.0001 §2, concept §4). Um `Protocol` sozinho não
carrega as propriedades de segurança de que este desenho depende: uma segunda
implementação que satisfaça **só os tipos** as destrói sem falhar nenhum type
check. Por isso as leis são texto normativo deste módulo, e há uma segunda
implementação (`tests/fakes/features/staff/in_memory_access_guard.py`) que as
obedece — lei que só a implementação de produção cumpre não é lei, é descrição.

- **L-AG1 — a exceção de autenticação sai crua.** `authenticate` levanta quando
  não há credencial válida, e o implementador **não a traduz**. É o que fará a
  faixa 401 da Stage 3.6 ser byte-idêntica à de identity: traduzir aqui criaria
  uma segunda faixa de erro para a mesma condição.
- **L-AG2 — a exceção de autorização sai crua.** `authorize` levanta quando o
  ator não pode agir sobre o alvo, e a exceção **sobe sem embrulho**, pela mesma
  razão (403 de corpo constante). Em particular, a conversão
  `UnitNotFoundError → UnitNotVisibleError` que fecha o oráculo de enumeração
  cross-tenant acontece **do lado de identity**; embrulhá-la aqui a apagaria.
- **L-AG3 — `tenant_id` nunca sai vazio.** `authorize` **jamais** devolve um
  `AuthorizedScope` cujo `tenant_id` seja vazio ou ausente. Ator sem tenant é
  **negado**, não coagido para `""`: `TenantId` é `NewType` sem validação de
  runtime, então `TenantId(actor_tenant_id or "")` compilaria, passaria mypy
  strict e produziria consultas de tenant vazio — o balde de falso isolamento
  que `InvalidIdentifierError` nomeia.
- **L-AG4 — uma autorização por alvo.** `authorize` é chamado **uma vez por
  alvo**; autorizar um alvo não autoriza outro. Reusar um `AuthorizedScope` já
  obtido para alcançar uma segunda unidade é escalada de escopo, não economia de
  chamada.

**Onde este port mora, e por quê** (ADR 3.4.0001 §4). Ele fica em
`application/ports/out/`, e **não** dentro do adapter HTTP. O único consumidor
previsto é o router da Stage 3.6, o que argumentaria por `adapters/inbound/http/`. A
colocação **antecipa a Stage 3.5**, cujo `IdentityGateway` é consumido por **use
case** e cuja pasta o roadmap já nomeia. A justificativa é o critério de
escalabilidade progressiva do projeto, **não** LAYOUT §5 — que descreve port de
saída como consumido por use case e, portanto, **ainda não é literalmente
verdade aqui**. Fica dito em vez de glosado: esta Stage não afirma conformidade
que não tem.
"""

from dataclasses import dataclass
from typing import Final, Protocol

from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
)

# Credencial **já verificada**, opaca para staff. É `object` de propósito: staff
# não interpreta o ator — não lê papel, não lê vínculo, não decide nada a partir
# dele. Tipá-lo exigiria conhecer a forma que identity dá ao ator autenticado, e
# conhecê-la é o começo de reimplementar a decisão de acesso aqui.
Actor = object

# As permissões que staff cita, como **valores** (ADR 3.4.0001). Citadas, jamais
# importadas: o vocabulário fechado mora do outro lado da fronteira, e o contrato
# `bc-independence` proíbe as duas direções. O preço está declarado — um erro de
# digitação aqui não é pego pelo type-checker, e sim pelos testes por papel e por
# rota. Moram neste módulo, e não na borda, desde a Stage 3.7: os **use cases**
# autorizam com elas (ADR 3.7.0001 §5), e application não importa adapter.
PERMISSION_MANAGE_STAFF: Final = "manage_staff"
PERMISSION_MANAGE_JOB_FUNCTIONS: Final = "manage_job_functions"
# Stage 3.5 — a terceira permissão citada por staff, e a primeira que **não é de
# staff**: criar o login de um funcionário cria uma conta em identity, e a
# permissão que governa contas é `manage_users` (concept 3.5 §5.3). R17 a exige
# **junto** com `manage_staff`, as duas sobre a unidade do alvo.
PERMISSION_MANAGE_USERS: Final = "manage_users"


@dataclass(frozen=True)
class AuthorizedScope:
    """O escopo que a autorização **concedeu** — a resposta, não o pedido.

    Duplica dois campos do `AuthorizedActor` de identity, e a duplicação é
    intencional: DTO não se compartilha entre bounded contexts (ADR 3.4.0001,
    §Trade-offs). O que atravessa a fronteira é o valor, não o tipo.

    Attributes:
        tenant_id: o restaurante dentro do qual a ação foi autorizada. **Nunca
            vazio nem ausente** — é a L-AG3, e é o campo cuja coerção silenciosa
            para `""` este port existe para impedir. Quando a chamada **omitiu**
            `tenant_id`, este é o tenant do **próprio ator autenticado**, e não
            um alvo mais largo: ver o parâmetro `tenant_id` de
            `AccessGuard.authorize` e o ADR 0.0.0005.
        unit_id: a unidade alvo quando a ação nomeia uma; `None` quando não
            nomeia. **`None` não significa "ação tenant-wide"** — e a
            afirmação contrária esteve escrita aqui até ser medida contra o
            guard real. Há **dois** caminhos que chegam a `None`, e o escopo não
            distingue entre eles:

            - **por permissão** — `"manage_job_functions"` pertence ao conjunto
              tenant-wide de identity: o alvo é o restaurante inteiro
              (`workforce.md` §3.2), e não há unidade a nomear;
            - **por papel** — `owner` e `platform_admin` fazem bypass de escopo
              de unidade (kickoff #9, ADR 2.1.0001, `workforce.md` §4 — o dono
              enxerga o tenant inteiro por desenho). Um `owner` exercendo
              `"manage_staff"` **sem** declarar unidade é autorizado, e o escopo
              volta com `unit_id=None` sobre uma permissão que é unit-scoped.

            **Consequência para quem consome:** inferir "esta ação é
            tenant-wide" de `unit_id is None` é **errado**, e o erro é
            silencioso — trataria a ação de funcionário de um `owner` como
            não-escopada. Quem precisa da distinção tem de carregar a permissão
            exercida; o escopo sozinho não a carrega.
    """

    tenant_id: TenantId
    unit_id: UnitId | None


class AccessGuard(Protocol):
    """Autentica a credencial e autoriza a ação sobre um alvo.

    Duas operações, e a separação é do modelo de acesso: *quem é* (L-AG1) e *o
    que pode sobre este alvo* (L-AG2/L-AG4) são perguntas distintas, e fundi-las
    numa só faria o chamador não conseguir distinguir 401 de 403.
    """

    def authenticate(self, request: object) -> Actor:
        """Verifica a credencial da requisição e devolve o ator.

        **L-AG1** — credencial ausente ou inválida ⇒ **levanta**, e a exceção
        **sai crua**. O implementador não a captura nem a traduz.

        `request` é `object` pela mesma razão que `Actor` é: a forma da
        requisição pertence ao adapter de entrada, e staff não a interpreta.
        """
        ...

    def authorize(
        self,
        actor: Actor,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str | None = None,
    ) -> AuthorizedScope:
        """Autoriza `actor` a exercer `permission` sobre o alvo, ou levanta.

        Args:
            actor: o ator devolvido por `authenticate`, opaco para staff.
            permission: o nome da permissão exigida, como **valor**
                (`"manage_staff"`, `"manage_job_functions"`).
            tenant_id: o restaurante alvo, como string opaca. **Ausente
                significa "o tenant do próprio ator autenticado"** — jamais
                "qualquer tenant" nem "todos". O significado é do **contrato**,
                e está escrito aqui em vez de inferível de uma implementação,
                porque as **duas** são obrigadas por ele: um fake que não
                resolva o tenant do ator não cumpre este port.

                A regra é o **ADR 0.0.0005**, global, em três cláusulas: (1) o
                tenant que decide acesso sempre deriva do token, e um tenant que
                chega na requisição é declaração **confirmada contra** ele,
                nunca a fonte; (2) ele aparece no path **só quando** o bounded
                context é dono do tenant como recurso endereçável, ou o ator
                pode agir fora do próprio tenant — **nenhuma das duas vale em
                staff**, e por isso nenhuma rota o carrega; (3) onde vem do
                token, é resolvido numa **camada confiável única**, cujo lugar
                segue a **opacidade do ator** — e como este port declara
                `Actor = object` de propósito, essa camada é o
                `composition_root`, nunca o router de staff.
            unit_id: a unidade alvo, como string opaca. Ausente quando a ação
                não nomeia unidade — seja por a permissão ser tenant-wide, seja
                por o papel do ator dispensar o escopo de unidade. Ver
                `AuthorizedScope.unit_id`: são dois caminhos, e a ausência
                sozinha não diz qual deles.

        Returns:
            O `AuthorizedScope` concedido — **um por alvo** (L-AG4).

        Raises:
            Exception: a exceção do implementador, **sem tradução** — L-AG2. O
                tipo não é fixado aqui de propósito: fixá-lo obrigaria staff a
                nomear o vocabulário de erro do outro bounded context, que é
                exatamente o acoplamento que este port existe para evitar.

        **L-AG3** — o `tenant_id` do escopo devolvido nunca é vazio nem ausente;
        ator sem tenant é **negado**, jamais coagido para `""`.
        """
        ...
