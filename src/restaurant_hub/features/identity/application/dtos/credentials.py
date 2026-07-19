"""Credencial de acesso — usuário + hash da senha.

A entidade `User` da Stage 2.1 **não** carrega senha, e isso é deliberado: o
domínio modela identidade e acesso, não o mecanismo de autenticação. O hash,
portanto, viaja **ao lado** da entidade, e este registro é o par que o
`UserRepository` devolve numa única ida ao banco — `authenticate_user` precisa
dos dois, e buscá-los em duas chamadas custaria duas queries e abriria janela de
inconsistência.

Carregar a entidade `User` aqui é legítimo e **não** viola LAYOUT §7: este é um
registro interno de port-out, no mesmo nível de `UserRepository.find_by_id() ->
User | None`. A regra "não vaze entidade" governa o **retorno de use case**, que
sempre devolve `UserResult`.
"""

from dataclasses import dataclass

from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.domain.entities.user import User


@dataclass(frozen=True)
class UserCredentials:
    """Usuário e o hash da sua senha, como devolvidos pela persistência."""

    user: User
    password_hash: PasswordHash
