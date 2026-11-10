"""Port de saída: persistência de funções de trabalho.

**As docstrings deste módulo são especificação, não comentário.** Cada método
cita a lei nomeada do concept §4 da Stage 3.2 (L-JF1…L-JF5) **+ `L-ORD`
(ADR 3.3.0003, Stage 3.3)** que o governa e o erro que levanta, porque é este
texto que a Stage 3.3 implementa em Postgres e que o teste de contrato de lá
pareia lei a lei. Declarar o comportamento só no fake é o defeito que a 2.2→2.3
pagou retroagindo o contrato (ADR 2.3.0003).

**`L-ORD` — ordem total, determinística e independente de ambiente.**
`list_by_tenant` e `find_all_by_ids` devolvem as funções ordenadas por `name` e,
em empate, por `id` — comparação **byte a byte** (codepoint), que em Postgres é
`ORDER BY name COLLATE "C", id COLLATE "C"` e em Python é
`sorted(…, key=lambda f: (f.name, f.id))`, medidos como **idênticos**.

Três coisas que esta lei declara e que não são detalhe de implementação:

- **O desempate por `id` é o que a torna total.** Nome de função é único por
  tenant hoje, mas o mesmo corpo de lei vale para o port de funcionário, onde
  homônimos são legítimos; e é o termo de desempate que a paginação da Stage 3.4
  usa como cursor. Ordem não-total pagina duplicando e omitindo linhas.
- **As duas colunas levam a colação explícita.** `COLLATE` liga-se ao operando à
  sua esquerda: um `id` sem ela volta a depender da colação do banco, justamente
  no termo do cursor.
- **A lei vale para as duas implementações.** O fake in-memory ordena igual; a
  lei não se relaxa para acomodá-lo (precedente literal do ADR 2.3.0003). É isso
  que permite à suíte de contrato ter **um** corpo de teste só.

`find_by_id` e `find_by_name` devolvem no máximo um registro e não têm ordem a
declarar. `list_by_unit` (L-JF6, Stage 3.11) obedece à mesma `L-ORD`.

**Habilitação por unidade (Stage 3.11, ADR 3.11.0001).** A função continua do
restaurante e carrega `unit_enablement` — todas as unidades ou um conjunto
não-vazio. Toda leitura deste port devolve a entidade **com** a habilitação
reidratada (L-JF4/L-JF5 e os dois `find_*`); `add` a grava junto com a linha
(L-JF1), `delete` a leva junto (L-JF3), e só `update_enablement` (L-JF7) a muda.
`update` (L-JF2) **não** a grava: renomear e mudar unidades são escritas
distintas para que uma não regrave a outra sob concorrência.

**Escopo de tenant na assinatura** (ADR 3.2.0002): não existe operação sem
`tenant_id`. A alternativa — buscar por id e comparar `entity.tenant_id` no use
case — só protege enquanto **cada** use case lembrar de comparar, e um use case
novo que esqueça compila, passa nos testes e vaza.

**Ordem de checagem, normativa** (concept §4/L-E3 e §5.4): todo método que
recebe `tenant_id` resolve **primeiro** o lookup por `(tenant_id, id)` — ausente
⇒ `*NotFoundError` — e só **depois** avalia qualquer outra guarda. Invertê-la
faz o port responder um erro que **confirma a existência de registro de outro
tenant**.
"""

from typing import Protocol

from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
    UnitId,
)


class JobFunctionRepository(Protocol):
    """Contrato de persistência da raiz de agregado `JobFunction`."""

    def add(self, job_function: JobFunction) -> None:
        """Persiste uma função nova.

        **L-JF1 — é inserção, não upsert.** Id já gravado ⇒
        `JobFunctionAlreadyExistsError`; nome já usado **no tenant**, comparado
        **verbatim** (sem trim, sem case-folding) ⇒
        `JobFunctionNameAlreadyExistsError`. Em ambos os casos **nada muda**: a
        releitura devolve os campos antigos.

        A colisão de **id** é checada **globalmente**, não por tenant — é a
        única lei destes ports que não é escopada, e a exceção é deliberada: na
        3.3 o id é a **chave primária**, e um fake que só olhasse dentro do
        tenant aceitaria uma inserção que o Postgres rejeita. A colisão de
        **nome** é por tenant (índice único `(tenant_id, name)` na 3.3).

        **L-JF1 (revisada) (Stage 3.11)** — a habilitação por unidade é gravada **com** a
        linha, atomicamente: a releitura devolve a mesma `unit_enablement`, e
        uma inserção recusada não deixa vínculo de unidade para trás.
        """
        ...

    def update(self, job_function: JobFunction) -> None:
        """Grava o estado de uma função existente.

        **L-JF2 — é `UPDATE`, não upsert.** Função inexistente **no tenant** ⇒
        `JobFunctionNotFoundError`, e **nada** é gravado. A guarda de nome de
        L-JF1 vale igual, **ignorando a própria função**: renomear para o nome
        atual não é conflito. `tenant_id` **não** é atualizável.

        **Grava só o nome** — a habilitação por unidade fica como está gravada,
        qualquer que seja a da entidade recebida (Stage 3.11). Quem a muda é
        `update_enablement` (L-JF7).
        """
        ...

    def delete(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> None:
        """Remove a função **definitivamente**.

        **L-JF3 — remoção guardada.** Inexistente **no tenant** ⇒
        `JobFunctionNotFoundError`; **referenciada por algum funcionário** ⇒
        `JobFunctionInUseError` (na 3.3, a FK `RESTRICT` traduzida pelo
        adapter), e a função continua legível.

        A referência conta **independentemente do estado do funcionário**:
        registro desligado ainda aponta para a função, e apagá-la deixaria o
        cadastro apontando para função inexistente.

        Ordem: o lookup por `(tenant_id, id)` vem **antes** da checagem de
        referências — apagar função do tenant A com `tenant_id` do B devolve
        `JobFunctionNotFoundError`, nunca `JobFunctionInUseError`, que
        confirmaria a existência do registro alheio.

        **L-JF3 (revisada) (Stage 3.11)** — a habilitação por unidade sai junto com a
        função; recriar uma função com o mesmo id não herda unidades antigas.
        """
        ...

    def find_by_id(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> JobFunction | None:
        """Devolve a função **do tenant**, ou `None` se não existir nele.

        Função existente em **outro** tenant devolve `None`: id alheio é
        indistinguível de inexistente (concept §5.4).
        """
        ...

    def find_by_name(self, tenant_id: TenantId, name: str) -> JobFunction | None:
        """Devolve a função homônima **do tenant**, ou `None`.

        Devolve a **entidade**, não um booleano, de propósito: o `rename`
        precisa saber **qual** função tem o nome para decidir se o conflito é
        consigo mesma — com booleano, renomear uma função para o próprio nome
        falharia. A comparação é **verbatim**: `"Cozinheiro"` e `"cozinheiro "`
        são nomes distintos (workforce §3.2).
        """
        ...

    def find_all_by_ids(
        self, tenant_id: TenantId, job_function_ids: frozenset[JobFunctionId]
    ) -> tuple[JobFunction, ...]:
        """Resolve um conjunto de ids **dentro do tenant**.

        **L-JF4 — devolve só as encontradas e não levanta erro** para ids
        ausentes: quem compara com o conjunto pedido, para descobrir o que
        falta, é o chamador. **Não filtra por estado porque a função não tem
        estado** (ADR 3.2.0005). Id de outro tenant simplesmente não vem.

        **`L-ORD` —** o resultado vem ordenado por `name`, desempatando por
        `id`, byte a byte. O parâmetro é um `frozenset` e portanto não carrega
        ordem: a do resultado é a da lei, não a do pedido.
        """
        ...

    def list_by_tenant(self, tenant_id: TenantId) -> tuple[JobFunction, ...]:
        """Lista **todas** as funções do tenant, e nenhuma de outro.

        **L-JF5 —** não há flag de estado porque não há estado.

        **`L-ORD` —** ordenado por `name`, desempatando por `id`, byte a byte.
        """
        ...

    def list_by_unit(self, tenant_id: TenantId, unit_id: UnitId) -> tuple[JobFunction, ...]:
        """Lista as funções do tenant **habilitadas na unidade** (Stage 3.11).

        **L-JF6 —** devolve as funções do tenant cuja habilitação cobre
        `unit_id`: as habilitadas em todas as unidades **e** as que nomeiam esta
        unidade. Função restrita a outras unidades não vem; função de outro
        tenant não vem, mesmo que nomeie uma unidade com o mesmo id.

        **`L-ORD` —** ordenado por `name`, desempatando por `id`, byte a byte.
        """
        ...

    def update_enablement(self, job_function: JobFunction) -> None:
        """Substitui onde a função vale (Stage 3.11, ADR 3.11.0001 §5).

        **L-JF7 —** é `UPDATE`, não upsert: função inexistente **no tenant** ⇒
        `JobFunctionNotFoundError`, e **nada** é gravado. Grava **só** a
        habilitação — o nome fica como está gravado — e a substitui inteira: as
        unidades que saíram deixam de valer, as que entraram passam a valer.
        """
        ...
