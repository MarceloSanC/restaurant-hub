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

# O id do **login** em identity, opaco para staff e tipado por staff — a mesma
# regra de `TenantId`/`UnitId`: o valor vem de fora e atravessa a fronteira como
# string; o tipo é nosso. A semântica **não** restringe o papel do `User`
# apontado: hoje o único produtor (R17, Stage 3.5) cria contas `employee`, mas um
# vínculo futuro a um login de gerente que também trabalha na escala é legítimo
# (workforce §3.3(b), §3.7; concept 3.5 §4).
UserId = NewType("UserId", str)
