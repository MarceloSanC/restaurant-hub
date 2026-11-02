"""Schemas Pydantic de request e response — o boundary HTTP do BC identity.

**Pydantic vive só aqui.** Os use cases recebem e devolvem dataclasses da camada
`application`; um schema nunca atravessa para dentro.

Quatro decisões deste módulo valem explicação, porque cada uma parece um detalhe e
nenhuma é:

**1. Credencial em request é `SecretStr`.** O `repr` de um `SecretStr` é
`**********`, então uma senha ou um refresh token não vazam por traceback com
`--showlocals`, captura de locals do Sentry ou log de debug do modelo. É a mesma
disciplina que `UserCredentials.password_hash` adotou na 2.3.

**2. Nenhum schema de resposta tem campo de senha, hash ou fingerprint.** Não é
só omissão: há teste que varre `model_fields` de **todo** schema `*Response`
contra uma lista negra, de modo que um schema novo entra na varredura sem ninguém
lembrar dele.

**3. `CreateUserRequest` não tem `tenant_id`, e a ausência é a defesa.** O tenant
do usuário criado vem do **ator** (concept §5 regra 3). Se o campo existisse,
alguém acabaria por lê-lo — e o corpo de um POST viraria vetor de escalada entre
tenants. Campos extras enviados pelo cliente são **ignorados** (default do
Pydantic v2, mantido de propósito): endurecer para `extra="forbid"` faria a
requisição maliciosa receber 422 em vez de ser silenciosamente desarmada, e o
teste que prova a defesa (CA13) deixaria de poder observá-la.

**4. Credencial em resposta é declarada no campo, e é a declaração que tira a
resposta do cache.** Os dois tokens de `TokenResponse` são `Credential`: a marca
`x-credential` no JSON Schema do campo faz o middleware de
`shared/infrastructure/http/credential_no_store.py` gravar `Cache-Control:
no-store` e `Pragma: no-cache` em toda resposta de login e de refresh (issue
#61). A chave vai por extenso porque adapter não importa `shared.infrastructure`
(LAYOUT §3); o teste deste schema a confere contra o detector de `shared`. Um
schema de resposta novo que carregue credencial usa o mesmo alias e nasce com os
cabeçalhos, qualquer que seja o seu nome.

A conversão de texto para value object (`Email`, `Role.from_string`) **não**
acontece aqui: fica no router, para que a falha seja erro de domínio — e caia no
mapa de status de `error_handlers.py` — em vez de virar um
`RequestValidationError` do FastAPI, que seguiria outro caminho.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, SecretStr

# Campo de resposta que carrega credencial (nota 4 do módulo). A anotação do campo
# continua `str` — a marca vai para o `FieldInfo` e para o JSON Schema, não para o
# tipo.
Credential = Annotated[str, Field(json_schema_extra={"x-credential": True})]


class LoginRequest(BaseModel):
    """Credenciais de login."""

    email: str
    password: SecretStr


class RefreshRequest(BaseModel):
    """Pedido de rotação do par de tokens."""

    refresh_token: SecretStr


class LogoutRequest(BaseModel):
    """Pedido de encerramento da sessão do refresh token apresentado."""

    refresh_token: SecretStr


class TokenResponse(BaseModel):
    """Par de tokens emitido por login ou rotação.

    `refresh_token` é `str`, e não `SecretStr`, por necessidade: ele **é** a
    resposta ao cliente, e um `SecretStr` serializaria como `**********`. A
    proteção do valor, no caminho de volta, é o `SecretStr` do request. No
    caminho de ida, é a marca `Credential` dos dois tokens que impede a resposta
    de ficar em cache (nota 4 do módulo).
    """

    access_token: Credential
    refresh_token: Credential
    token_type: str = "bearer"
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


class CreateUnitRequest(BaseModel):
    """Criação de unidade sob um restaurante.

    Sem `restaurant_id`: o restaurante é o recurso pai, e vem do path.
    """

    name: str


class UnitResponse(BaseModel):
    """Unidade criada."""

    id: str
    restaurant_id: str
    name: str


class CreateOwnerRequest(BaseModel):
    """O `owner` de um restaurante (ação de plataforma).

    Corpo de `POST /restaurants/{id}/owners` e campo `owner` de
    `ProvisionRestaurantRequest` — as duas rotas que emitem `owner` (ADR 0.0.0012).

    Sem campo `role`: o papel é fixado em `Role.OWNER` no código (no router e no
    use case de provisionamento). É o que garante que **nenhuma rota emite
    `platform_admin`** — se o papel viesse do request, estas seriam as rotas por
    onde ele entraria (ADR 2.4.0003 §2b).
    """

    email: str
    password: SecretStr


class ProvisionRestaurantRequest(BaseModel):
    """Provisionamento de um tenant: o restaurante e o seu primeiro `owner`.

    Só `platform_admin` alcança. O dono tem a forma de `CreateOwnerRequest` —
    sem `role` e sem tenant: o papel é `owner`, fixado no use case, e o tenant é
    o restaurante que nasce junto (ADR 0.0.0012).
    """

    name: str
    owner: CreateOwnerRequest


class CreateUserRequest(BaseModel):
    """Criação de usuário dentro do tenant do ator.

    Sem `tenant_id` — ver a nota 3 do módulo.
    """

    email: str
    password: SecretStr
    role: str
    unit_ids: list[str] = Field(default_factory=list)


class UserResponse(BaseModel):
    """Usuário criado.

    Carrega `tenant_id` porque o cliente precisa saber em que tenant a conta
    nasceu — mas o valor é o que o servidor **decidiu**, não o que o request
    pediu.
    """

    id: str
    email: str
    role: str
    tenant_id: str | None
    unit_ids: list[str]


class ProvisionedRestaurantResponse(BaseModel):
    """Restaurante provisionado, com o dono criado na mesma unidade de trabalho."""

    id: str
    name: str
    owner: UserResponse


class InviteUserRequest(BaseModel):
    """Convite de uma pessoa que ainda não tem conta.

    **Sem campo de senha, e a ausência é o ponto da Stage inteira**: quem convida
    não escolhe, não conhece e não transporta a credencial de quem é convidado.

    Sem `tenant_id` pela mesma razão de `CreateUserRequest` (nota 3 do módulo): o
    tenant vem do ator.
    """

    email: str
    role: str
    unit_ids: list[str] = Field(default_factory=list)


class RequestPasswordResetRequest(BaseModel):
    """Pedido público de redefinição de senha.

    Só o e-mail. A resposta é a mesma para endereço cadastrado e não cadastrado —
    não há campo, status ou corpo que os distinga (concept §5 regra 7).
    """

    email: str


class SetPasswordRequest(BaseModel):
    """Redenção do token: define a senha da conta.

    **Sem campo de usuário, e a ausência é a defesa.** O usuário alvo sai do
    registro que o servidor gravou ao emitir o token. Se houvesse um `user_id`
    aqui, quem pedisse uma redefinição para a própria conta definiria a senha de
    qualquer outra.

    Os dois campos são `SecretStr`: um é credencial bearer viva, o outro é senha
    em claro. Nenhum dos dois pode aparecer num traceback com `--showlocals`.
    """

    token: SecretStr
    password: SecretStr
