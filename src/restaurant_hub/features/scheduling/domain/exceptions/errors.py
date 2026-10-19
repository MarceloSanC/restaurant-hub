"""Exceções de domínio do bounded context scheduling.

Todas herdam de `SchedulingError`, que por sua vez herda de `DomainError`
(`shared/domain`) — o error handler HTTP converte a hierarquia `DomainError` em
resposta 4xx; o mapa de status deste BC é da Stage 4.5. Aqui garante-se apenas a
hierarquia e a mensagem; nenhuma exceção carrega estado além do texto.

**As 20 da Stage 4.1 nasceram juntas, antes de terem consumidor.** O mapa de erros do concept
§6 é uma **totalidade** (21 linhas para 20 exceções), e a varredura que o cobra
(`test_exceptions.py`) enumera `vars` deste módulo. Se as exceções chegassem aos
poucos, junto com cada VO/entidade que as levanta, a varredura não seria
totalidade em nenhum commit intermediário e o piso de
`tests/unit/test_status_map.py` (`_TOTAIS_MINIMOS["scheduling"]`) seria falso no
primeiro commit da Stage. Cada uma é levantada por uma Task 02-10.

A Stage 4.2 acrescenta duas, pelo mesmo motivo juntas na Task 01: a recusa da
configuração de validação e a do insumo do avaliador (concept 4.2 §6).
"""

from restaurant_hub.shared.domain.exceptions.base import DomainError


class SchedulingError(DomainError):
    """Erro de negócio do bounded context scheduling."""


class InvalidIdentifierError(SchedulingError):
    """Identificador de entidade vazio ou só-whitespace.

    Entidade sem identidade é entidade inválida. Importa em especial para o
    `tenant_id`/`unit_id`: um identificador vazio criaria um balde de falso
    isolamento entre tenants/unidades.
    """

    def __init__(self, entity: str) -> None:
        super().__init__(f"identificador de {entity} não pode ser vazio")


class InvalidTimeRangeError(SchedulingError):
    """Faixa de horário malformada, ou com intervalo declarado fora dos limites.

    Cobre os dois grupos de defeito que o concept §6 lista em três linhas: o par
    de instantes (tz-aware, segundo/microssegundo não zero, `start >= end`,
    duração nominal > 24h) e o intervalo da faixa
    (`0 <= break_minutes < nominal_minutes`), na construção ou por
    `redeclare_band_break`. `reason` existe porque um erro que cobre defeitos
    distintos não pode afirmar sempre o mesmo — dizer "início deve anteceder o
    fim" sobre um intervalo negativo descreveria o defeito errado a quem recebe
    a recusa.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"faixa de horário inválida: {reason}")


class InvalidWeekdayError(SchedulingError):
    """Dia da semana desconhecido — fora do conjunto fechado de `Weekday`.

    Espelha `InvalidDayPeriodError` de staff: a conversão de texto para o enum
    falha como **erro de domínio**, e não como o `ValueError` cru do `StrEnum`
    (que não é `SchedulingError`, não tem handler, e viraria 500 na borda).
    """

    def __init__(self, value: str) -> None:
        super().__init__(f"dia da semana inválido: {value!r}")


class InvalidDayCutoffError(SchedulingError):
    """Horário de corte malformado — `time` tz-aware ou sem minuto inteiro.

    **Não** cobre teto de horário: o corte é configuração por restaurante e não
    tem teto na v1 (ADR 4.1.0002 §2, confirmado pelo sponsor em 2026-09-27).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"horário de corte inválido: {reason}")


class InvalidSchedulePeriodError(SchedulingError):
    """Período da escala fora do domínio válido, ou desalinhado ao dia de início.

    `reason` é obrigatório porque a §6 usa esta exceção para **dois** cenários
    distintos: a contagem de dias fora de `1 <= days <= 31` e o `first_day` que
    não cai no `week_start` do calendário (na fábrica `period_starting_on` e no
    `Schedule.__post_init__`, logo também na reidratação). Sem o motivo, a
    mensagem descreveria um dos dois erradamente.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"período de escala inválido: {reason}")


class InvalidDemandQuantityError(SchedulingError):
    """Quantidade de demanda negativa.

    `0` é estado válido — "faixa habilitada sem demanda dessa função" — e N é
    alvo, não teto (ADR 4.1.0003 (g)). Só o negativo é recusado.
    """

    def __init__(self, value: object) -> None:
        super().__init__(f"quantidade de demanda inválida: {value!r} (deve ser >= 0)")


class InvalidScheduleVersionError(SchedulingError):
    """Contador de versão da escala menor que 1.

    A versão nasce em 1 e só cresce (ADR 4.1.0001 §2); a checagem otimista que a
    consome é da 4.4.
    """

    def __init__(self, value: object) -> None:
        super().__init__(f"versão de escala inválida: {value!r} (deve ser >= 1)")


class InvalidAssignmentBreakError(SchedulingError):
    """Intervalo declarado na alocação fora dos limites.

    O piso (`>= 0`) é verificado na própria `Assignment`; o **teto**
    (`< nominal_minutes` da faixa que a contém) só na `ShiftBand`, o único nível
    que vê a duração nominal e as alocações ao mesmo tempo (ADR 4.1.0011).
    `reason` distingue os dois, e também o encurtamento de faixa que invalida um
    intervalo já declarado (`reschedule_band`).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"intervalo da alocação inválido: {reason}")


class DuplicateEntityIdError(SchedulingError):
    """Dois objetos internos do agregado com o mesmo identificador.

    `id_type` nomeia **qual** coleção quebrou (`ShiftBandId`, `ShiftDemandId` ou
    `AssignmentId`): a invariante 15 é par a par por tipo, em qualquer nível, e
    uma mensagem que não diz o tipo não diz onde procurar (concept §5.15).
    """

    def __init__(self, id_type: str) -> None:
        super().__init__(f"dois objetos do agregado com o mesmo {id_type}")


class DuplicateShiftBandError(SchedulingError):
    """Duas faixas da escala com o mesmo par `(start, end)`.

    A chave de unicidade é o par de instantes e **não** inclui o intervalo
    declarado (ADR 4.1.0011): duas faixas idênticas no relógio com intervalos
    diferentes seriam ambiguidade, não variação.
    """

    def __init__(self) -> None:
        super().__init__("a escala já tem uma faixa com esse par (início, fim)")


class ShiftBandNotFoundError(SchedulingError):
    """Faixa inexistente na escala."""

    def __init__(self) -> None:
        super().__init__("faixa não encontrada na escala")


class ShiftBandInUseError(SchedulingError):
    """Desabilitar faixa que ainda tem alocação (§5.21).

    A guarda **recusa** em vez de cascatear sobre pessoas alocadas: cada
    `unassign` é uma mutação publicada, com auditoria e notificação próprias. As
    demandas **sem** alocação saem com a faixa — a cascata é sobre demanda, não
    sobre alocação.
    """

    def __init__(self) -> None:
        super().__init__("faixa com alocação pendente não pode ser desabilitada")


class ShiftBandDayChangeError(SchedulingError):
    """Reagendamento cujo destino cai em outro dia operacional (§5.22).

    Reagendar preserva demandas e alocações, e isso só faz sentido dentro do
    mesmo dia operacional: mover a faixa de dia moveria pessoas escaladas para
    um dia em que ninguém as escalou.
    """

    def __init__(self) -> None:
        super().__init__("reagendamento não pode mudar o dia operacional da faixa")


class TimeRangeOutsidePeriodError(SchedulingError):
    """Faixa que começa fora dos dias operacionais do período da escala.

    A checagem é sobre o dia operacional do `start` — uma faixa pode terminar
    até 24h adentro do período seguinte, e isso é desenho (ADR 4.1.0008 §3).
    """

    def __init__(self) -> None:
        super().__init__("a faixa começa fora dos dias operacionais do período")


class DuplicateShiftDemandError(SchedulingError):
    """Segunda demanda da mesma função na mesma faixa.

    A cardinalidade é uma demanda por função e faixa (ADR 4.1.0010); duas
    linhas para a mesma função na mesma faixa tornariam ambígua a quantidade
    alvo.
    """

    def __init__(self) -> None:
        super().__init__("a faixa já tem demanda dessa função")


class ShiftDemandNotFoundError(SchedulingError):
    """Demanda inexistente na escala."""

    def __init__(self) -> None:
        super().__init__("demanda não encontrada na escala")


class ShiftDemandInUseError(SchedulingError):
    """Retirar demanda que ainda tem alocação (§5.21).

    A irmã de `ShiftBandInUseError`, no nível da demanda: retirar a demanda
    apagaria as vagas ocupadas sem passar pelo `unassign` de cada uma.
    """

    def __init__(self) -> None:
        super().__init__("demanda com alocação pendente não pode ser retirada")


class DuplicateAssignmentError(SchedulingError):
    """O mesmo funcionário em duas vagas da **mesma** demanda.

    Nível que possui as alocações. Disjunta de
    `DuplicateAssignmentInBandError`, que é o mesmo funcionário em demandas
    **distintas** da mesma faixa (concept §5.23).
    """

    def __init__(self) -> None:
        super().__init__("o funcionário já ocupa uma vaga desta demanda")


class DuplicateAssignmentInBandError(SchedulingError):
    """O mesmo funcionário em duas vagas da **mesma faixa** (invariante 23).

    Uma pessoa em dois lugares é impossibilidade física, não política
    (ADR 4.1.0012) — e é o estado que tornava errada a fórmula única de horas.
    Faixas **distintas**, inclusive parcialmente sobrepostas, seguem aceitas: a
    sobreposição entre faixas é política da 4.2.
    """

    def __init__(self) -> None:
        super().__init__("o funcionário já ocupa uma vaga de outra demanda da mesma faixa")


class AssignmentNotFoundError(SchedulingError):
    """Alocação inexistente na escala."""

    def __init__(self) -> None:
        super().__init__("alocação não encontrada na escala")


class InvalidValidationConfigError(SchedulingError):
    """Configuração de validação do restaurante fora do domínio válido (Stage 4.2).

    Descanso mínimo negativo, teto diário ou semanal não positivo, tolerância da
    carga negativa (concept 4.2 §5.3). `reason` nomeia o parâmetro: uma recusa que
    cobre cinco parâmetros e não diz qual quebrou não diz o que corrigir.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"configuração de validação inválida: {reason}")


class InvalidEvaluationInputError(SchedulingError):
    """Insumo do avaliador incompleto ou incoerente (Stage 4.2, concept §5.4).

    Fail-closed: vizinha de outro tenant/unidade ou não adjacente, período que não
    é de 7 dias, `AssignmentId` repetido entre escalas, fatos repetidos ou faltando
    para um registro alocado, carga ou janela de indisponibilidade malformada.
    Pular o que falta deixaria passar uma violação `block` em silêncio. `reason`
    distingue os cenários.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"insumo de avaliação inválido: {reason}")
