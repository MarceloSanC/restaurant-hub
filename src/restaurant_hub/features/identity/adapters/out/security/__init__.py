"""Adapters de saída de segurança do BC identity.

Aqui vive **toda** a criptografia do bounded context: o hash de senha
(`argon2_hasher`) e a emissão/verificação de token (`jwt_issuer`). A camada de
aplicação não hasheia, não assina e não gera segredo — ela conhece apenas os
ports `PasswordHasher` e `TokenIssuer`.

Concentrar assim é o que torna a troca de algoritmo uma mudança de um arquivo, e
o que impede que um parâmetro de custo ou um segredo apareça no meio de um use
case. ADR 2.4.0004.
"""
