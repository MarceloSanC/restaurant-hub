"""Identificadores tipados das entidades do BC identity.

`NewType` sobre `str`: dá identidade distinta em tempo de type-check (impede
trocar acidentalmente um `RestaurantId` por um `UnitId`), sem custo de runtime.
A geração do valor concreto é responsabilidade da application/infra — o domínio
trata o id como opaco. `tenant_id` no domínio é sempre um `RestaurantId` (um
restaurante É o seu tenant; ver ADR 2.1.0001).
"""

from typing import NewType

RestaurantId = NewType("RestaurantId", str)
UnitId = NewType("UnitId", str)
UserId = NewType("UserId", str)
