"""Schemas Pydantic de request e response — o boundary HTTP do BC identity.

**Pydantic vive só aqui.** Os use cases recebem e devolvem dataclasses da camada
`application`; um schema nunca atravessa para dentro.

Três decisões deste módulo valem explicação, porque cada uma parece um detalhe e
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

A conversão de texto para value object (`Email`, `Role.from_string`) **não**
acontece aqui: fica no router, para que a falha seja erro de domínio — e caia no
mapa de status de `error_handlers.py` — em vez de virar um
`RequestValidationError` do FastAPI, que seguiria outro caminho.
"""

from datetime import datetime

from pydantic import BaseModel, Field, SecretStr


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
    proteção do valor, no caminho de volta, é o `SecretStr` do request.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


class CreateRestaurantRequest(BaseModel):
    """Criação de restaurante (o tenant). Só `platform_admin` alcança."""

    name: str


class RestaurantResponse(BaseModel):
    """Restaurante criado."""

    id: str
    name: str


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
    """Provisionamento do `owner` de um restaurante (ação de plataforma).

    Sem campo `role`: o papel é fixado em `Role.OWNER` no código do router. É o
    que garante que **nenhuma rota emite `platform_admin`** — se o papel viesse
    do request, esta seria a rota por onde ele entraria (ADR 2.4.0003 §2b).
    """

    email: str
    password: SecretStr


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
