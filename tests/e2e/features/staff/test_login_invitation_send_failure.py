"""Issue #175 — a falha de envio do convite de login de funcionário não vaza nada.

O critério de aceite pelo entrypoint real (`create_app` + Postgres), na rota R17 de
staff — `POST /units/{unit_id}/employees/{employee_id}/login` com
`delivery=email` —, que envia o convite por `LocalIdentityGateway` →
`IdentityFacade.send_invitation` → `SendInvitationUseCase`. É o caminho que a
issue #170 deixou de fora: lá, as três rotas de convite de identity
(`tests/e2e/features/identity/test_invitation_send_failure.py`).

**A propriedade, não um caso.** O sender deste arquivo falha com o pior texto
possível: o destinatário e o corpo inteiro da mensagem — o link, com o token — na
mensagem da exceção. Nada disso pode aparecer no log nem no corpo da resposta.

**O log inclui o do servidor.** Antes da #175 a falha escapava da app e quem a
registrava era o servidor ASGI, com traceback (uvicorn: `logger.error("Exception
in ASGI application\\n", exc_info=exc)`). O `ASGITransport` não tem esse servidor,
então `_postar` faz o papel dele: se a exceção escapar, ela é registrada como o
uvicorn registraria, e o vazamento aparece no `caplog`. Sem isso o teste
observaria só o log da app e passaria verde à toa com o defeito de volta.

**E exige que algo tenha sido registrado.** A ausência do link num log vazio é
verdade vazia: o teste cobra a linha com o `user_id` do login vinculado ao
registro e o nome qualificado da falha.
"""

import logging
from http import HTTPStatus

import pytest
from httpx import AsyncClient, Response

from restaurant_hub.features.identity.application.use_cases import _invitation
from restaurant_hub.shared.application.ports.out.email_sender import EmailMessage
from tests.e2e.features.staff.conftest import API, Cenario, auth
from tests.e2e.features.staff.test_employee_login_flow import _criar_funcionario, _registro
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.e2e

_CONVIDADO = "iara-175@cantina.com"
# O corpo 5xx de identity, escrito por extenso — o oráculo não importa a constante
# que testa.
_CORPO_5XX = {"detail": "erro interno", "type": "internal_error"}
_SERVIDOR = logging.getLogger("uvicorn.error")


class FalhaDeProvedor(Exception):
    """Falha de provedor que ecoa o que recebeu."""


class _CaixaQueEcoaNaFalha(RecordingEmailSender):
    """Entrega normal até `quebrar()`; depois falha ecoando destinatário e corpo.

    Funciona no começo porque o cenário provisiona o dono, e o convite dele também
    é um e-mail (ADR 0.0.0018). Guarda as mensagens que **tentou** enviar depois de
    quebrada: é delas que o teste tira o link e o token que não podem aparecer.
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


async def test_falha_de_envio_no_r17_nao_leva_destinatario_nem_link_ao_log_nem_a_resposta(
    client: AsyncClient,
    cenario: Cenario,
    caixa_de_entrada: _CaixaQueEcoaNaFalha,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Iara")
    url = f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/login"
    pedido = {"email": _CONVIDADO, "delivery": "email"}
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    caixa_de_entrada.quebrar()

    resposta = await _postar(client, url, pedido, cabecalho)

    # O que não pode vazar: o destinatário, o link inteiro e o token sozinho.
    [tentativa] = caixa_de_entrada.tentativas
    assert tentativa.to == _CONVIDADO
    link = next(linha for linha in tentativa.body_text.splitlines() if "token=" in linha)
    token = link.partition("token=")[2]
    assert token
    segredos = (_CONVIDADO, link, token)

    for segredo in segredos:
        assert segredo not in caplog.text, f"{segredo!r} no log"

    # Algo foi registrado — e é o id do login que ficou vinculado ao registro.
    registro = await _registro(client, cabecalho, cenario.unidade_a, employee_id)
    user_id = registro["user_id"]
    assert user_id is not None
    [linha] = [r for r in caplog.records if r.name == _invitation.__name__]
    assert linha.levelno == logging.ERROR
    assert linha.exc_info is None
    assert linha.args == (user_id, f"{__name__}.FalhaDeProvedor")

    # A resposta: 5xx, corpo constante, nada do envio.
    assert resposta is not None, "a falha escapou da app até o servidor"
    assert resposta.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert resposta.json() == _CORPO_5XX
    for segredo in segredos:
        assert segredo not in resposta.text

    # CA30 continua: o vínculo ficou, e um segundo R17 responde 409.
    segundo = await client.post(url, json=pedido, headers=cabecalho)
    assert segundo.status_code == HTTPStatus.CONFLICT
