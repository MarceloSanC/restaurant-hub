"""Pacote shared — preocupações transversais reutilizáveis entre features.

Contém código genuinamente compartilhado: exceções base, ports compartilhados
(Clock, IdGenerator, EmailSender) e infraestrutura (config, banco, HTTP).
Regra: shared nunca importa de features/ — o fluxo de dependência é sempre
features → shared, nunca o contrário.
"""
