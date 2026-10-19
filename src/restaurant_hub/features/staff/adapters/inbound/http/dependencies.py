"""Validador de identificador, requisito de acesso por rota e provedor de ator.

**Este módulo não decide acesso.** Ele declara qual permissão cada rota exige e
qual é o alvo, e delega ao port `AccessGuard`. Não há tabela de papéis, mapa de
permissões nem lógica de bypass aqui, e nenhum nome do vocabulário de identity é
importado: as duas permissões atravessam a fronteira como **valores**
(`"manage_staff"`, `"manage_job_functions"`), jamais como enum (ADR 3.4.0001,
ADR 2.4.0003).

## Por que a validação de identificador é de adapter, e não de domínio

**A pergunta é legítima e a resposta é medida, não estilística** — sem ela
escrita, um refactor futuro "limpa" este módulo empurrando a regra para o
domínio, e o buraco reabre (ADR 3.6.0002 §Consequences).

Um identificador de staff é um `NewType` sobre `str` (`identifiers.py`: *"este
módulo não tem lógica de runtime"*). `NewType` **não tem gancho de runtime**:
`UnitId("\\x00")` constrói, passa mypy strict e chega ao banco. E um identificador
que vem da requisição **nunca passa por entidade nenhuma** no caminho que
importa: o `target_unit_id` da cópia vai para `units.find_by_id` **dentro de
identity**, e cada elemento de `job_function_ids` vai para `find_all_by_ids` do
repositório **antes** da construção do `Employee`. `Employee.__post_init__` valida
`id`, `tenant_id`, `unit_id`, `name` e a não-vacuidade do conjunto — **nenhum
elemento** dele.

Consequência medida: `{"job_function_ids": ["\\x00"]}` produz `psycopg.DataError`,
recusado **client-side**, que não é `IntegrityError` (o tradutor da 3.3 nunca é
chamado), não é `StaffError` e não é `IdentityError` — nenhum handler o alcança,
e vira **500**. A borda é o último ponto em que ainda dá para recusá-lo como erro
de negócio.

## A ordem é contrato: autenticar → validar → autorizar

- **Autenticar primeiro** (§5.1): uma requisição sem credencial tem de receber
  401, não um 422 que deixaria um cliente sem credencial sondar a forma do
  payload. Por isso a autenticação é `Depends` — o FastAPI resolve dependências
  **antes** de validar o corpo contra o schema.
- **Validar antes de autorizar**: é o que impede um valor cru de alcançar
  `units.find_by_id` dentro de identity, no passo 5 de `AuthorizeActionUseCase`.

**A ordem não é observável pelo status**, e por isso o critério que a trava
(CA21) é sobre a **ausência de chamada**: um 422 na resposta é compatível tanto
com "validou antes" quanto com "o guard rodou, passou, e a validação veio
depois". O que se assere é que o dublê do port não registrou **nenhum**
`authorize(...)` — deliberadamente não `calls == []`, porque o mesmo dublê
registra `authenticate`, que a ordem exige que rode primeiro e que não toca
identificador nenhum.

## O que o validador NÃO faz

**Exatamente três valores são rejeitados** — vazio, só-whitespace e contendo o
byte NUL. Nada além disso é normalizado, aparado ou reescrito: o ADR 2.3.0005
proíbe normalização silenciosa, e a Stage 3.3 mediu que o resto do conjunto
adversarial (acento, emoji com ZWJ, quebra de linha, aspas, mil caracteres) faz
round-trip verbatim. A restrição é do tamanho da divergência medida, e não maior.

**O tenant não é dobrado aqui.** Ele nunca chega pela requisição (concept §5.3,
ADR 0.0.0005): não há o que validar, e uma função que o aceitasse convidaria
alguém a passá-lo.

**Limite medido, declarado para não virar critério impossível:** identificador
**vazio** em segmento de **path** não casa `[^/]+`, e o Starlette responde
404/405 sem que este validador rode. É por isso que o eixo de path de CA20
exclui `""` — critério de segurança que não fecha é critério que alguém relaxa.
"""

from dataclasses import dataclass
from typing import Annotated, Final, Never, get_args, get_origin

from fastapi import Depends, Request
from pydantic import BaseModel

from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_JOB_FUNCTIONS,
    PERMISSION_MANAGE_STAFF,
    PERMISSION_MANAGE_USERS,
    AccessGuard,
    Actor,
)
from restaurant_hub.features.staff.domain.exceptions.errors import InvalidIdentifierError

# O byte que produz 500 hoje, e o único dos três rejeitados que o produz. Os
# outros dois — vazio e só-whitespace — são recusados por higiene declarada:
# identificador em branco é o balde de falso isolamento que
# `InvalidIdentifierError` nomeia, e uma consulta com chave sem sentido é ruído
# que esconde defeito de cliente. O motivo é esse, e **não** "senão vira 500";
# a justificativa errada envelhece pior que nenhuma (concept §5.14).
_BYTE_NUL: Final = "\x00"

# As três permissões que staff cita moram no módulo do **port** desde a Stage 3.7
# (ADR 3.7.0001 §5): os use cases autorizam com elas, e application não importa
# adapter. A borda as importa de lá — continuam atributos deste módulo, e é daqui
# que os requisitos abaixo e os testes de borda as leem.


def validate_identifier(raw: str, *, entity: str) -> str:
    """Valida um identificador vindo da requisição — path, query **ou** corpo.

    Args:
        raw: o valor cru, exatamente como chegou.
        entity: o que o identificador endereça, só para a mensagem do erro.

    Returns:
        A mesma string, **verbatim**. Nada é aparado nem reescrito.

    Raises:
        InvalidIdentifierError: vazio, só-whitespace ou contendo o byte NUL —
            erro de domínio de staff, que o mapa de status classifica como 422.
    """
    if not raw.strip() or _BYTE_NUL in raw:
        raise InvalidIdentifierError(entity)
    return raw


@dataclass(frozen=True)
class AccessRequirement:
    """O requisito de acesso de uma rota: a permissão exigida e a forma do alvo.

    É **declaração**, não decisão: quem decide é o port, e por trás dele o
    `AuthorizeActionUseCase` de identity. O que esta classe carrega é o que o
    router teria de dizer de qualquer forma ao chamar `authorize` — e concentrá-lo
    num valor por rota é o que impede que duas rotas do mesmo recurso declarem
    requisitos diferentes sem que ninguém note.

    Attributes:
        permission: o nome da permissão, como valor opaco para identity.
        names_unit: se o alvo nomeia uma unidade. **Falso não significa
            "tenant-wide por papel"**: significa que a rota endereça o
            restaurante inteiro porque a permissão é tenant-wide
            (ADR 3.4.0008 — o passo 4 do guard dispensa a unidade **por
            permissão**). A distinção importa porque `AuthorizedScope.unit_id`
            chega a `None` por **dois** caminhos e não distingue entre eles.
    """

    permission: str
    names_unit: bool


# Os dois requisitos desta Stage. O catálogo de funções endereça o tenant inteiro
# (`workforce.md` §3.2); o funcionário endereça a unidade do path (ADR 3.4.0007).
#
# O sufixo `_ACCESS` não é decoração: sem ele, `MANAGE_JOB_FUNCTIONS` importado
# aqui teria o **mesmo nome** que o membro `Permission.MANAGE_JOB_FUNCTIONS` de
# identity — que é justamente o símbolo que staff nunca pode importar (CA07). Um
# leitor do router veria o nome proibido e concluiria a coisa errada sobre a
# fronteira entre os dois bounded contexts.
MANAGE_JOB_FUNCTIONS_ACCESS: Final = AccessRequirement(
    permission=PERMISSION_MANAGE_JOB_FUNCTIONS, names_unit=False
)
MANAGE_STAFF_IN_UNIT_ACCESS: Final = AccessRequirement(
    permission=PERMISSION_MANAGE_STAFF, names_unit=True
)
# Stage 3.5 — o requisito adicional de R17. `names_unit=True` porque o alvo é a
# unidade do path, como em toda rota de funcionário: `manage_users` é
# unit-scoped para `manager`/`hr` (ADR 3.4.0006), e o guard decide o resto.
MANAGE_USERS_IN_UNIT_ACCESS: Final = AccessRequirement(
    permission=PERMISSION_MANAGE_USERS, names_unit=True
)


def get_access_guard() -> AccessGuard:
    """Chave do `dependency_overrides`, preenchida pelo composition root.

    Levanta se for chamada de verdade: significa que o wiring não aconteceu.
    Falhar alto é melhor que servir um `None` que só quebra três camadas adiante
    — é o padrão que o router de identity já usa.
    """
    _nao_conectado("staff_access_guard")


def _nao_conectado(nome: str) -> Never:
    raise RuntimeError(
        f"dependência {nome!r} não foi conectada pelo composition root — "
        "veja wire_dependencies() e create_app()"
    )


def authenticated_actor(
    request: Request,
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> Actor:
    """Autenticação como **dependência**, e não como chamada no corpo da rota.

    A diferença é observável: o FastAPI resolve as dependências **antes** de
    validar o corpo da requisição. Autenticando aqui, uma requisição sem
    credencial recebe 401 mesmo com corpo que não casa o schema; autenticando
    dentro da rota, o 422 da validação chegaria primeiro — e um cliente sem
    credencial nenhuma passaria a sondar a forma do payload de rotas protegidas.

    `Depends`, e não middleware (ADR 2.4.0003): com `Depends`, uma rota **sem**
    guard é visível na assinatura da função; com middleware global seria preciso
    manter uma allowlist de rotas públicas, que erra por omissão e **abre** rota
    sem querer.

    **A exceção sai crua** (L-AG1): nada é capturado aqui, para que a faixa 401
    de staff seja byte-idêntica à de identity.
    """
    actor: Actor = guard.authenticate(request)
    return actor


StaffAccessGuard = Annotated[AccessGuard, Depends(get_access_guard)]
CurrentActor = Annotated[Actor, Depends(authenticated_actor)]


@dataclass(frozen=True)
class IdentifierField:
    """Um campo de identificador de um schema de request.

    Attributes:
        name: o nome do campo.
        is_collection: se o campo é uma **lista** de identificadores. A distinção
            é o que permite às varreduras corromper um **elemento** de
            `job_function_ids` em vez do campo inteiro — corromper o campo
            produziria um erro de forma (`RequestValidationError`, 422 do
            framework) em vez do erro de identificador que se quer medir.
    """

    name: str
    is_collection: bool


def identifier_fields(model: type[BaseModel]) -> tuple[IdentifierField, ...]:
    """Os campos de identificador (`*_id` / `*_ids`) de um schema de request.

    Existe para que as varreduras de borda **derivem** o domínio em vez de
    listá-lo: um campo de identificador acrescentado a um request entra na
    varredura de CA20 sem que ninguém precise lembrar de estender um teste.

    **Não tem chamador de produção, e a ausência é declarada.**
    `grep -rn "identifier_fields(" src/` devolve **só** esta definição: as rotas
    validam o identificador de corpo à mão, uma a uma, e quem consome esta
    função são as varreduras estruturais. É a mesma forma que
    `AccessRequirement.names_unit` tem — declaração cujo leitor é o teste —, e
    fica dita aqui para que ninguém a leia como plumbing esquecido nem a apague
    por parecer código morto: apagá-la esvazia o domínio de CA20 no eixo do
    corpo. Plugá-la no router é a outra saída, e vale a medição do dia em que a
    validação à mão divergir entre duas rotas.

    **Alcance declarado:** os campos de **primeiro nível** do modelo. Hoje nenhum
    modelo aninhado dos requests de staff carrega identificador — o único
    aninhado é a união do perfil de jornada —, e se um passar a carregar, esta
    função é o lugar de estendê-la. Dito em vez de presumido, porque uma
    varredura que silenciosamente não alcança metade do domínio é pior que
    nenhuma.
    """
    return tuple(
        IdentifierField(name=nome, is_collection=_e_colecao(info.annotation))
        for nome, info in model.model_fields.items()
        if nome.endswith(("_id", "_ids"))
    )


def _e_colecao(anotacao: object) -> bool:
    """Se a anotação alcança um `list[...]`, inclusive sob `| None`."""
    if get_origin(anotacao) is list:
        return True
    return any(_e_colecao(argumento) for argumento in get_args(anotacao))
