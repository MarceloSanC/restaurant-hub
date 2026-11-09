"""Handlers de erro HTTP globais.

Rede de segurança para a hierarquia de domínio: `DomainError` que nenhum handler de
feature alcançou vira 422. Cada bounded context registra o seu handler, sobre as suas
duas raízes, com o mapa explícito de status — esse é o caminho normal (ADR 3.9.0001).

**Não há rede para `ApplicationError`, de propósito** (ADR 3.9.0001 §5): qualquer
status escolhido aqui estaria errado para algum membro (um lookup como 422, um token
inválido como 404), e responderia em silêncio por um BC que esqueceu de registrar a
raiz. Os gates de `tests/unit/test_status_map.py` tornam esse estado inalcançável no
build. O handler 404 de `NotFoundError` saiu com a classe, na mesma Stage.

Nunca coloque lógica de negócio nos handlers.
"""

from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from restaurant_hub.shared.domain.exceptions.base import DomainError

# Corpo CONSTANTE do 422 de validação (Stage 2.5, concept §5 regra 11).
#
# O handler default do FastAPI serializa o `input` que falhou — isto é, **o corpo
# inteiro da requisição** — de volta ao cliente. Numa rota que recebe credencial
# isso é vazamento direto: `POST /auth/password` com uma senha que falha a
# validação devolveria o **token vivo** no corpo do 422, e o gravaria em qualquer
# log de acesso que registre resposta. O mesmo já valia para as senhas de
# `/auth/login` e `/users` desde a 2.4.
#
# A alternativa "filtrar só os campos sensíveis" foi descartada: exigiria manter
# uma lista de nomes por schema, que erra por omissão exatamente no campo novo
# que ninguém lembrou de listar. Corpo constante não tem esse modo de falha.
#
# O que se perde é a mensagem de qual campo faltou. É um custo real de
# usabilidade de API, e é o preço aceito: o cliente controla o que envia, e
# nenhuma rota deste sistema tem schema complexo o bastante para que a
# adivinhação seja cara.
_VALIDATION_422_BODY: Final = {"detail": "requisição inválida", "type": "validation_error"}


def register_error_handlers(app: FastAPI) -> None:
    """Registra todos os exception handlers na aplicação FastAPI."""

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        """DomainError genérico → 422 Unprocessable Entity."""
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc), "type": "domain_error"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Erro de validação do FastAPI → 422 com corpo **constante**.

        Substitui o handler default, que ecoaria o corpo da requisição — e com
        ele o token de definição de senha — de volta ao cliente. Ver a nota de
        `_VALIDATION_422_BODY`.

        Registrado em `shared` porque vale para a app inteira: a rota que vaza
        credencial hoje é de identity, mas o defeito é do handler default, não da
        feature.
        """
        return JSONResponse(status_code=422, content=_VALIDATION_422_BODY)
