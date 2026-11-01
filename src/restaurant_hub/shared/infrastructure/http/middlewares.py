"""Registro de middlewares FastAPI.

Centraliza a configuração de middlewares para manter create_app() limpo.
Adicione novos middlewares aqui: autenticação, rate limiting, request ID, etc.
A ordem de registro importa: middlewares são executados de baixo para cima
(o último registrado é o primeiro a processar a requisição).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from restaurant_hub.shared.infrastructure.http.credential_no_store import (
    CredentialNoStoreMiddleware,
)


def register_middlewares(app: FastAPI) -> None:
    """Registra todos os middlewares na aplicação FastAPI.

    Configuração atual:
    - CORS: permite todas as origens (ajuste para produção com lista explícita)
    - Sem cache para resposta com credencial: `Cache-Control: no-store` e
      `Pragma: no-cache` em toda rota cujo schema de resposta marca um campo como
      credencial (`credential_no_store.py`, issue #61). A ordem em relação ao CORS
      não importa: os dois só acrescentam cabeçalhos, e nenhum lê os do outro.
    """
    # CORS — em produção, substitua allow_origins=["*"] pela lista de domínios reais
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # FIXME: restringir em produção
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CredentialNoStoreMiddleware)
