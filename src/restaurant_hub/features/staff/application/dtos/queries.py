"""Queries — a entrada de cada use case de leitura do BC staff.

`frozen` pelo mesmo motivo dos commands. Ambas carregam `tenant_id`; a de
funcionário carrega também `unit_id`, e **isso é o contrato**, não conveniência:
não existe listagem tenant-wide de funcionário nesta camada, e a ausência dela é
o que torna impossível **por assinatura** a consulta que vazaria unidades
(L-E6; workforce §3.1).
"""

from dataclasses import dataclass

from restaurant_hub.features.staff.domain.value_objects.identifiers import TenantId, UnitId


@dataclass(frozen=True)
class ListJobFunctionsQuery:
    """Listagem das funções do restaurante.

    Não tem flag de estado porque **não há estado** a filtrar: a função não tem
    ciclo de vida (ADR 3.2.0005, L-JF5).
    """

    tenant_id: TenantId


@dataclass(frozen=True)
class ListEmployeesQuery:
    """Listagem dos funcionários de **uma** unidade.

    Attributes:
        tenant_id: restaurante dono dos registros.
        unit_id: unidade pedida — obrigatória.
        include_inactive: opt-in explícito. O default esconde os desligados, que
            continuam existindo (endereçáveis por id e contando como referência
            para a guarda de remoção de função) — só somem desta lista.
    """

    tenant_id: TenantId
    unit_id: UnitId
    include_inactive: bool = False
