"""Resposta que carrega credencial não fica em cache — issue #61.

**A regra.** Toda resposta de uma rota cujo schema de resposta declara uma
credencial sai com `Cache-Control: no-store` e `Pragma: no-cache`. O OWASP ASVS
5.0 pede o primeiro no req. 14.3.2 ("sufficient anti-caching HTTP response header
fields (i.e., Cache-Control: no-store)"). A RFC 6749 §5.1 exige os dois do
servidor de autorização OAuth em "any response containing tokens, credentials, or
other sensitive information"; esta API não é esse servidor, mas emite o mesmo
tipo de credencial, e a regra vale por analogia. `Pragma: no-cache` é legado de
HTTP/1.0: a RFC 9111 §5.4 o deprecia e lembra que o sentido dele em resposta
nunca foi especificado. Vai porque a RFC 6749 o pede e não custa nada; a proteção
efetiva é o `no-store`, com a ressalva da própria RFC 9111 §5.2.2.5: ele "is not
a reliable or sufficient mechanism for ensuring privacy". Reduz a exposição em
cache de navegador e de intermediário; não substitui TLS nem o TTL curto dos
segredos.

**A marca é do campo, não do nome do schema.** Uma rota declara que o corpo
carrega credencial marcando o **campo** no próprio schema Pydantic com a extensão
de JSON Schema `x-credential: true` — `Field(json_schema_extra={"x-credential":
True})`. A detecção lê o JSON Schema de serialização do `response_model` da rota,
o que alcança modelo aninhado, lista e união. Por isso uma rota nova que devolva
um campo marcado, sob qualquer nome de schema, nasce com os cabeçalhos sem
ninguém editar este módulo. É o caso que a issue nomeia: a rota irmã de R17 que
vai reemitir o link de definição de senha (concept 3.5 §10).

**Por que uma chave de extensão, e não uma classe-marcador importável.** Adapter
de feature não importa `shared.infrastructure` (LAYOUT §3 lista só `application/`
e `domain/`), e `shared/domain` e `shared/application` não podem importar
Pydantic. A chave é contrato declarativo: cada bounded context a escreve no seu
schema, este módulo a lê, e o documento OpenAPI a publica — é uma Specification
Extension, daí o prefixo `x-`. Os testes de cada BC conferem a marca contra
`declares_credential`, para que um erro de digitação não desarme a regra em
silêncio.

**Por que middleware, e não `Depends` por rota.** O concept 2.4 §7.5 recusou
middleware para **autenticação** porque ele exigiria uma allowlist de rotas
públicas, que erra por omissão e abre rota. Aqui não há allowlist: o middleware
age sobre a marca, que mora no campo que cria a necessidade, e acompanha rota
nova sem edição. Uma dependência por rota pediria duas declarações para a mesma
coisa — a marca e o `Depends` —, e o FastAPI descarta os cabeçalhos da
sub-resposta quando o handler devolve um `Response` ou levanta.

**O que fica de fora, declarado.** Um campo de credencial que nasça **sem** a
marca escapa da regra e da varredura do e2e. Não é como esquecer o `Depends` de
autenticação, que a perna 401 do deny-by-default reprova em toda rota não
pública: aqui nenhum gate vê o esquecimento. Nenhuma forma por rota o fecharia —
só `no-store` global, que a issue põe como non-goal. A mitigação é de
proximidade: cada BC declara a marca num alias ao lado do schema que a rota nova
vai copiar.

**A política é da rota, não da resposta.** Os cabeçalhos saem em toda resposta da
rota marcada, 2xx e 4xx tratados, e não só na que traz o segredo. Fica de fora o
500 não tratado, que o `ServerErrorMiddleware` responde por fora deste e que não
carrega credencial. Rota sem marca não é tocada: a política de cache das demais
rotas é non-goal da issue #61.

**De onde vem a rota.** O roteamento do FastAPI grava a `APIRoute` casada em
`scope["route"]` antes de chamar o handler (0.139.0,
`_IncludedRouter._handle_selected`), e o middleware a lê quando a resposta começa.
Rota inexistente chega sem ela, e passa sem cabeçalho.
"""

from functools import cache
from typing import Any, Final

from pydantic import TypeAdapter
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# A chave de extensão que declara um campo de resposta como credencial. É
# contrato: os schemas de identity e de staff a escrevem por extenso, porque não
# importam este módulo (ver o docstring).
CREDENTIAL_MARK: Final = "x-credential"

# Os dois cabeçalhos e os valores exatos da RFC 6749 §5.1. Gravados com
# substituição: um `Cache-Control` que o handler tenha posto perde para este.
_NO_STORE_HEADERS: Final = (("Cache-Control", "no-store"), ("Pragma", "no-cache"))


# `Any` porque o `response_model` do FastAPI é qualquer anotação de tipo, não só
# classe: `list[...]`, união, `Annotated`.
@cache
def declares_credential(response_model: Any) -> bool:  # noqa: ANN401
    """True se o JSON Schema de serialização do modelo marca algum campo como credencial.

    `None` é rota sem schema de resposta (`204`, `Response` cru) e não declara
    nada. O resultado é memoizado por modelo: gerar o JSON Schema a cada resposta
    seria trabalho repetido para uma resposta que não muda enquanto a app vive.
    As formas de `response_model` que o FastAPI aceita são hasheáveis (classe,
    `list[...]`, união, `Annotated`); uma que não fosse levantaria aqui, alto, na
    primeira resposta da rota — e a geração do OpenAPI já teria falhado antes.
    """
    if response_model is None:
        return False
    return _carries_mark(TypeAdapter(response_model).json_schema(mode="serialization"))


def _carries_mark(node: object) -> bool:
    """Procura a marca em qualquer nível do schema, `$defs` incluído.

    A comparação é com `True`, e não com a presença da chave: um campo cujo
    **nome** fosse `x-credential` aparece como chave do dicionário `properties`,
    com um schema como valor, e não pode passar por credencial declarada.
    """
    if isinstance(node, dict):
        return node.get(CREDENTIAL_MARK) is True or any(_carries_mark(v) for v in node.values())
    if isinstance(node, list):
        return any(_carries_mark(item) for item in node)
    return False


def _route_declares_credential(scope: Scope) -> bool:
    route = scope.get("route")
    return declares_credential(getattr(route, "response_model", None))


class CredentialNoStoreMiddleware:
    """Middleware ASGI puro: grava os cabeçalhos de não-cache na rota que declara credencial.

    ASGI puro, e não `BaseHTTPMiddleware`, porque só precisa reescrever a
    mensagem `http.response.start`: não lê o corpo, não o bufferiza e não muda o
    fluxo da requisição.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_policy(message: Message) -> None:
            if message["type"] == "http.response.start" and _route_declares_credential(scope):
                headers = MutableHeaders(scope=message)
                for name, value in _NO_STORE_HEADERS:
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_policy)
