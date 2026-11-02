"""Entrypoint da aplicação — inicia o servidor HTTP.

Este módulo é o ponto de entrada ASGI. Ele cria a instância do FastAPI via
`create_app()` (definida em shared/infrastructure/http/app.py) e a expõe como
`app` para que uvicorn possa encontrá-la. Em produção, nunca importe este módulo
diretamente — use `uvicorn restaurant_hub.main:app`.
"""

import uvicorn

from restaurant_hub.shared.infrastructure.http.app import create_app

app = create_app()

if __name__ == "__main__":
    # Execução direta para debug local: python -m restaurant_hub.main
    # Em produção, prefira: uvicorn restaurant_hub.main:app --workers 4
    #
    # Entrega ao uvicorn a app já montada, e não a string de import. Aqui este
    # arquivo roda como `__main__`, que para o import é outro módulo; com a string,
    # o uvicorn importaria `restaurant_hub.main` de novo e o boot inteiro (logging e
    # wiring) aconteceria duas vezes no mesmo processo, como a issue #6 mediu.
    # Reload e workers exigem a string: para eles, use o comando do uvicorn acima.
    uvicorn.run(app, host="0.0.0.0", port=8000)
