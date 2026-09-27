"""Adapters de saída de staff para identity — a única aresta entre os dois BCs.

Qualquer módulo deste pacote herda a permissão do par nomeado no contrato
`bc-independence` (`staff.adapters.out.identity.* -> identity.application.facade`,
ADR 3.5.0001 §3) — e **só** ela: importar qualquer outro módulo de identity a
partir daqui continua reprovando `lint-imports`.
"""
