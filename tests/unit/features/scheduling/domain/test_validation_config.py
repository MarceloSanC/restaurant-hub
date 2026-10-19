"""Testes da configuração de validação (value_objects/validation_config.py) — CA1, CA2.

**CA1 é sítio único, não só valor.** Além de conferir os defaults, a varredura AST
abaixo exige que os três números legais (660, 600, 2640) apareçam como literal
inteiro **só** nas linhas de `ValidationConfig.default()` em todo o pacote
`features/scheduling` — precedente do CA7 da 4.1 (`test_operational_calendar.py`).
Um `660` copiado numa política reprova aqui, sem depender de alguém rodar `rg`.
"""

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from restaurant_hub.features import scheduling
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidValidationConfigError,
)
from restaurant_hub.features.scheduling.domain.value_objects import validation_config
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    PolicyRule,
    ValidationConfig,
    WorkloadDirection,
)

pytestmark = pytest.mark.unit

_DEFAULTS_LEGAIS = (660, 600, 2640)

_CONFIGURAVEIS = (
    "overlap",
    "rest_between_shifts",
    "daily_cap",
    "weekly_cap",
    "workload",
    "function_mismatch",
    "over_coverage",
    "break_divergence",
)


def test_os_valores_dos_enums_sao_travados_por_nome() -> None:
    assert [(membro.name, membro.value) for membro in PolicyKind] == [
        ("OVERLAP", "overlap"),
        ("UNAVAILABILITY", "unavailability"),
        ("REST_BETWEEN_SHIFTS", "rest_between_shifts"),
        ("DAILY_CAP", "daily_cap"),
        ("WEEKLY_CAP", "weekly_cap"),
        ("WORKLOAD", "workload"),
        ("FUNCTION_MISMATCH", "function_mismatch"),
        ("OVER_COVERAGE", "over_coverage"),
        ("BREAK_DIVERGENCE", "break_divergence"),
    ]
    assert {membro.value for membro in EnforcementMode} == {"block", "warn"}
    assert {membro.value for membro in WorkloadDirection} == {"excess", "both"}


def test_default_devolve_os_valores_e_modos_do_adr_4_1_0003() -> None:
    config = ValidationConfig.default()

    assert config.min_rest_minutes == 11 * 60
    assert config.daily_cap_minutes == 10 * 60
    assert config.weekly_cap_minutes == 44 * 60
    assert config.workload_tolerance_minutes == 0
    assert config.workload_direction is WorkloadDirection.EXCESS
    assert config.overlap == PolicyRule(enabled=True, mode=EnforcementMode.BLOCK)
    for nome in _CONFIGURAVEIS[1:]:
        assert getattr(config, nome) == PolicyRule(enabled=True, mode=EnforcementMode.WARN), nome


def test_rule_for_cobre_os_nove_tipos_e_cada_campo_responde_pelo_seu() -> None:
    # Regras distintas por campo: um rule_for que trocasse dois campos reprova aqui.
    modos = (EnforcementMode.BLOCK, EnforcementMode.WARN)
    regras = {
        nome: PolicyRule(enabled=indice % 3 != 0, mode=modos[indice % 2])
        for indice, nome in enumerate(_CONFIGURAVEIS)
    }
    base = ValidationConfig.default()
    config = dataclasses.replace(base, **regras)

    for nome in _CONFIGURAVEIS:
        assert config.rule_for(PolicyKind(nome)) is regras[nome]
    assert {kind.value for kind in PolicyKind} == {*_CONFIGURAVEIS, "unavailability"}


def test_indisponibilidade_e_sempre_block_habilitada_e_sem_campo() -> None:
    config = dataclasses.replace(
        ValidationConfig.default(),
        overlap=PolicyRule(enabled=False, mode=EnforcementMode.WARN),
    )

    assert config.rule_for(PolicyKind.UNAVAILABILITY) == PolicyRule(
        enabled=True, mode=EnforcementMode.BLOCK
    )
    assert "unavailability" not in {campo.name for campo in dataclasses.fields(ValidationConfig)}


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("min_rest_minutes", -1),
        ("workload_tolerance_minutes", -1),
        ("daily_cap_minutes", 0),
        ("daily_cap_minutes", -5),
        ("weekly_cap_minutes", 0),
    ],
)
def test_config_recusa_parametro_fora_do_dominio_nomeando_o_parametro(
    campo: str, valor: int
) -> None:
    with pytest.raises(InvalidValidationConfigError, match=campo):
        dataclasses.replace(ValidationConfig.default(), **{campo: valor})


def test_config_aceita_as_fronteiras() -> None:
    config = dataclasses.replace(
        ValidationConfig.default(),
        min_rest_minutes=0,
        workload_tolerance_minutes=0,
        daily_cap_minutes=1,
        weekly_cap_minutes=1,
    )

    assert (config.min_rest_minutes, config.daily_cap_minutes, config.weekly_cap_minutes) == (
        0,
        1,
        1,
    )


def _literais_legais_no_bc() -> set[tuple[Path, int, int]]:
    raiz = Path(next(iter(scheduling.__path__)))
    return {
        (arquivo.resolve(), no.lineno, no.value)
        for arquivo in raiz.rglob("*.py")
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8")))
        if isinstance(no, ast.Constant) and type(no.value) is int and no.value in _DEFAULTS_LEGAIS
    }


def test_os_defaults_legais_aparecem_so_em_validation_config_default() -> None:
    linhas, inicio = inspect.getsourcelines(ValidationConfig.default)
    arquivo = Path(inspect.getfile(validation_config)).resolve()
    linhas_do_default = {(arquivo, inicio + indice) for indice in range(len(linhas))}

    ocorrencias = _literais_legais_no_bc()

    # Anti-vácuo por valor: cada um dos três tem de ser achado no próprio default.
    assert {valor for _, _, valor in ocorrencias} == set(_DEFAULTS_LEGAIS)
    assert {(caminho, linha) for caminho, linha, _ in ocorrencias} <= linhas_do_default
