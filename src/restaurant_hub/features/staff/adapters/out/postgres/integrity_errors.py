"""Tradução de `IntegrityError` do Postgres para os erros de aplicação de staff.

Chama-se `integrity_errors` e não `errors` de propósito: `application/errors.py`
é a **hierarquia** de erros do BC; este módulo é só o **tradutor** que leva uma
violação de constraint até ela.

**A tradução é por NOME de constraint**, lido de `diag.constraint_name` — nunca
por texto de mensagem, cujo conteúdo varia entre versões e locales do Postgres e
cuja quebra nenhum gate pegaria. Por isso todas as constraints são nomeadas
explicitamente em `tables.py`.

**E é por OPERAÇÃO, o que diverge de identity — ADR 3.3.0004.** A razão é
medida, não estética: `fk_employee_job_functions_job_function` é violada por
duas operações com significados de negócio **opostos**, com o **mesmo** nome e o
mesmo sqlstate `23503`:

| Operação | Significado | Erro |
|---|---|---|
| `INSERT` de vínculo com função inexistente no tenant | L-E4 | `JobFunctionNotFoundError` |
| `DELETE` da função referenciada | L-JF3 | `JobFunctionInUseError` |

Um mapa global por nome — o de identity — responderia errado em metade dos
casos, e erraria de forma **plausível**: "função não encontrada" ao apagar uma
função que existe, ou "função em uso" ao atribuir a função de outro
restaurante. Erro plausível é pior que erro cru, porque não convida a
investigar. A ambiguidade é resolvida pela **intenção do chamador**, que é
sempre conhecida, e nunca por inspeção de texto (`diag.message_detail` seria
parsing de mensagem com outro nome).

**Idioma: inglês**, divergindo do `traduzir` de identity. Estes nomes são **API
de módulo**, não identificadores locais; CONVENTIONS §1 é literal e a §7 do
technical da 3.2 já registrou o `[finding]` cuja direção é renomear os
identificadores PT deste BC. A divergência fica registrada aqui para que uma
varredura futura trate o módulo de identity como a dívida, e não como o padrão a
replicar.

**Só constraint com significado de negócio é traduzida** (precedente: concept
2.3 §7 Decisão 7). Sobem intactas, deliberadamente:

- as **três** FKs de filha para pai (`fk_employee_job_functions_employee`,
  `fk_employee_unavailabilities_employee`,
  `fk_employee_shift_preferences_employee`);
- as **PKs das três filhas**;
- as **cinco** `CHECK`;
- qualquer constraint **desconhecida**.

Todas só são alcançáveis por bug do mapper ou corrupção escrita por fora do
domínio — as invariantes correspondentes já são impostas pelo `__post_init__`
das entidades. Vesti-las de erro de negócio produziria um 4xx plausível
escondendo o defeito, que é a pior coisa que se pode fazer com um bug.

**Erros que nem chegam aqui:** `DeadlockDetected` (`40P01`) e falhas de
serialização (`40001`) são `OperationalError`, não `IntegrityError`. A §5.20
torna o primeiro raro (as filhas são escritas por diferença, não por reescrita
cega); o mapeamento HTTP dos dois está escalado para a Stage 3.4.
"""

from collections.abc import Callable, Mapping

from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.staff.application.errors import (
    EmployeeAlreadyExistsError,
    JobFunctionAlreadyExistsError,
    JobFunctionInUseError,
    JobFunctionNameAlreadyExistsError,
    JobFunctionNotFoundError,
)

# Nome da constraint -> fábrica da exceção de aplicação.
#
# A fábrica recebe o "detalhe" já extraído pelo chamador (o id ou o nome em
# conflito), porque só o repositório sabe o que estava tentando gravar — a
# mensagem do Postgres nem sempre carrega o valor de forma confiável, e lê-la
# seria parsing de mensagem.
ConstraintMap = Mapping[str, Callable[[str], Exception]]


# `add` de função (L-JF1). A colisão de id é **global**: a PK não inclui o
# tenant, e `uq_job_functions_id_tenant` — a âncora da FK composta — pode
# responder pela mesma colisão. As duas apontam para o mesmo erro.
ON_INSERT_JOB_FUNCTION: ConstraintMap = {
    "pk_job_functions": JobFunctionAlreadyExistsError,
    "uq_job_functions_id_tenant": JobFunctionAlreadyExistsError,
    "uq_job_functions_tenant_name": JobFunctionNameAlreadyExistsError,
}

# `update` de função (L-JF2). **Só** o conflito de nome: `id` entra apenas no
# `WHERE` e `tenant_id` nunca entra no `SET` (§5.3), então nenhuma das duas
# constraints de identidade é alcançável por esta operação. Repeti-las aqui
# faria o mapa afirmar um caminho que não existe.
ON_UPDATE_JOB_FUNCTION: ConstraintMap = {
    "uq_job_functions_tenant_name": JobFunctionNameAlreadyExistsError,
}

# `delete` de função (L-JF3). O `RESTRICT` da FK é a guarda de remoção, e é
# **aqui** que aquela constraint significa "em uso".
ON_DELETE_JOB_FUNCTION: ConstraintMap = {
    "fk_employee_job_functions_job_function": JobFunctionInUseError,
}

# `add`/`update` de funcionário (L-E1, L-E4). A **mesma** constraint da linha
# acima, com o significado **oposto**: aqui ela é o backstop da pré-checagem
# referencial — a corrida em que a função some entre a checagem e a escrita —, e
# por isso vira `JobFunctionNotFoundError`. É esta linha, contra a anterior, que
# um mapa global não consegue expressar.
ON_WRITE_EMPLOYEE: ConstraintMap = {
    "pk_employees": EmployeeAlreadyExistsError,
    "uq_employees_id_tenant": EmployeeAlreadyExistsError,
    "fk_employee_job_functions_job_function": JobFunctionNotFoundError,
}


def constraint_name(error: IntegrityError) -> str | None:
    """Extrai o nome da constraint violada, ou `None` se não der para saber.

    O psycopg 3 expõe isso de forma estruturada em `diag.constraint_name`, sem
    parsing de texto. Quando o atributo não existe (outro driver, erro que não é
    de constraint), devolve `None` e o chamador deixa o erro subir — degradar
    para parsing de mensagem seria trocar uma falha explícita por uma silenciosa.
    """
    original = getattr(error, "orig", None)
    diag = getattr(original, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return str(name) if name else None


def translate(error: IntegrityError, constraint_map: ConstraintMap, detail: str) -> Exception:
    """Devolve a exceção de aplicação correspondente à operação, ou o próprio `error`.

    **Devolve** em vez de levantar, como o `traduzir` de identity: o
    `raise … from error` fica no repositório, onde preserva o `__cause__` — e
    perder a cadeia de causa custaria caro justamente no diagnóstico de um
    conflito de integridade.

    `constraint_map` é o mapa **da operação** em curso; `detail` é o valor em
    conflito (id ou nome), fornecido por quem tentou gravar.
    """
    name = constraint_name(error)
    if name is None:
        return error
    factory = constraint_map.get(name)
    if factory is None:
        # Constraint conhecida do banco mas sem significado de negócio **nesta
        # operação** (as FKs de filha, as PKs das filhas, as CHECK), ou
        # constraint nova que ninguém mapeou: sobe intacta.
        return error
    return factory(detail)
