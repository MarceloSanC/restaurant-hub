"""Token de definição de senha — o material e o registro persistido.

**Não é um refresh token, e a separação é estrutural** (ADR 2.5.0002). Os dois
são valores opacos guardados por fingerprint, e a semelhança termina aí:

| | refresh token | token de setup |
|---|---|---|
| vida | dias/semanas, renovada a cada rotação | horas, fixa |
| consumo | **rotaciona** (revoga o velho, emite o novo) | **consome** uma vez, e acabou |
| entrega | corpo de resposta HTTPS a cliente autenticado | e-mail, fora de banda |
| portador | quem já se autenticou | quem ainda não se autenticou |

Reusar o mecanismo de sessão aqui seria economia aparente: um `purpose` em
`sessions` faria toda consulta de sessão carregar um discriminador, e o caminho
que esquecesse o filtro trataria um convite como sessão de login.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId


class SetupTokenPurpose(StrEnum):
    """Por que este token foi emitido.

    **Tem trabalho de verdade, não é rótulo.** Na emissão, a invalidação em massa
    é escopada por propósito: pedir uma redefinição de senha mata as redefinições
    anteriores e **não** toca num convite pendente. Sem esse escopo, qualquer
    pessoa na internet mataria o convite de qualquer vítima em laço, pela rota
    pública de redefinição — o link morreria no instante em que a vítima o
    clicasse, indefinidamente.

    Na redenção o escopo some: definir uma senha invalida **todos** os tokens do
    usuário, de qualquer propósito, para que um convite antigo de TTL longo não
    sobreviva e permita redefinir a senha semanas depois (ADR 2.5.0003).
    """

    INVITATION = "invitation"
    PASSWORD_RESET = "password_reset"


@dataclass(frozen=True)
class IssuedSetupToken:
    """Token recém-emitido: o valor que vai no e-mail e o fingerprint que fica.

    Attributes:
        value: valor opaco entregue ao usuário — **nunca** persistido.
        fingerprint: derivação determinística do valor, essa sim persistida.
            Vale a lei do port: `issuer.fingerprint(value) == fingerprint`.
    """

    # `repr=False` pela mesma razão do `refresh_token` dos commands da 2.2: o repr
    # default de uma dataclass imprime o campo inteiro em qualquer traceback com
    # `--showlocals`, captura de locals do Sentry ou log de debug. Aqui o valor é
    # uma credencial bearer viva que, apresentada uma vez, define a senha de uma
    # conta.
    value: str = field(repr=False)
    fingerprint: str


@dataclass(frozen=True)
class PasswordSetupToken:
    """O registro persistido de um token de definição de senha.

    Attributes:
        id: identidade do registro.
        user_id: dono do token — e **a única** origem do usuário alvo na
            redenção (concept §5 regra 10).
        purpose: por que foi emitido.
        token_fingerprint: derivação do valor. O valor não tem coluna.
        issued_at: instante da emissão.
        expires_at: instante em que deixa de valer.
        consumed_at: instante do consumo, ou `None` enquanto nunca foi usado.
    """

    id: SetupTokenId
    user_id: UserId
    purpose: SetupTokenPurpose
    token_fingerprint: str
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    def is_usable(self, now: datetime) -> bool:
        """True se o token ainda pode ser redimido em `now`.

        Intervalo **half-open**, idêntico ao de `Session.is_active`: em
        `now == expires_at` o token **já** expirou. A convenção precisa ser
        explícita porque o instante de fronteira é onde fake e adapter real
        divergem em silêncio — e, aqui, um `<=` no lugar do `<` estenderia a
        validade de um token de recuperação de conta por um instante que ninguém
        escolheu.

        **Isto não é a garantia de uso único.** Um `is_usable` verdadeiro em duas
        requisições simultâneas é perfeitamente possível; quem decide quem venceu
        é `PasswordSetupTokenRepository.consume`, com uma transição condicional
        atômica. Este método é a checagem barata que evita ir ao banco à toa, não
        a trava.
        """
        return self.consumed_at is None and now < self.expires_at
