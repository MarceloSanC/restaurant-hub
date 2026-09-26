"""Adapters de entrada (driving) do BC identity.

**O diretório se chamou `in/` até a issue #45.** `in` é palavra reservada do
Python, então nenhum módulo daqui podia ser alcançado por `import` estático —
`from ...adapters.in.http.router import router` é **SyntaxError**, não
ImportError — e o composition root os carregava por `importlib`.

O nome mudou para `inbound/`, que preserva a nomenclatura canônica de Ports &
Adapters sem colidir com a linguagem. O ganho não é de estilo: enquanto os
imports eram dinâmicos, **nenhuma** aresta deste pacote aparecia no grafo do
import-linter, e o contorno da keyword era ele próprio um ponto cego — a mesma
classe de defeito que a #45 existe para fechar.
"""
