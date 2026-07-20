"""Testes dos schemas do boundary HTTP — CA17.

O teste central é `test_nenhum_schema_de_resposta_carrega_credencial`: ele não
verifica os schemas que alguém lembrou de listar, e sim **todos** os que existem,
por introspecção. É a diferença entre um teste que protege e um teste que
documenta o passado — um schema de resposta novo entra na varredura sozinho, sem
depender de o autor lembrar deste arquivo.
"""

import importlib

import pytest
from pydantic import BaseModel, SecretStr

pytestmark = pytest.mark.unit

# `in` é keyword Python: import estático deste caminho é SyntaxError (LAYOUT §8).
schemas = importlib.import_module("restaurant_hub.features.identity.adapters.in.http.schemas")

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
