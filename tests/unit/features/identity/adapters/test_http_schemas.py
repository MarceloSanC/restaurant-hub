"""Testes dos schemas do boundary HTTP — CA17.

O teste central é `test_nenhum_schema_de_resposta_carrega_credencial`: ele não
verifica os schemas que alguém lembrou de listar, e sim **todos** os que existem,
por introspecção. É a diferença entre um teste que protege e um teste que
documenta o passado — um schema de resposta novo entra na varredura sozinho, sem
depender de o autor lembrar deste arquivo.
"""

import pytest
from pydantic import BaseModel, SecretStr

from restaurant_hub.features.identity.adapters.inbound.http import schemas
from restaurant_hub.shared.infrastructure.http.credential_no_store import (
    CREDENTIAL_MARK,
    declares_credential,
)

pytestmark = pytest.mark.unit

# Nomes que jamais podem sair numa resposta. `fingerprint` está aqui junto com
# senha e hash porque, embora não seja utilizável como credencial, é o índice que
# localiza a sessão — e o ADR 2.2.0001 desenhou o sistema para que ele nunca
# precisasse sair do servidor.
_NOMES_PROIBIDOS_EM_RESPOSTA = (
    "password",
    "senha",
    "hash",
    "password_hash",
    "fingerprint",
    "secret",
)

# Piso contra o teste virar vácuo se os schemas forem reorganizados ou o módulo
# renomeado: sem ele, uma varredura que não encontrasse schema nenhum passaria.
_TOTAL_DE_SCHEMAS_DE_RESPOSTA = 4


def _schemas_do_modulo() -> list[type[BaseModel]]:
    return [
        obj
        for nome, obj in vars(schemas).items()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj is not BaseModel
        and not nome.startswith("_")
    ]


def _schemas_de_resposta() -> list[type[BaseModel]]:
    return [cls for cls in _schemas_do_modulo() if cls.__name__.endswith("Response")]


def test_a_varredura_de_respostas_nao_esta_vazia() -> None:
    """Guarda do guarda: uma varredura vazia passaria em todos os testes abaixo."""
    assert len(_schemas_de_resposta()) == _TOTAL_DE_SCHEMAS_DE_RESPOSTA


def test_nenhum_schema_de_resposta_carrega_credencial() -> None:
    """CA17 — varredura por introspecção, não por lista mantida à mão.

    `UserResult` sequer carrega o hash, então hoje não há de onde vazar; este
    teste existe para o dia em que alguém adicionar um campo "conveniente" a um
    response e ninguém reler o concept.
    """
    for schema in _schemas_de_resposta():
        for campo in schema.model_fields:
            for proibido in _NOMES_PROIBIDOS_EM_RESPOSTA:
                assert proibido not in campo.lower(), (
                    f"{schema.__name__}.{campo} parece material de credencial"
                )


@pytest.mark.parametrize(
    ("schema_nome", "campo"),
    [
        ("LoginRequest", "password"),
        ("RefreshRequest", "refresh_token"),
        ("LogoutRequest", "refresh_token"),
        ("CreateUserRequest", "password"),
        ("CreateOwnerRequest", "password"),
    ],
)
def test_credencial_em_request_e_secret_str(schema_nome: str, campo: str) -> None:
    """Todo campo de credencial em request é `SecretStr`.

    Não é preciosismo de tipo: é o que faz o `repr` do modelo sair como
    `**********` em traceback com `--showlocals`, captura de locals de APM e log
    de debug. A senha em claro só deve existir dentro do `PasswordHasher`.
    """
    schema = getattr(schemas, schema_nome)

    assert schema.model_fields[campo].annotation is SecretStr


def test_repr_de_request_nao_revela_a_senha() -> None:
    """A propriedade observável do `SecretStr` — testada, não presumida."""
    request = schemas.LoginRequest(email="a@b.com", password=SecretStr("s3nha-real"))

    assert "s3nha-real" not in repr(request)
    assert "s3nha-real" not in str(request)
    # E o valor continua recuperável por quem tem o direito de usá-lo.
    assert request.password.get_secret_value() == "s3nha-real"


def test_repr_de_refresh_request_nao_revela_o_token() -> None:
    request = schemas.RefreshRequest(refresh_token=SecretStr("refresh-vivo"))

    assert "refresh-vivo" not in repr(request)


def test_create_user_request_nao_aceita_tenant_id() -> None:
    """A ausência do campo é a defesa (concept §5 regra 3).

    O tenant do usuário criado vem do ator. Se o schema tivesse `tenant_id`,
    alguém acabaria por lê-lo, e o corpo do POST viraria vetor de escalada entre
    tenants.
    """
    assert "tenant_id" not in schemas.CreateUserRequest.model_fields


def test_create_owner_request_nao_aceita_role() -> None:
    """O papel é literal no router — é o que impede uma rota de emitir platform_admin."""
    assert "role" not in schemas.CreateOwnerRequest.model_fields


def test_dono_convidado_no_provisionamento_so_tem_o_email() -> None:
    """ADR 0.0.0018 — a senha do dono não transita pela API de plataforma.

    Conjunto **exato**: um campo `password` (ou `role`) que voltasse ao schema
    reprova aqui, antes de qualquer rota o ler.
    """
    assert set(schemas.InviteOwnerRequest.model_fields) == {"email"}
    assert schemas.ProvisionRestaurantRequest.model_fields["owner"].annotation is (
        schemas.InviteOwnerRequest
    )


def test_campo_extra_no_corpo_e_ignorado_e_nao_rejeitado() -> None:
    """Política de `extra` fixada de propósito (Task 07 do technical).

    Endurecer para `extra="forbid"` parece a escolha segura e aqui seria pior: a
    requisição que tenta injetar `tenant_id` receberia 422 em vez de ser
    silenciosamente desarmada, e CA13 — que prova que o valor enviado é
    descartado — deixaria de poder observar a defesa funcionando.
    """
    request = schemas.CreateUserRequest(
        email="novo@restaurante.com",
        password=SecretStr("s3nha"),
        role="manager",
        tenant_id="tenant-de-outro-restaurante",
    )

    assert not hasattr(request, "tenant_id")


def test_token_response_expoe_o_refresh_em_claro_por_necessidade() -> None:
    """O refresh de RESPOSTA é `str`, não `SecretStr` — e a razão é funcional.

    Ele é a resposta ao cliente; um `SecretStr` serializaria como `**********` e
    o cliente nunca receberia o token. A proteção do valor está no caminho de
    volta, onde `RefreshRequest` o recebe como `SecretStr`.
    """
    assert schemas.TokenResponse.model_fields["refresh_token"].annotation is str


def _campos_marcados_como_credencial(schema: type[BaseModel]) -> set[str]:
    """Os campos de topo cujo JSON Schema de serialização traz a marca."""
    propriedades = schema.model_json_schema(mode="serialization")["properties"]
    return {nome for nome, valor in propriedades.items() if valor.get(CREDENTIAL_MARK) is True}


def test_token_response_declara_os_dois_tokens_como_credencial() -> None:
    """Issue #61: é a marca que tira do cache as respostas de login e de refresh.

    Duas asserções, porque falham por motivos diferentes. A primeira cruza a
    chave escrita por extenso no schema com o detector de `shared`: um erro de
    digitação na chave desarmaria a regra sem mais nenhum sintoma. A segunda fixa
    **quais** campos: `token_type` e os instantes de expiração não são segredo, e
    marcá-los diria no OpenAPI uma coisa falsa.
    """
    assert declares_credential(schemas.TokenResponse) is True
    assert _campos_marcados_como_credencial(schemas.TokenResponse) == {
        "access_token",
        "refresh_token",
    }


@pytest.mark.parametrize(
    "schema",
    [schemas.UserResponse, schemas.ProvisionedRestaurantResponse, schemas.UnitResponse],
    ids=lambda schema: schema.__name__,
)
def test_resposta_sem_credencial_nao_e_declarada_credencial(schema: type[BaseModel]) -> None:
    """O non-goal da issue #61, nos schemas de hoje: dado de cadastro não é credencial.

    Marcar `UserResponse.email`, por exemplo, poria `no-store` em três rotas de
    identity e faria o OpenAPI declarar como credencial o que não é. A lista
    nomeia os schemas existentes de propósito, em vez de varrer o módulo: uma
    varredura "só `TokenResponse` é marcado" obrigaria a editar este teste a cada
    schema novo que carregasse credencial — e esse schema tem de nascer com os
    cabeçalhos sem edição (nota 4 de `schemas.py`).
    """
    assert declares_credential(schema) is False
