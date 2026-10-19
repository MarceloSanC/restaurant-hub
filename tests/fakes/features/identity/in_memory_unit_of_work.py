"""Fake in-memory de `UnitOfWork` (ADR 2.6.0001 §4).

Os repositórios em memória não têm transação: cada chamada já é "a própria
transação". O fake dá a eles a mesma história que o Postgres conta — tudo ou nada
no bloco — fotografando o **estado persistido** dos repositórios guardados na
entrada e devolvendo-o na saída por exceção.

Três escolhas deliberadas, cada uma fechando uma forma de o fake mentir:

- **Só o estado persistido volta.** Contadores de chamada, flags e logs de injetor
  de falha **não** são linhas de tabela; se voltassem, o rollback apagaria a prova
  de que a falha disparou na escrita N, e "nada foi gravado" passaria até quando o
  use case falha antes de escrever. A tabela `_ESTADO_PERSISTIDO` declara, por
  classe, quais atributos são estado — e é resolvida pela MRO, para que a
  subclasse injetora de falha herde a declaração da classe-mãe.
- **Repositório sem declaração reprova na construção.** Um fake novo guardado sem
  entrada na tabela seria guardado de mentira; o `TypeError` é o fail-closed.
- **Restauração no lugar.** `dict.clear()` + `update`, `list[:] = …`: uma
  referência ao dict tomada por um teste antes da unidade continua apontando para
  o estado verdadeiro depois do rollback.

A lei L5 (não reentrante) usa uma `ContextVar` de módulo, como o adapter Postgres:
duas instâncias **distintas** aninhadas também levantam, e é isso que torna a lei
testável pela mesma suíte nas duas implementações.
"""

import copy
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from restaurant_hub.features.identity.application.ports.out.unit_of_work import UnitOfWork
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
)
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository

# Classe de repositório em memória → atributos que representam linhas gravadas.
_ESTADO_PERSISTIDO: dict[type, tuple[str, ...]] = {
    InMemoryRestaurantRepository: ("restaurants",),
    InMemoryUnitRepository: ("units",),
    InMemoryUserRepository: ("users", "password_hashes", "memberships", "emails"),
    InMemorySessionRepository: ("sessions",),
    InMemoryPasswordSetupTokenRepository: ("tokens",),
}

_unidade_aberta: ContextVar[bool] = ContextVar("unidade_em_memoria_aberta", default=False)


def _atributos_persistidos(repositorio: object) -> tuple[str, ...]:
    for classe in type(repositorio).__mro__:
        if classe in _ESTADO_PERSISTIDO:
            return _ESTADO_PERSISTIDO[classe]
    raise TypeError(
        f"{type(repositorio).__name__} não declara estado persistido em "
        f"_ESTADO_PERSISTIDO — guardá-lo seria um rollback de mentira."
    )


def _restaurar_no_lugar(atual: object, fotografado: object) -> None:
    if isinstance(atual, dict) and isinstance(fotografado, dict):
        atual.clear()
        atual.update(fotografado)
    elif isinstance(atual, list) and isinstance(fotografado, list):
        atual[:] = fotografado
    else:
        raise TypeError(f"estado persistido de tipo não restaurável: {type(atual).__name__}")


class InMemoryUnitOfWork:
    """Implementação in-memory do port, guardando os repositórios recebidos."""

    def __init__(self, *repositorios: object) -> None:
        self._guardados = [(r, _atributos_persistidos(r)) for r in repositorios]
        # Observáveis para os testes: quantas unidades abriram, comitaram e desfizeram.
        self.aberturas = 0
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if _unidade_aberta.get():
            raise RuntimeError("unidade de trabalho já aberta neste contexto (L5)")

        fotografia = [
            (repositorio, {nome: copy.deepcopy(getattr(repositorio, nome)) for nome in nomes})
            for repositorio, nomes in self._guardados
        ]
        marca = _unidade_aberta.set(True)
        self.aberturas += 1
        try:
            yield
        except BaseException:
            for repositorio, estado in fotografia:
                for nome, valor in estado.items():
                    _restaurar_no_lugar(getattr(repositorio, nome), valor)
            self.rollbacks += 1
            raise
        else:
            self.commits += 1
        finally:
            _unidade_aberta.reset(marca)


_conforms: UnitOfWork = InMemoryUnitOfWork()
