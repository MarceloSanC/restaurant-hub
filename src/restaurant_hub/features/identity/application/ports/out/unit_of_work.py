"""Port de saída: a unidade de trabalho de identity (ADR 2.6.0001).

É a fronteira transacional dos use cases que escrevem **mais de uma vez** numa
requisição. Sem ela, cada chamada de repositório é a própria transação, e a falha
da N-ésima escrita deixa as N-1 anteriores gravadas — link de senha queimado com a
senha inalterada, sessão antiga revogada sem a nova, conta nascida sem token.

**Quem abre a unidade é o use case**, e em volta **só** das escritas que precisam
ser atômicas (ADR 2.6.0001 §2): leitura e checagem que decidem se haverá escrita
vêm antes; trabalho de CPU (hash de senha) vem antes, para não alongar a janela de
lock; efeito colateral que não se desfaz (e-mail) vem **depois** do commit — um
rollback não "desenvia" uma mensagem.

**Leis** (fixadas pela suíte de contrato, fake e Postgres):

- **L1 — tudo ou nada.** As escritas de repositório feitas dentro do bloco ficam
  duráveis se ele sai normalmente, e nenhuma fica se ele sai por exceção.
- **L2 — a exceção atravessa intacta.** A unidade não traduz, não embrulha e não
  engole o que saiu do bloco: quem chama recebe o **mesmo** objeto.
- **L3 — chamada que falha não deixa efeito próprio nem envenena a unidade.** As
  escritas anteriores continuam pendentes, e é a saída do bloco que decide o
  destino delas.
- **L4 — leitura dentro do bloco enxerga as escritas do próprio bloco.**
- **L5 — não é reentrante.** Abrir `transaction()` com outra aberta no mesmo
  contexto de execução levanta `RuntimeError` antes de tocar em qualquer coisa.
- **L6 — fora do bloco nada muda.** Cada chamada de repositório continua sendo a
  própria transação, como antes da Stage 2.6.

A unidade é **de identity**. Não atravessa a fachada para outro bounded context
(ADR 2.6.0002 §2): staff escreve no próprio banco na própria transação.
"""

from contextlib import AbstractContextManager
from typing import Protocol


class UnitOfWork(Protocol):
    """Fronteira transacional dos use cases de identity com escrita múltipla."""

    def transaction(self) -> AbstractContextManager[None]:
        """Abre uma unidade: tudo ou nada nas escritas de repositório feitas dentro.

        Uso: `with self._unit_of_work.transaction(): ...` — commit na saída normal,
        rollback na saída por exceção, que sobe intacta (leis L1 a L6 do módulo).

        Raises:
            RuntimeError: já há uma unidade aberta neste contexto de execução (L5).
        """
        ...
