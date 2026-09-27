"""Entidade Employee — registro de funcionário por unidade.

Raiz de agregado: agrega os períodos de indisponibilidade, cuja
**não-sobreposição por funcionário** é consistência transacional do agregado
(workforce §3.6). Referencia `JobFunction` **só por id** — conjunto não-vazio
(ADR 3.1.0006); a **validade referencial** do conjunto (toda id existe no
tenant) continua sendo enforcement da 3.2/3.3. Não há bloqueio de função
inativa: a função não tem estado (ADR 3.2.0005).

Entidade **frozen**: transições devolvem nova instância via
`dataclasses.replace`, revalidada pelo `__post_init__` — as invariantes valem
em **todos** os caminhos de construção, inclusive a reidratação do mapper da
3.3 (a coleção inicial de indisponibilidades é validada par a par). Igualdade
por **identidade**.

A consistência `unit_id` ↔ `tenant_id` (a unidade pertence ao tenant) é
premissa da borda (concept §3): aqui ambos são opacos não-vazios.
"""

import dataclasses
from dataclasses import dataclass

from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeAlreadyHasLoginError,
    EmptyJobFunctionsError,
    InvalidIdentifierError,
    InvalidNameError,
    OverlappingUnavailabilityError,
    TerminatedEmployeeLoginError,
    UnavailabilityNotFoundError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import ShiftPreference
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import WorkloadProfile


@dataclass(frozen=True, eq=False)
class Employee:
    """Registro de funcionário de uma unidade.

    Attributes:
        id: identidade do registro.
        tenant_id: restaurante dono do registro.
        unit_id: unidade à qual o registro pertence (registro por unidade).
        name: nome verbatim (sem trim/case — ADR 3.1.0002), não-vazio e
            não-único (homônimos são legítimos).
        workload_profile: exatamente um perfil — fixa ou sob demanda
            (garantia estática da união de tipos).
        shift_preference: preferência declarada; `None` = sem preferência
            (ADR 3.1.0004).
        job_function_ids: funções do registro, no mínimo uma (ADR 3.1.0006).
        unavailabilities: períodos de indisponibilidade, sem sobreposição
            par a par (semântica semi-aberta — ADR 3.1.0001).
        active: estado do ciclo de vida (ADR 3.2.0006). O registro desligado
            **sobrevive** com toda a história: some da listagem default da
            unidade, continua endereçável por id e continua contando como
            **referência** para a guarda de remoção da função que ele aponta.
        user_id: o login em identity vinculado a **este** registro, ou `None`
            (Stage 3.5, ADR 3.5.0004). Opcional por desenho — login é ato
            explícito do gerente, por registro (workforce §3.8) —, definido
            **uma vez** por `link_login` e **nunca carregado pela cópia**: a
            construção campo a campo do clone não o nomeia, e o default `None`
            é o que faz "a cópia não carrega" valer por construção
            (ADR 3.2.0003 — lista de exclusão fechada; ADR 3.5.0004 §5).
            Quando presente é não-vazio, pela mesma razão dos demais ids: um
            `""` reidratado seria um vínculo-fantasma que bloquearia R17 para
            sempre.
    """

    id: EmployeeId
    tenant_id: TenantId
    unit_id: UnitId
    name: str
    workload_profile: WorkloadProfile
    shift_preference: ShiftPreference | None
    job_function_ids: frozenset[JobFunctionId]
    unavailabilities: tuple[UnavailabilityPeriod, ...] = ()
    active: bool = True
    user_id: UserId | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidIdentifierError("funcionário")
        if not self.tenant_id.strip():
            raise InvalidIdentifierError("tenant do funcionário")
        if not self.unit_id.strip():
            raise InvalidIdentifierError("unidade do funcionário")
        if not self.name.strip():
            raise InvalidNameError("funcionário")
        # Só o byte NUL, e nada além dele (ADR 3.4.0003 §2): é a única entrada da
        # bateria adversarial da 3.3 em que fake e Postgres divergiam. Aqui, em
        # `__post_init__`, a regra vale para TODO caminho de construção — `rename`
        # (que passa por `dataclasses.replace`) e a reidratação do mapper da 3.3.
        if "\x00" in self.name:
            raise InvalidNameError("funcionário", reason="não pode conter o byte NUL")
        if not self.job_function_ids:
            raise EmptyJobFunctionsError()
        # Presente ⇒ não-vazio. `None` é o estado legítimo "sem login"; `""`
        # não é estado nenhum (concept 3.5 §4; ADR 3.5.0004 §1).
        if self.user_id is not None and not self.user_id.strip():
            raise InvalidIdentifierError("login do funcionário")
        # Par a par sobre a coleção inteira: cobre a reidratação da 3.3 e as
        # transições (add_unavailability revalida por aqui via replace).
        for indice, periodo in enumerate(self.unavailabilities):
            for outro in self.unavailabilities[indice + 1 :]:
                if periodo.overlaps(outro):
                    raise OverlappingUnavailabilityError()

    def rename(self, name: str) -> "Employee":
        """Renomeia o registro — nova instância revalidada (nome verbatim)."""
        return dataclasses.replace(self, name=name)

    def assign_job_functions(self, ids: frozenset[JobFunctionId]) -> "Employee":
        """Substitui o conjunto de funções — vazio é rejeitado na revalidação."""
        return dataclasses.replace(self, job_function_ids=ids)

    def change_workload_profile(self, profile: WorkloadProfile) -> "Employee":
        """Troca o perfil de jornada (fixa ↔ sob demanda)."""
        return dataclasses.replace(self, workload_profile=profile)

    def declare_shift_preference(self, preference: ShiftPreference | None) -> "Employee":
        """Declara (ou substitui) a preferência de turno; `None` a limpa."""
        return dataclasses.replace(self, shift_preference=preference)

    def add_unavailability(self, period: UnavailabilityPeriod) -> "Employee":
        """Acrescenta um período — sobreposição com qualquer existente é
        rejeitada na revalidação (`OverlappingUnavailabilityError`); adjacente
        é aceito (semântica semi-aberta)."""
        return dataclasses.replace(self, unavailabilities=(*self.unavailabilities, period))

    def remove_unavailability(self, period: UnavailabilityPeriod) -> "Employee":
        """Remove um período por igualdade de valor — inexistente é erro."""
        if period not in self.unavailabilities:
            raise UnavailabilityNotFoundError()
        restantes = tuple(existente for existente in self.unavailabilities if existente != period)
        return dataclasses.replace(self, unavailabilities=restantes)

    def deactivate(self) -> "Employee":
        """Desliga o registro — idempotente no valor (já desligado não é erro).

        Desligar não apaga: a história (funções, indisponibilidades,
        preferência) permanece no registro (ADR 3.2.0006).
        """
        return dataclasses.replace(self, active=False)

    def reactivate(self) -> "Employee":
        """Recontrata o registro — idempotente no valor (já ativo não é erro)."""
        return dataclasses.replace(self, active=True)

    def assert_can_link_login(self) -> None:
        """As duas guardas do vínculo, **nesta ordem** (concept 3.5 §5.5, CA01).

        Método separado de `link_login` porque o use case precisa **perguntar
        antes de provisionar** a conta em identity: recusar depois deixaria uma
        conta pendente sem registro para um pedido que staff sempre ia recusar
        (§5.4). `link_login` chama esta guarda de novo, para que a regra tenha
        **uma** casa.

        Raises:
            EmployeeAlreadyHasLoginError: o registro já tem login — definido
                uma vez; não há "trocar" nesta Stage.
            TerminatedEmployeeLoginError: o registro está desligado — criar
                login é conceder acesso, e desligar cortou (kickoff #4,
                ADR 3.5.0003). Vinculado vence desligado na precedência.
        """
        if self.user_id is not None:
            raise EmployeeAlreadyHasLoginError(self.id)
        if not self.active:
            raise TerminatedEmployeeLoginError(self.id)

    def link_login(self, user_id: UserId) -> "Employee":
        """Vincula o login recém-criado — nova instância revalidada.

        Passa por `assert_can_link_login` e pelo `__post_init__` (que recusa
        `user_id` vazio), como toda transição desta entidade.
        """
        self.assert_can_link_login()
        return dataclasses.replace(self, user_id=user_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Employee):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
