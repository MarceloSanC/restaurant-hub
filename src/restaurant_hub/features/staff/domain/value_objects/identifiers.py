"""Identificadores tipados das entidades do BC staff.

`NewType` sobre `str`: dá identidade distinta em tempo de type-check (impede
trocar acidentalmente um `EmployeeId` por um `JobFunctionId`), sem custo de
runtime. São tipos **próprios do BC** — staff não importa os tipos de identity
(contrato de independência entre BCs no `.importlinter`); identificadores
atravessam a fronteira entre BCs como strings opacas, e cada BC tipa os seus.

A geração do valor concreto é responsabilidade da application/infra — o domínio
o trata como opaco. A validação de não-vazio é imposta **nas entidades**
(`InvalidIdentifierError`), não aqui: este módulo não tem lógica de runtime.
"""

from typing import NewType

EmployeeId = NewType("EmployeeId", str)
JobFunctionId = NewType("JobFunctionId", str)
TenantId = NewType("TenantId", str)
UnitId = NewType("UnitId", str)
