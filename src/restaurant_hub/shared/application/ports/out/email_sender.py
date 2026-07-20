"""Port compartilhado: envio de e-mail.

**Mora em `shared/` e não na feature que o estreou** (ADR 2.5.0001). A regra
prática do LAYOUT §4 — "em caso de dúvida, comece na feature; mova quando a
segunda precisar" — existe contra abstração **prematura**, e prematuro é o que
não tem segundo consumidor identificado. Aqui ele tem nome e Stage: a `4.6`
(notificação de publicação de escala) já declara `EmailSender (2.5)` em
`contratos_consumidos`.

**O teste que autorizou a promoção:** conseguir descrever a assinatura sem dizer
"convite". Destinatário, assunto e corpo — nada sobre token, usuário ou tenant.

**E a restrição de camada é o que a mantém honesta.** `shared/application` não
pode importar de `features/` (LAYOUT §3, contrato `shared-independence` do
import-linter), então `to` é `str` e **não tem como** virar o value object `Email`
do BC identity. Quem converte é o chamador, com `email.value`. Essa linha a mais
no use case é o preço visível da genericidade, e é barato.

**Síncrono, e pode levantar** (ADR 2.2.0004 vale para todos os ports do projeto).
Quem chama decide o que fazer com a falha, e os dois chamadores desta Stage
decidem coisas opostas de propósito: o convite deixa propagar (quem convidou
precisa saber que o e-mail não saiu), o pedido de redefinição de senha absorve
(deixar propagar faria "500" significar "este e-mail está cadastrado" — concept
§5 regra 8).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    """Uma mensagem de e-mail pronta para envio.

    Attributes:
        to: endereço do destinatário, já normalizado por quem chama.
        subject: assunto.
        body_text: corpo em texto puro. Não há variante HTML nesta Stage — o
            roadmap declara "templates elaborados" como non-goal, e acrescentar
            um campo depois é aditivo.
    """

    to: str
    subject: str
    body_text: str


class EmailSender(Protocol):
    """Contrato de envio de uma mensagem de e-mail."""

    def send(self, message: EmailMessage) -> None:
        """Envia a mensagem.

        Levanta se o envio falhar — o port não engole erro por conta própria. A
        exceção concreta é do adapter; quem chama trata pelo efeito, não pelo tipo.
        """
        ...
