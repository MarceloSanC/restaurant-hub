"""Use case: consultar o fuso de uma unidade.

Nasce na issue #198 para a fachada (ADR 4.1.0005): o fuso é atributo da unidade,
de identity, e scheduling, ponto e hub o leem do dono para converter horário de
parede em instante. O port de leitura de cada consumidor nasce com o primeiro
consumidor; aqui fica só a metade do fornecedor.

**Só leitura.** Uma linha sobre `UnitRepository.find_by_id`.

**O endereço é (tenant, unidade), não só a unidade.** Unidade de outro tenant
responde como inexistente: quem pergunta pelo fuso de uma unidade alheia não
aprende nem que ela existe. É o mesmo endereço com que scheduling guarda as suas
linhas (`tenant_id` e `unit_id`), e fecha de saída a lacuna que o ADR 3.8.0001
registrou para a leitura por id solto.

**Unidade desconhecida devolve `None`, não erro**, como `GetAccountRoleUseCase`:
espelha o `find_by_id`, e quem traduz a ausência para o próprio vocabulário é o
gateway do consumidor, que sabe o que ela significa no seu contrato.

Não autoriza e não recebe ator: só a fachada o chama, e é exclusão nomeada do
inventário do ADR 0.0.0020. Quem chama pela fachada responde pela autorização do
seu lado, antes de perguntar.
"""

from restaurant_hub.features.identity.application.dtos.commands import GetUnitTimezoneCommand
from restaurant_hub.features.identity.application.dtos.results import UnitTimezoneResult
from restaurant_hub.features.identity.application.ports.out.unit_repository import (
    UnitRepository,
)


class GetUnitTimezoneUseCase:
    """Devolve o fuso da unidade do tenant, ou `None` se ela não existe nele."""

    def __init__(self, units: UnitRepository) -> None:
        self._units = units

    def execute(self, command: GetUnitTimezoneCommand) -> UnitTimezoneResult | None:
        """Consulta o fuso; não levanta por unidade desconhecida ou de outro tenant.

        Raises:
            Exception: a falha do repositório sobe como é — devolvê-la como `None`
                faria o consumidor tratar "o banco caiu" como "a unidade não existe".
        """
        unit = self._units.find_by_id(command.unit_id)
        if unit is None or unit.tenant_id != command.tenant_id:
            return None
        return UnitTimezoneResult(timezone=unit.timezone)
