"""Erros da camada de aplicação do BC staff.

Todos herdam de `StaffError` (domínio, Stage 3.1) e, por consequência, de
`DomainError`, que é a única raiz com handler HTTP registrado (ADR 2.2.0003).
A alternativa que o ADR recusa — uma hierarquia de aplicação paralela, fora
de `DomainError` — deixou de ser representável na #45, quando o
`ApplicationError` do template foi removido por não ter subclasse nem `raise`
em seis Stages. O pior caso não-ajustado é 422; a
Stage 3.4 refina para 404/409 registrando handlers, sem tocar nesta camada.

Os **dois** erros de "não encontrado" herdam também de `NotFoundError`, **nesta
ordem**: a MRO fica `… -> StaffError -> NotFoundError -> DomainError`, e o
lookup de handler do Starlette (que percorre `type(exc).__mro__`) alcança o
handler da raiz do BC antes do genérico, e o 404 antes do 422.

São dois, não três: o `UnavailabilityNotFoundError` do domínio 3.1 continua
herdando **só** de `StaffError` e é deliberadamente **422**, porque fala de um
**valor dentro do agregado** (um período que aquele registro não tem), não de
um recurso endereçável — o funcionário existe e foi encontrado (concept §4).

Erros de invariante do domínio (`InvalidNameError`, `EmptyJobFunctionsError`,
`OverlappingUnavailabilityError` etc.) **não** são reembrulhados: sobem como
estão, com a mesma raiz `StaffError` (concept §5.15).
"""

from restaurant_hub.features.staff.domain.exceptions.errors import StaffError
from restaurant_hub.shared.domain.exceptions.base import NotFoundError


class JobFunctionNotFoundError(StaffError, NotFoundError):
    """Função de trabalho inexistente **no tenant consultado**.

    Como todo acesso é escopado por tenant (ADR 3.2.0002), uma função que
    existe em **outro** restaurante cai aqui: id alheio é indistinguível de
    inexistente, e nenhum erro pode confirmar a existência do registro alheio
    (concept §5.4).
    """

    def __init__(self, job_function_id: str) -> None:
        super().__init__(f"função de trabalho não encontrada: {job_function_id!r}")


class EmployeeNotFoundError(StaffError, NotFoundError):
    """Registro de funcionário inexistente **no tenant consultado**.

    Mesma regra de escopo de `JobFunctionNotFoundError`: registro de outro
    tenant devolve este erro, nunca `EmployeeRelocationError` (concept §5.4
    vence a L-E3).
    """

    def __init__(self, employee_id: str) -> None:
        super().__init__(f"funcionário não encontrado: {employee_id!r}")


class JobFunctionNameAlreadyExistsError(StaffError):
    """Nome de função já usado no tenant, comparado **verbatim**.

    Sem trim e sem case-folding (workforce §3.2): `"Cozinheiro"` e
    `"cozinheiro "` são nomes distintos e ambos são aceitos. Na 3.3 a guarda
    vira o índice único `(tenant_id, name)`.
    """

    def __init__(self, name: str) -> None:
        super().__init__(f"nome de função de trabalho já usado no restaurante: {name!r}")


class JobFunctionAlreadyExistsError(StaffError):
    """Função com o mesmo id já gravada — `add` é inserção, não upsert (L-JF1).

    A colisão de id é checada **globalmente**, não por tenant: na 3.3 o id é a
    chave primária, e um fake que só olhasse dentro do tenant aceitaria uma
    inserção que o Postgres rejeita (ADR 2.3.0003).
    """

    def __init__(self, job_function_id: str) -> None:
        super().__init__(f"função de trabalho já existe: {job_function_id!r}")


class EmployeeAlreadyExistsError(StaffError):
    """Funcionário com o mesmo id já gravado — `add` é inserção (L-E1).

    Escopo global do id, pelo mesmo motivo de `JobFunctionAlreadyExistsError`.
    """

    def __init__(self, employee_id: str) -> None:
        super().__init__(f"funcionário já existe: {employee_id!r}")


class JobFunctionInUseError(StaffError):
    """Remoção de função referenciada por algum funcionário (L-JF3).

    A referência conta em **qualquer** unidade do tenant e
    **independentemente do estado** do funcionário: registro desligado ainda
    aponta para a função, e apagá-la deixaria o cadastro apontando para função
    inexistente, furando a invariante "ao menos uma função" da 3.1.
    """

    def __init__(self, job_function_id: str) -> None:
        super().__init__(f"função de trabalho em uso por algum funcionário: {job_function_id!r}")


class EmployeeInUseError(StaffError):
    """Remoção de funcionário referenciado por outro agregado (L-E5).

    **Nasce sem produtor em v1**, e isso é declarado, não esquecido: nada no
    escopo atual referencia o registro de funcionário. Quem passa a produzi-la
    é o **Step 4** (alocação), quando a escala referenciar o registro — via a
    FK da 3.3. Publicá-la agora evita que a 3.4/Step 4 retroajam o contrato do
    port, o defeito exato que a 2.2→2.3 pagou (ADR 2.3.0003).
    """

    def __init__(self, employee_id: str) -> None:
        super().__init__(f"funcionário em uso por outro registro: {employee_id!r}")


class EmployeeRelocationError(StaffError):
    """`update` que mudaria a unidade do registro — localização é imutável (L-E3).

    A lei tem erro **nomeado** de propósito: sem ele, a única saída seria
    gravar o que veio (mover o registro em silêncio) ou gravar o que estava
    (descartar a escrita em silêncio), e as duas são corrupção silenciosa. O
    único caminho para existir em outra unidade é a cópia (concept §5.10).

    É erro **intra-tenant**: só alcançável quando o registro foi encontrado no
    tenant pedido e a unidade diverge. Com tenant divergente o erro é
    `EmployeeNotFoundError` (concept §5.4) — por isso a mensagem cita as duas
    unidades e **não** cita o tenant.
    """

    def __init__(self, employee_id: str, stored_unit_id: str, requested_unit_id: str) -> None:
        super().__init__(
            f"funcionário {employee_id!r} não pode ser relocalizado: "
            f"gravado na unidade {stored_unit_id!r}, recebido com {requested_unit_id!r}"
        )


class SameUnitCopyError(StaffError):
    """Cópia cujo destino é a própria unidade de origem (concept §5.11).

    Detectável **sem** vínculo — são dois `unit_id` que o use case já tem em
    mãos. Copiar duas vezes para um destino **diferente** da origem, por outro
    lado, não é detectável nesta camada e é limite declarado, não erro.
    """

    def __init__(self, unit_id: str) -> None:
        super().__init__(f"cópia exige unidade destino diferente da origem: {unit_id!r}")


class LoginEmailAlreadyInUseError(StaffError):
    """O e-mail já é login de alguém — em **qualquer** tenant (kickoff #2).

    É a tradução, pelo gateway, do `EmailAlreadyRegisteredError` de identity
    (L-IG2, concept 3.5 §4): staff nomeia a condição no seu vocabulário porque o
    gerente precisa distingui-la das demais recusas de R17. A mensagem cita
    **só** o e-mail enviado — nunca de quem é, nem em que tenant: dizer mais
    seria o oráculo de existência global de conta que a 2.5 §13 registrou e que
    esta Stage mantém por coerência (concept 3.5 §10). 409: conflito com estado
    já gravado do outro lado da fronteira.
    """

    def __init__(self, email: str) -> None:
        super().__init__(f"e-mail já usado como login: {email!r}")


class InvalidLoginEmailError(StaffError):
    """O conteúdo enviado como e-mail de login não é um e-mail.

    Tradução do `InvalidEmailError` de identity (L-IG2): staff **não** valida
    e-mail — o VO `Email` é de identity, e é a fachada quem o constrói (concept
    3.5 §5.7). Inclui o byte NUL, que o VO passa a recusar nesta Stage (D8).
    422: invariante violada pelo conteúdo enviado.
    """

    def __init__(self, email: str) -> None:
        super().__init__(f"e-mail de login inválido: {email!r}")


class EmployeeHasLoginError(StaffError):
    """Remoção definitiva de registro **com login** — recusada (ADR 3.5.0003 §1b).

    Irmã de `EmployeeInUseError`: as duas guardam a remoção (L-E5), com causas
    diferentes. Remoção definitiva existe para *cadastro criado por engano*
    (ADR 3.2.0006); um registro que recebeu login não é engano, e apagá-lo
    deixaria em identity uma conta que ninguém aponta — e-mail tomado
    globalmente, membership viva, irrecuperável até existir "desvincular". O
    caminho é **desligar** (R13), que preserva o registro e corta o acesso que
    ele concede (as sessões do login de funcionário — ADR 3.8.0001).
    Vale também para o desligado com login: o vínculo é história (concept 3.5
    §5.5). 409: conflito com estado já gravado.
    """

    def __init__(self, employee_id: str) -> None:
        super().__init__(
            f"funcionário com login não pode ser removido; desligue-o: {employee_id!r}"
        )
