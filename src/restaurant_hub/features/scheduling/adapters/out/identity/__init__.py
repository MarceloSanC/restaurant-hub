"""Adapters de saída de scheduling para identity — a aresta scheduling → identity.

Qualquer módulo deste pacote herda a permissão do par nomeado no contrato
`bc-independence` (`scheduling.adapters.out.identity.* -> identity.application.facade`,
ADR 4.5.0003) — e **só** ela: importar qualquer outro módulo de identity a partir daqui
continua reprovando `lint-imports`.
"""
