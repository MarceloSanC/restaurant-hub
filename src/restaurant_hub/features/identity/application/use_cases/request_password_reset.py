"""Use case: pedir a redefinição de senha, sem revelar se o e-mail existe.

**Este use case é definido pelo que ele NÃO faz.** É público, não autentica
ninguém, e recebe um e-mail escolhido por quem chama — de modo que qualquer
diferença observável entre "existe" e "não existe" vira enumeração de contas. Por
isso ele não levanta em nenhum dos dois caminhos, não devolve nada que os
distinga, e absorve a falha do envio.

**A absorção da falha do `EmailSender` é a parte contraintuitiva, e é
indispensável** (concept §5 regra 8). `send` só é chamado quando o e-mail
**existe**; deixar a exceção subir faria **500 significar "cadastrado"** e **202
significar "não cadastrado"**. O atacante nem precisaria medir tempo: bastaria
sondar durante uma indisponibilidade do provedor, ou usar um endereço que o
provedor rejeita, e ler o status. É o oposto do que acontece no convite, onde a
falha propaga — lá quem chama é um ator autenticado que precisa saber que o
e-mail não saiu, e não há nada a enumerar.

**Invalidar as anteriores e gravar a nova é uma unidade de trabalho** (Stage
2.6, ADR 2.6.0001): sem ela, uma falha no `add` deixava as redefinições anteriores
mortas e nenhuma nova. A unidade fica **dentro** do `try` — um rollback é falha
como outra qualquer, e é absorvido pela mesma regra 8 — e o envio sai **depois**
de ela comitar, ainda dentro do `try` (ADR 2.6.0002 §3).

**A invalidação é escopada por `PASSWORD_RESET`**, e não global: um pedido de
redefinição não pode matar um convite pendente, senão qualquer pessoa na internet
mataria o convite de qualquer vítima em laço, por esta mesma rota.

**Oráculo de tempo residual, declarado.** O caminho "existe" grava e envia; o
"não existe" retorna na hora. A diferença é medível, e fechá-la exige envio
assíncrono, que está fora do escopo desta Stage (concept §10 e §13). O que esta
Stage garante é que status, corpo e cabeçalhos são idênticos.

**A falha absorvida vai para o log — só o tipo dela** (issue #26). Absorver é o
que fecha o oráculo; absorver sem registro deixaria o operador sem saber por que
o e-mail de redefinição não chegou. O registro leva o id do usuário e o nome
qualificado da exceção, e nada além: a mensagem e o traceback de uma falha de
provedor podem ecoar o destinatário ou o corpo com o link, e o link é a
credencial.
"""

import logging
from datetime import timedelta

from restaurant_hub.features.identity.application.dtos.commands import (
    RequestPasswordResetCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.ports.out.password_setup_token_repository import (
    PasswordSetupTokenRepository,
)
from restaurant_hub.features.identity.application.ports.out.setup_token_issuer import (
    SetupTokenIssuer,
)
from restaurant_hub.features.identity.application.ports.out.unit_of_work import UnitOfWork
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.features.identity.application.use_cases._invitation import setup_link
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from restaurant_hub.shared.application.ports.out.clock import Clock
from restaurant_hub.shared.application.ports.out.email_sender import (
    EmailMessage,
    EmailSender,
)
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator

_ASSUNTO = "Redefinição de senha do Restaurant Hub"

_log = logging.getLogger(__name__)


class RequestPasswordResetUseCase:
    """Emite e envia um token de redefinição — em silêncio, sempre."""

    def __init__(  # noqa: PLR0913 — grafo de dependências, não parâmetros de chamada
        self,
        users: UserRepository,
        tokens: PasswordSetupTokenRepository,
        token_issuer: SetupTokenIssuer,
        email_sender: EmailSender,
        id_generator: IdGenerator,
        clock: Clock,
        reset_ttl: timedelta,
        base_url: str,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._token_issuer = token_issuer
        self._email_sender = email_sender
        self._id_generator = id_generator
        self._clock = clock
        self._reset_ttl = reset_ttl
        self._base_url = base_url
        self._unit_of_work = unit_of_work

    def execute(self, command: RequestPasswordResetCommand) -> None:
        """Processa o pedido. **Nunca levanta e nunca devolve nada.**

        As duas propriedades são o contrato: um retorno diferente ou uma exceção
        num dos caminhos distinguiria e-mail cadastrado de não cadastrado, que é
        exatamente o que a regra 7 do concept proíbe.
        """
        credenciais = self._users.find_credentials_by_email(command.email)
        if credenciais is None:
            # Silêncio deliberado. Não levanta, não registra, não envia — e o
            # chamador não tem como saber que foi por aqui que passou.
            return

        # **Todo** o caminho "existe" fica dentro do `try`, e não apenas o envio.
        #
        # A regra 8 é sobre o **efeito colateral assimétrico**, não sobre a classe
        # `EmailSender`: emitir e gravar o token também só acontece para e-mail
        # cadastrado. Com a emissão fora daqui, bastava o banco recusar escrita —
        # failover para réplica somente-leitura, disco cheio, deadlock no UPDATE
        # de invalidação, timeout de statement — para o e-mail cadastrado dar 500
        # e o desconhecido dar 202. Enumeração completa pelo status, sem medir
        # tempo nenhum, exatamente o ataque que esta regra existe para fechar.
        try:
            with self._unit_of_work.transaction():
                valor_do_token = self._emitir_token(credenciais.user.id)
            self._enviar(command.email.value, valor_do_token)
        except Exception as exc:
            # Sem `exc_info` e sem `str(exc)`, de propósito — ver o docstring do
            # módulo. O nome da classe separa "provedor fora" de "banco recusou
            # escrita", que é o que o operador precisa para agir.
            classe = type(exc)
            _log.error(
                "redefinição de senha não concluída (falha absorvida): user_id=%s erro=%s",
                credenciais.user.id,
                f"{classe.__module__}.{classe.__qualname__}",
            )
            return

    def _emitir_token(self, user_id: UserId) -> str:
        """Invalida as redefinições anteriores e emite uma nova."""
        agora = self._clock.now()

        # Escopado por propósito: um convite pendente do mesmo usuário sobrevive.
        # Sem o escopo, esta rota pública seria um botão de "matar o convite de
        # qualquer pessoa", acionável em laço por quem soubesse o e-mail dela.
        self._tokens.invalidate_all_for_user(
            user_id, agora, purpose=SetupTokenPurpose.PASSWORD_RESET
        )

        emitido = self._token_issuer.issue()
        self._tokens.add(
            PasswordSetupToken(
                id=SetupTokenId(str(self._id_generator.next_id())),
                user_id=user_id,
                purpose=SetupTokenPurpose.PASSWORD_RESET,
                token_fingerprint=emitido.fingerprint,
                issued_at=agora,
                expires_at=agora + self._reset_ttl,
            )
        )
        return emitido.value

    def _enviar(self, destinatario: str, valor_do_token: str) -> None:
        """Compõe e envia a mensagem.

        **A absorção da falha não acontece aqui**: ela envolve o caminho inteiro,
        em `execute`. Um `try` só em volta do envio deixaria a emissão de fora, e
        um erro de escrita no repositório reabriria o oráculo pelo status —
        cadastrado dá 500, desconhecido dá 202.

        A falha não é silenciada por desprezo ao problema: `execute` a registra
        no log do servidor (issue #26) — só o tipo, nunca a mensagem, porque a
        de um provedor de e-mail pode ecoar o destinatário ou o link.
        """
        link = setup_link(self._base_url, valor_do_token)
        self._email_sender.send(
            EmailMessage(
                to=destinatario,
                subject=_ASSUNTO,
                body_text=(
                    "Recebemos um pedido para redefinir a sua senha.\n\n"
                    f"Defina uma senha nova por este link:\n{link}\n\n"
                    "Se não foi você, ignore esta mensagem."
                ),
            )
        )
