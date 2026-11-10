"""Issue #170 — a falha de envio do convite não leva destinatário nem link ao log.

O critério de aceite, pelo entrypoint real (`create_app` + Postgres), nas **três**
rotas que convidam depois de comitar a conta: `POST /restaurants`,
`POST /restaurants/{id}/owners` e `POST /users/invitations`.

**A propriedade, não um caso.** O sender deste arquivo falha com o pior texto
possível: o destinatário e o corpo inteiro da mensagem — o link, com o token —
na mensagem da exceção. Um provedor real (Resend, Stage 6.2) pode fazer
exatamente isso. Nada dele pode aparecer no log nem no corpo da resposta.

**O log inclui o do servidor.** Antes da #170 a falha escapava da app e quem a
registrava era o servidor ASGI, com traceback (uvicorn: `logger.error("Exception
in ASGI application\\n", exc_info=exc)`). O `ASGITransport` não tem esse servidor,
então `_postar` faz o papel dele: se a exceção escapar, ela é registrada como o
uvicorn registraria, e o vazamento aparece no `caplog`. Sem isso o teste
observaria só o log da app e passaria verde à toa com o defeito de volta.

**E exige que algo tenha sido registrado.** A ausência do link num log vazio é
verdade vazia: cada caso cobra a linha com o `user_id` da conta criada e o nome
qualificado da falha.
"""

import logging
from http import HTTPStatus

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import Engine, text

from restaurant_hub.features.identity.application.use_cases import _invitation
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.shared.application.ports.out.email_sender import EmailMessage
from tests.e2e.features.identity.conftest import (
    API,
    auth,
    corpo_tenant,
    fazer_login,
    login_do_dono,
)
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.e2e

_ROTAS = ("provisionamento", "dono-de-restaurante", "convite-de-usuario")
_CONVIDADO = "convidado-170@x.com"
# O corpo 5xx, escrito por extenso — o oráculo não importa a constante que testa.
_CORPO_5XX = {"detail": "erro interno", "type": "internal_error"}
_SERVIDOR = logging.getLogger("uvicorn.error")


class FalhaDeProvedor(Exception):
    """Falha de provedor que ecoa o que recebeu."""


class _CaixaQueEcoaNaFalha(RecordingEmailSender):
    """Entrega normal até `quebrar()`; depois falha ecoando destinatário e corpo.

    Guarda as mensagens que **tentou** enviar: é delas que o teste tira o link e o
    token que não podem aparecer em lugar nenhum.
    """

    def __init__(self) -> None:
        super().__init__()
        self.quebrada = False
        self.tentativas: list[EmailMessage] = []

    def quebrar(self) -> None:
        self.quebrada = True

    def send(self, message: EmailMessage) -> None:
        if not self.quebrada:
            super().send(message)
            return
        self.tentativas.append(message)
        raise FalhaDeProvedor(f"recusado para {message.to}: {message.body_text}")


@pytest.fixture
def caixa_de_entrada() -> _CaixaQueEcoaNaFalha:
    """Substitui a caixa do conftest — `app_e2e` a injeta no `create_app`."""
    return _CaixaQueEcoaNaFalha()


async def _postar(client: AsyncClient, url: str, corpo: dict, cabecalho: dict) -> Response | None:
    """POST que, se a exceção escapar da app, a registra como o servidor faria."""
    try:
        return await client.post(url, json=corpo, headers=cabecalho)
    except Exception as exc:  # o que o servidor ASGI faz com o que escapa
        _SERVIDOR.error("Exception in ASGI application\n", exc_info=exc)
        return None


async def _convidar_com_a_caixa_quebrada(
    client: AsyncClient, caixa: _CaixaQueEcoaNaFalha, admin: dict, rota: str
) -> Response | None:
    """Monta o cenário da rota com a caixa funcionando, quebra a caixa e convida."""
    if rota == "provisionamento":
        caixa.quebrar()
        return await _postar(
            client, f"{API}/restaurants", corpo_tenant("Cantina", _CONVIDADO), auth(admin)
        )

    restaurante = (
        await client.post(
            f"{API}/restaurants",
            json=corpo_tenant("Cantina", "primeiro-dono@x.com"),
            headers=auth(admin),
        )
    ).json()["id"]
    if rota == "dono-de-restaurante":
        caixa.quebrar()
        return await _postar(
            client, f"{API}/restaurants/{restaurante}/owners", {"email": _CONVIDADO}, auth(admin)
        )

    dono = await login_do_dono(client, caixa, "primeiro-dono@x.com")
    caixa.quebrar()
    return await _postar(
        client,
        f"{API}/users/invitations",
        {"email": _CONVIDADO, "role": "manager", "unit_ids": []},
        auth(dono),
    )


@pytest.mark.parametrize("rota", _ROTAS)
async def test_falha_de_envio_nao_leva_destinatario_nem_link_ao_log_nem_a_resposta(  # noqa: PLR0913 — fixtures do cenário, o log e o eixo da rota
    client: AsyncClient,
    admin_semeado: User,
    caixa_de_entrada: _CaixaQueEcoaNaFalha,
    engine: Engine,
    caplog: pytest.LogCaptureFixture,
    rota: str,
) -> None:
    admin = await fazer_login(client, admin_semeado.email.value)
    caplog.clear()
    caplog.set_level(logging.DEBUG)

    resposta = await _convidar_com_a_caixa_quebrada(client, caixa_de_entrada, admin, rota)

    # O que não pode vazar: o destinatário, o link inteiro e o token sozinho.
    [tentativa] = caixa_de_entrada.tentativas
    assert tentativa.to == _CONVIDADO
    link = next(linha for linha in tentativa.body_text.splitlines() if "token=" in linha)
    token = link.partition("token=")[2]
    assert token
    segredos = (_CONVIDADO, link, token)

    for segredo in segredos:
        assert segredo not in caplog.text, f"{rota}: {segredo!r} no log"

    # A conta ficou comitada (regra 13 da 2.5) — e é o id dela que o log leva.
    with engine.connect() as conexao:
        user_id = conexao.execute(
            text("SELECT id FROM users WHERE email = :e"), {"e": _CONVIDADO}
        ).scalar_one()
        tokens = conexao.execute(
            text("SELECT count(*) FROM password_setup_tokens WHERE user_id = :u"), {"u": user_id}
        ).scalar_one()
    assert tokens == 1
    [registro] = [r for r in caplog.records if r.name == _invitation.__name__]
    assert registro.levelno == logging.ERROR
    assert registro.args == (user_id, f"{__name__}.FalhaDeProvedor")

    # A resposta: 5xx, corpo constante, nada do envio.
    assert resposta is not None, f"{rota}: a falha escapou da app até o servidor"
    assert resposta.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert resposta.json() == _CORPO_5XX
    for segredo in segredos:
        assert segredo not in resposta.text
