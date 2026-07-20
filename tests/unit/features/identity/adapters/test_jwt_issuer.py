"""Testes do adapter JWT contra as leis do port `TokenIssuer`.

Dois grupos, com pesos diferentes:

- **Round-trip de claims** — que o token emitido volte igual. É o mínimo.
- **Recusa** — que assinatura adulterada, segredo errado, algoritmo trocado e
  expiração sejam recusados. É onde mora a segurança, e é o que um teste de
  "emitir e decodificar funciona" nunca exercita.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from restaurant_hub.features.identity.adapters.out.security.jwt_issuer import (
    JwtTokenIssuer,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import InvalidAccessTokenError
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role

pytestmark = pytest.mark.unit

# >= 32 bytes (RFC 7518 §3.2): abaixo disso o PyJWT emite
# InsecureKeyLengthWarning, e um teste que convive com o aviso ensina a ignorá-lo.
_SEGREDO = "segredo-de-teste-com-32-bytes-ou-mais"
_FUTURO = datetime.now(UTC) + timedelta(minutes=15)
_TENANT_PADRAO = RestaurantId("rest-1")
_AMOSTRA_DE_REFRESH = 10


def _claims(
    *,
    role: Role = Role.OWNER,
    tenant_id: RestaurantId | None = _TENANT_PADRAO,
    expires_at: datetime | None = None,
) -> AccessTokenClaims:
    return AccessTokenClaims(
        subject=UserId("user-1"),
        role=role,
        tenant_id=tenant_id,
        session_id=SessionId("sess-1"),
        expires_at=expires_at or _FUTURO,
    )


def _issuer() -> JwtTokenIssuer:
    return JwtTokenIssuer(secret_key=_SEGREDO)


def test_adapter_satisfaz_o_protocolo() -> None:
    """Conformidade estrutural com o port (declarada no teste, não no módulo)."""
    issuer: TokenIssuer = _issuer()

    assert issuer.fingerprint("x") == _issuer().fingerprint("x")


def test_round_trip_preserva_todas_as_claims() -> None:
    issuer = _issuer()
    claims = _claims()

    decodificado = issuer.decode_access_token(issuer.issue_access_token(claims))

    assert decodificado.subject == claims.subject
    assert decodificado.role is claims.role
    assert decodificado.tenant_id == claims.tenant_id
    assert decodificado.session_id == claims.session_id
    # `exp` do JWT tem resolução de segundo — comparar o instante truncado.
    assert decodificado.expires_at == claims.expires_at.replace(microsecond=0)


def test_round_trip_preserva_tenant_nulo_de_platform_admin() -> None:
    """`None` é o tenant legítimo do `platform_admin`, não dado ausente.

    Colapsá-lo numa string vazia faria `User.__post_init__` levantar
    `MissingTenantError` do outro lado — e o erro apareceria longe daqui.
    """
    issuer = _issuer()
    token = issuer.issue_access_token(_claims(role=Role.PLATFORM_ADMIN, tenant_id=None))

    assert issuer.decode_access_token(token).tenant_id is None


def test_recusa_token_com_assinatura_adulterada() -> None:
    issuer = _issuer()
    token = issuer.issue_access_token(_claims())
    adulterado = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")

    with pytest.raises(InvalidAccessTokenError):
        issuer.decode_access_token(adulterado)


def test_recusa_token_assinado_com_outro_segredo() -> None:
    """O caso do atacante que forja um token com estrutura perfeita."""
    forjado = JwtTokenIssuer(secret_key="outro-segredo-com-32-bytes-ou-mais!!").issue_access_token(
        _claims()
    )

    with pytest.raises(InvalidAccessTokenError):
        _issuer().decode_access_token(forjado)


def test_recusa_token_expirado() -> None:
    issuer = _issuer()
    token = issuer.issue_access_token(_claims(expires_at=datetime.now(UTC) - timedelta(seconds=1)))

    with pytest.raises(InvalidAccessTokenError):
        issuer.decode_access_token(token)


def test_recusa_token_com_algoritmo_none() -> None:
    """Confusão de algoritmo — o ataque que a allowlist `algorithms=[...]` fecha.

    O atacante monta um token sem assinatura declarando `alg: none`. Se o decode
    aceitasse o algoritmo declarado no cabeçalho do próprio token, quem escolhe a
    verificação passaria a ser o portador (RFC 8725 §3.1).
    """
    sem_assinatura = jwt.encode({"sub": "user-1"}, key="", algorithm="none")

    with pytest.raises(InvalidAccessTokenError):
        _issuer().decode_access_token(sem_assinatura)


def test_recusa_token_assinado_com_outro_algoritmo() -> None:
    """Token válido, segredo certo, algoritmo fora da allowlist."""
    token = jwt.encode(
        {"sub": "user-1", "role": "owner", "tenant_id": "r", "sid": "s", "exp": _FUTURO},
        _SEGREDO,
        algorithm="HS512",
    )

    with pytest.raises(InvalidAccessTokenError):
        _issuer().decode_access_token(token)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"sub": "u"}, id="claims-faltando"),
        pytest.param(
            {"sub": "u", "role": "papel-inexistente", "tenant_id": None, "sid": "s"},
            id="papel-desconhecido",
        ),
    ],
)
def test_recusa_token_bem_assinado_com_payload_de_forma_errada(
    payload: dict[str, object],
) -> None:
    """Assinatura válida não basta — a forma do payload também é verificada.

    Cenário real numa troca de formato de claims, quando tokens do formato antigo
    ainda circulam. Sem esta captura, um `KeyError` viraria 500 em vez de 401.
    """
    token = jwt.encode({**payload, "exp": _FUTURO}, _SEGREDO, algorithm="HS256")

    with pytest.raises(InvalidAccessTokenError):
        _issuer().decode_access_token(token)


def test_recusa_lixo_que_nem_e_jwt() -> None:
    with pytest.raises(InvalidAccessTokenError):
        _issuer().decode_access_token("isto-nao-e-um-token")


def test_lei_do_port_fingerprint_do_valor_emitido_bate() -> None:
    """`issuer.fingerprint(t.value) == t.fingerprint`.

    Asserida via `fingerprint(...)` e não por igualdade de campo: é a formulação
    que pega o adapter que derivasse o fingerprint de um jeito na emissão e de
    outro na consulta — caso em que toda busca de sessão falharia.
    """
    issuer = _issuer()
    emitido = issuer.issue_refresh_token()

    assert issuer.fingerprint(emitido.value) == emitido.fingerprint


def test_refresh_tokens_emitidos_sao_distintos() -> None:
    issuer = _issuer()

    valores = {issuer.issue_refresh_token().value for _ in range(_AMOSTRA_DE_REFRESH)}

    assert len(valores) == _AMOSTRA_DE_REFRESH


def test_fingerprint_e_deterministico_e_nao_reversivel_por_inspecao() -> None:
    """Determinístico porque `find_by_fingerprint` busca por valor exato."""
    issuer = _issuer()

    assert issuer.fingerprint("abc") == issuer.fingerprint("abc")
    assert issuer.fingerprint("abc") != issuer.fingerprint("abd")
    # O valor não aparece dentro do fingerprint — é o que torna um dump do banco
    # inútil para quem quer um refresh token (ADR 2.2.0001).
    assert "abc" not in issuer.fingerprint("abc")


def test_fingerprint_tem_o_tamanho_de_um_sha256_hex() -> None:
    """64 hex chars — cabe na coluna `Text` da tabela `sessions` da 2.3."""
    esperado = 64

    assert len(_issuer().fingerprint("qualquer-coisa")) == esperado
