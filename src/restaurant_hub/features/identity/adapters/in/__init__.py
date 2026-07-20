"""Adapters de entrada (driving) do BC identity.

**Atenção — `in` é palavra reservada do Python.** Nenhum módulo abaixo deste
pacote pode ser alcançado por `import` estático:

    # SyntaxError, não ImportError:
    from restaurant_hub.features.identity.adapters.in.http.router import router

O caminho suportado é `importlib.import_module(...)`, usado uma única vez, no
`composition_root`. Não é uma gambiarra para contornar o import-linter: é uma
restrição da linguagem, documentada em `docs/LAYOUT.md` §8, e o diretório se
chama `in` para preservar a nomenclatura canônica de Ports & Adapters.
"""
