"""Wiring dos repositórios e dos 16 use cases de staff no composition root — CA18.

Espelho de `test_composition_root_identity.py`, e o espelho é deliberado: a regra
que ele guarda ("só o composition root instancia adapter") é a mesma, e o BC
staff acabou de ganhar o seu primeiro pacote de adapters de saída.

**Os 16 use cases nascem sem consumidor**, e é por isso que estes testes têm de
ser mais do que "o campo existe". Não há adapter de entrada de staff até a
Stage 3.4: nenhum request, nenhum e2e e nenhum teste de integração passa por
`wire_dependencies()` para staff. Se o wiring estiver errado — um repositório
trocado, um fake no lugar do adapter, um use case montado com o repositório do
outro agregado — **nada mais no repositório reclama**. Este arquivo é o único
lugar onde esse erro é visível antes da 3.4.

Por isso as asserções são sobre **o que foi injetado**, não sobre o tipo do use
case: `isinstance(deps.staff_create_employee, CreateEmployeeUseCase)` é
verdadeiro por construção do `dataclass` e não prova nada que o type-checker já
não provasse.
"""

import ast
import pathlib

import pytest

from restaurant_hub.composition_root import ApplicationDependencies, wire_dependencies
from restaurant_hub.features.staff.adapters.out.postgres.employee_repository import (
    PostgresEmployeeRepository,
)
from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from restaurant_hub.shared.infrastructure.config.settings import Settings

pytestmark = pytest.mark.unit

_SRC = pathlib.Path(__file__).resolve().parents[5] / "src" / "restaurant_hub"
_PACOTE_DE_ADAPTERS = _SRC / "features" / "staff" / "adapters"
_MODULO_DE_ADAPTERS = "restaurant_hub.features.staff.adapters"
_COMPOSITION_ROOT = _SRC / "composition_root.py"

# Os 16 de `features/staff/application/use_cases/`, na forma como o contêiner os
# expõe. A lista é **explícita** e não derivada por varredura de pasta de
# propósito: derivada, ela se ajustaria sozinha a um use case que alguém
# esquecesse de wirar, e o teste passaria a confirmar o esquecimento.
_USE_CASES_DE_STAFF = (
    "staff_create_job_function",
    "staff_rename_job_function",
    "staff_delete_job_function",
    "staff_list_job_functions",
    "staff_create_employee",
    "staff_rename_employee",
    "staff_list_employees",
    "staff_delete_employee",
    "staff_assign_job_functions",
    "staff_change_workload_profile",
    "staff_declare_shift_preference",
    "staff_register_unavailability",
    "staff_remove_unavailability",
    "staff_deactivate_employee",
    "staff_reactivate_employee",
    "staff_copy_employee_to_unit",
)

_TOTAL_DE_USE_CASES = 16


def _dependencias() -> ApplicationDependencies:
    """O grafo real, sem banco no ar — `create_engine` não abre conexão."""
    return wire_dependencies(Settings(_env_file=None))


def test_ca18_os_dezesseis_use_cases_de_staff_estao_no_conteiner() -> None:
    """A contagem é asserção, não decoração.

    O número 16 vem do plano e da pasta `use_cases/`. Sem asserir a contagem, um
    use case esquecido no wiring não teria sintoma nenhum até a 3.4 — quando
    apareceria como `AttributeError` num router recém-escrito, longe da causa.
    """
    deps = _dependencias()

    assert len(_USE_CASES_DE_STAFF) == _TOTAL_DE_USE_CASES
    ausentes = [nome for nome in _USE_CASES_DE_STAFF if getattr(deps, nome, None) is None]
    assert ausentes == [], f"use cases de staff não montados: {ausentes}"


def test_ca18_a_lista_deste_teste_cobre_a_pasta_de_use_cases_inteira() -> None:
    """Fecha o buraco da lista explícita: ela pode ficar **incompleta**.

    A lista acima é escrita à mão para que um use case não wirado apareça como
    falha em vez de sumir da varredura. O preço é que ela mesma pode envelhecer:
    um use case novo entra na pasta, ninguém acrescenta aqui, e o teste anterior
    continua verde. Esta asserção cobra a pasta contra a lista — e é a **única**
    varredura de diretório do arquivo, feita de propósito no lugar onde
    derivar ajuda em vez de esconder.
    """
    pasta = _SRC / "features" / "staff" / "application" / "use_cases"
    na_pasta = {arquivo.stem for arquivo in pasta.glob("*.py") if arquivo.stem != "__init__"}
    na_lista = {nome.removeprefix("staff_") for nome in _USE_CASES_DE_STAFF}

    assert na_pasta == na_lista, (
        f"a lista deste teste divergiu da pasta — só na pasta: {sorted(na_pasta - na_lista)}; "
        f"só na lista: {sorted(na_lista - na_pasta)}"
    )


def test_ca18_os_use_cases_recebem_os_adapters_postgres_e_nao_fakes() -> None:
    """O que CA18 realmente pede: o repositório **injetado** é o do Postgres.

    Trocar `PostgresEmployeeRepository` por um fake no composition root passaria
    despercebido em toda a suíte — não há consumidor de staff até a 3.4 — e o
    sintoma seria uma aplicação que aceita cadastros e os perde no restart.
    """
    deps = _dependencias()

    assert isinstance(deps.staff_create_employee._employees, PostgresEmployeeRepository)
    assert isinstance(deps.staff_create_employee._job_functions, PostgresJobFunctionRepository)
    assert isinstance(deps.staff_list_job_functions._job_functions, PostgresJobFunctionRepository)
    assert isinstance(deps.staff_delete_job_function._employees, PostgresEmployeeRepository)
    assert isinstance(deps.staff_copy_employee_to_unit._employees, PostgresEmployeeRepository)


def test_os_dois_ports_cruzados_compartilham_a_mesma_instancia_de_repositorio() -> None:
    """Os use cases que tocam os dois agregados veem **o mesmo** par.

    `delete_job_function` consulta funcionário (L-JF3) e `create_employee`
    consulta função (L-E4). Com instâncias diferentes — pior, com `Engine`
    diferentes — as duas guardas passariam a olhar para pools distintos sem ganho
    nenhum, e o wiring estaria pagando conexão por engano. A identidade de objeto
    é a forma mais direta de travar isso.
    """
    deps = _dependencias()

    assert deps.staff_create_employee._employees is deps.staff_delete_employee._employees
    assert (
        deps.staff_create_employee._job_functions is deps.staff_delete_job_function._job_functions
    )
    assert deps.staff_delete_job_function._employees is deps.staff_list_employees._employees


def test_duas_chamadas_devolvem_grafos_de_staff_independentes() -> None:
    """Sem singleton global (skill `composition-root`), também para staff."""
    primeiro = _dependencias()
    segundo = _dependencias()

    assert primeiro.staff_create_employee is not segundo.staff_create_employee
    assert primeiro.staff_create_employee._employees is not segundo.staff_create_employee._employees


def _modulos_que_importam_adapters_de_staff() -> set[str]:
    """Varre `src/` por imports do pacote de adapters de staff.

    Ignora os arquivos **de dentro do próprio pacote**: um repositório importar
    `mappers`, `tables` ou `integrity_errors` do vizinho é coesão interna, não a
    violação que este teste procura (um consumidor externo pulando o composition
    root).
    """
    culpados: set[str] = set()
    for arquivo in _SRC.rglob("*.py"):
        if arquivo.is_relative_to(_PACOTE_DE_ADAPTERS):
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for no in ast.walk(arvore):
            alvo = ""
            if isinstance(no, ast.ImportFrom) and no.module:
                alvo = no.module
            elif isinstance(no, ast.Import):
                alvo = " ".join(alias.name for alias in no.names)
            if _MODULO_DE_ADAPTERS in alvo:
                culpados.add(str(arquivo.relative_to(_SRC)))
    return culpados


def test_so_o_composition_root_importa_os_adapters_de_staff() -> None:
    """A regra que o import-linter não cobre, como asserção mecânica.

    `bc-independence` compara `features.identity` contra `features.staff`, e o
    composition root não pertence a nenhum dos dois — então nada nos contratos
    impede um **outro** módulo de importar os adapters de staff direto. Este
    teste fecha a janela pelo lado do consumidor, como o de identity faz.
    """
    esperado = {str(_COMPOSITION_ROOT.relative_to(_SRC))}
    assert _modulos_que_importam_adapters_de_staff() == esperado, (
        f"apenas composition_root.py pode importar {_MODULO_DE_ADAPTERS}; "
        f"receba o repositório por injeção (LAYOUT §6)"
    )


def test_um_import_proibido_plantado_reprova() -> None:
    """Teste negativo: o detector detecta.

    Um guarda que nunca viu um caso positivo não é um guarda — é uma função que
    devolve conjunto vazio.
    """
    codigo_violador = (
        "from restaurant_hub.features.staff.adapters.out.postgres.employee_repository "
        "import PostgresEmployeeRepository"
    )
    arvore = ast.parse(codigo_violador)

    alvos = [no.module for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) and no.module]

    assert any(_MODULO_DE_ADAPTERS in alvo for alvo in alvos)
