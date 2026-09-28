"""Identificadores tipados das entidades do BC scheduling.

`NewType` sobre `str`: dá identidade distinta em tempo de type-check (impede
trocar acidentalmente um `ShiftDemandId` por um `AssignmentId`), sem custo de
runtime. São tipos **próprios do BC** — scheduling não importa os tipos de
staff nem de identity (contrato de independência entre BCs no `.importlinter`);
identificadores atravessam a fronteira entre BCs como strings opacas, e cada BC
tipa os seus. Vale em especial para `EmployeeId`/`JobFunctionId`: os **valores**
são emitidos por staff, mas o **tipo** é deste BC (concept §4 Consumidos).

A geração do valor concreto é responsabilidade da application/infra — o domínio
o trata como opaco. A validação de não-vazio é imposta **nas entidades**
(`InvalidIdentifierError`), não aqui: este módulo não tem lógica de runtime.
"""

from typing import NewType

ScheduleId = NewType("ScheduleId", str)
ShiftBandId = NewType("ShiftBandId", str)
ShiftDemandId = NewType("ShiftDemandId", str)
AssignmentId = NewType("AssignmentId", str)
TenantId = NewType("TenantId", str)
UnitId = NewType("UnitId", str)
EmployeeId = NewType("EmployeeId", str)
JobFunctionId = NewType("JobFunctionId", str)
