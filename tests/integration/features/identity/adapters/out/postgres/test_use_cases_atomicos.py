"""Use cases de identity com escrita múltipla, contra PostgreSQL real (Stage 2.6, CA5).

Para cada use case, um injetor que falha **depois** de a N-ésima escrita delegar
ao repositório real — a escrita N chegou ao banco, dentro da unidade — e a
asserção de que as tabelas envolvidas ficaram idênticas ao estado de antes, para
todo N. "Depois de delegar" é o que distingue este teste de um com fake: um
injetor que levantasse antes da chamada nunca provaria que a própria escrita N é
desfeita, só as anteriores.

As corridas (CA7, CA13) usam duas threads e intercalação **forçada** por eventos
dentro da unidade da primeira: sem forçar, as threads quase nunca se sobrepõem e o
teste passaria pelo motivo errado.
"""

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, Table, select, text
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres import tables
from restaurant_hub.features.identity.adapters.out.postgres.password_setup_token_repository import (
    PostgresPasswordSetupTokenRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.session_repository import (
    PostgresSessionRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_of_work import (
    PostgresUnitOfWork,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_repository import (
    PostgresUnitRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.application.dtos.commands import (
    InviteUserCommand,
    ProvisionAccountCommand,
    SetPasswordWithTokenCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
    SetupTokenId,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import InvalidSetupTokenError
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_account import (
    ProvisionAccountUseCase,
)
from restaurant_hub.features.identity.application.use_cases.set_password_with_token import (
    SetPasswordWithTokenUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.integration

_AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
_ESPERA = 10  # segundos — teto de toda espera entre threads: o teste falha em vez de travar
_SONDAGEM = 0.05  # segundos entre leituras de `pg_stat_activity`


class _FalhaInjetada(Exception):
    """Levantada pelo injetor depois de a escrita N chegar ao banco."""


# ---------------------------------------------------------------------------
# Injetores: repositórios reais que registram cada escrita e falham na N-ésima
# ---------------------------------------------------------------------------


@dataclass
class Registro:
    """Ordem das escritas tentadas e em qual delas falhar (`None` = nenhuma)."""

    falhar_em: int | None = None
    escritas: list[str] = field(default_factory=list)

    def escreveu(self, nome: str) -> None:
        self.escritas.append(nome)
        if self.falhar_em is not None and len(self.escritas) == self.falhar_em:
            raise _FalhaInjetada(nome)


class _Usuarios(PostgresUserRepository):
    def __init__(self, engine: Engine, registro: Registro) -> None:
        super().__init__(engine)
        self._registro = registro

    def set_password_hash(self, user_id: UserId, password_hash: PasswordHash) -> None:
        super().set_password_hash(user_id, password_hash)
        self._registro.escreveu("users.set_password_hash")

    def add(
        self,
        user: User,
        password_hash: PasswordHash,
        memberships: Sequence[UnitMembership] = (),
    ) -> None:
        super().add(user, password_hash, memberships)
        self._registro.escreveu("users.add")


class _Sessoes(PostgresSessionRepository):
    def __init__(self, engine: Engine, registro: Registro) -> None:
        super().__init__(engine)
        self._registro = registro

    def revoke_all_for_user(self, user_id: UserId, revoked_at: datetime) -> None:
        super().revoke_all_for_user(user_id, revoked_at)
        self._registro.escreveu("sessions.revoke_all_for_user")


class _Tokens(PostgresPasswordSetupTokenRepository):
    def __init__(self, engine: Engine, registro: Registro) -> None:
        super().__init__(engine)
        self._registro = registro

    def consume(self, token_id: SetupTokenId, consumed_at: datetime) -> bool:
        consumiu = super().consume(token_id, consumed_at)
        self._registro.escreveu("tokens.consume")
        return consumiu

    def invalidate_all_for_user(
        self,
        user_id: UserId,
        consumed_at: datetime,
        purpose: SetupTokenPurpose | None = None,
    ) -> int:
        invalidados = super().invalidate_all_for_user(user_id, consumed_at, purpose)
        self._registro.escreveu("tokens.invalidate_all_for_user")
        return invalidados

    def add(self, token: PasswordSetupToken) -> None:
        super().add(token)
        self._registro.escreveu("tokens.add")


# ---------------------------------------------------------------------------
# Estado do banco
# ---------------------------------------------------------------------------


def _linhas(engine: Engine, *tabelas: Table) -> dict[str, list[tuple[object, ...]]]:
    """Todas as linhas das tabelas, em ordem de PK — o "byte a byte" do CA5."""
    with engine.connect() as conexao:
        return {
            tabela.name: [
                tuple(linha)
                for linha in conexao.execute(
                    select(tabela).order_by(*tabela.primary_key.columns)
                ).all()
            ]
            for tabela in tabelas
        }


def _semear_tenant_e_usuario(engine: Engine) -> None:
    PostgresRestaurantRepository(engine).add(Restaurant(id=RestaurantId("rest-a"), name="Cantina"))
    PostgresUnitRepository(engine).add(
        Unit(id=UnitId("unit-a1"), restaurant_id=RestaurantId("rest-a"), name="Centro")
    )
    PostgresUserRepository(engine).add(
        User(
            id=UserId("user-1"),
            email=Email("um@x.com"),
            role=Role.MANAGER,
            tenant_id=RestaurantId("rest-a"),
        ),
        PasswordHash("unusable::0"),
    )


# ---------------------------------------------------------------------------
# set_password_with_token — quatro escritas, três repositórios
# ---------------------------------------------------------------------------

_VALOR_DO_LINK = "setup-1"
_ESCRITAS_DA_SENHA = (
    "tokens.consume",
    "sessions.revoke_all_for_user",
    "tokens.invalidate_all_for_user",
    "users.set_password_hash",
)
_TABELAS_DA_SENHA = (tables.users, tables.sessions, tables.password_setup_tokens)


@pytest.fixture
def com_link(banco_limpo: Engine) -> Engine:
    """Usuário com sessão aberta, o link de convite e uma redefinição pendente."""
    _semear_tenant_e_usuario(banco_limpo)
    PostgresSessionRepository(banco_limpo).add(
        Session(
            id=SessionId("sess-1"),
            user_id=UserId("user-1"),
            refresh_token_fingerprint="fp::sessao",
            issued_at=_AGORA,
            expires_at=_AGORA + timedelta(days=14),
        )
    )
    tokens = PostgresPasswordSetupTokenRepository(banco_limpo)
    for token_id, proposito, valor in (
        ("tok-1", SetupTokenPurpose.INVITATION, _VALOR_DO_LINK),
        ("tok-2", SetupTokenPurpose.PASSWORD_RESET, "setup-outro"),
    ):
        tokens.add(
            PasswordSetupToken(
                id=SetupTokenId(token_id),
                user_id=UserId("user-1"),
                purpose=proposito,
                token_fingerprint=FakeSetupTokenIssuer().fingerprint(valor),
                issued_at=_AGORA,
                expires_at=_AGORA + timedelta(hours=72),
            )
        )
    return banco_limpo


def _definir_senha(
    engine: Engine,
    registro: Registro,
    *,
    tokens: PostgresPasswordSetupTokenRepository | None = None,
) -> SetPasswordWithTokenUseCase:
    return SetPasswordWithTokenUseCase(
        users=_Usuarios(engine, registro),
        sessions=_Sessoes(engine, registro),
        tokens=tokens if tokens is not None else _Tokens(engine, registro),
        token_issuer=FakeSetupTokenIssuer(),
        hasher=FakePasswordHasher(),
        clock=FakeClock(_AGORA),
        unit_of_work=PostgresUnitOfWork(engine),
    )


def _hash_gravado(engine: Engine) -> str:
    with engine.connect() as conexao:
        return str(
            conexao.execute(
                select(tables.users.c.password_hash).where(tables.users.c.id == "user-1")
            ).scalar_one()
        )


class TestDefinirSenhaAtomico:
    def test_sem_falha_grava_as_quatro_escritas_na_ordem(self, com_link: Engine) -> None:
        registro = Registro()

        _definir_senha(com_link, registro).execute(
            SetPasswordWithTokenCommand(token=_VALOR_DO_LINK, plain_password="nova")
        )

        assert tuple(registro.escritas) == _ESCRITAS_DA_SENHA
        assert _hash_gravado(com_link) == FakePasswordHasher().hash("nova")

    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS_DA_SENHA) + 1))
    def test_falha_na_escrita_n_deixa_as_tabelas_identicas(self, com_link: Engine, n: int) -> None:
        antes = _linhas(com_link, *_TABELAS_DA_SENHA)
        registro = Registro(falhar_em=n)

        with pytest.raises(_FalhaInjetada):
            _definir_senha(com_link, registro).execute(
                SetPasswordWithTokenCommand(token=_VALOR_DO_LINK, plain_password="nova")
            )

        assert tuple(registro.escritas) == _ESCRITAS_DA_SENHA[:n]
        assert _linhas(com_link, *_TABELAS_DA_SENHA) == antes

    def test_o_mesmo_link_funciona_depois_de_uma_falha(self, com_link: Engine) -> None:
        """O ganho visível da unidade: o link não é queimado pela tentativa que falhou."""
        with pytest.raises(_FalhaInjetada):
            _definir_senha(com_link, Registro(falhar_em=4)).execute(
                SetPasswordWithTokenCommand(token=_VALOR_DO_LINK, plain_password="nova")
            )

        _definir_senha(com_link, Registro()).execute(
            SetPasswordWithTokenCommand(token=_VALOR_DO_LINK, plain_password="nova")
        )

        assert _hash_gravado(com_link) == FakePasswordHasher().hash("nova")


class _TokensQueSeguramAUnidade(PostgresPasswordSetupTokenRepository):
    """Depois do `consume`, avisa e espera — a unidade fica aberta com a linha travada."""

    def __init__(self, engine: Engine, *, falhar_depois: bool) -> None:
        super().__init__(engine)
        self.consumiu = threading.Event()
        self.liberar = threading.Event()
        self._falhar_depois = falhar_depois

    def consume(self, token_id: SetupTokenId, consumed_at: datetime) -> bool:
        consumiu = super().consume(token_id, consumed_at)
        self.consumiu.set()
        assert self.liberar.wait(_ESPERA), "a thread principal não liberou a primeira redenção"
        if self._falhar_depois:
            raise _FalhaInjetada("depois do consume")
        return consumiu


def _esperar_alguem_bloqueado_por_lock(engine: Engine) -> None:
    """Espera até uma sessão deste banco aparecer esperando **lock** (`wait_event_type`).

    É a prova de que a segunda thread está parada na linha travada pela primeira —
    e não apenas lenta (retirando conexão, lendo o fingerprint). Um `sleep` seguido
    de `is_alive()` passaria pelo motivo errado numa máquina carregada.
    """
    limite = time.monotonic() + _ESPERA
    consulta = text(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
    )
    while time.monotonic() < limite:
        with engine.connect() as conexao:
            if conexao.execute(consulta).scalar_one() > 0:
                return
        time.sleep(_SONDAGEM)
    pytest.fail("nenhuma sessão ficou esperando lock — a segunda thread não bloqueou na linha")


def _em_thread(alvo: Callable[[], None]) -> tuple[threading.Thread, list[BaseException]]:
    erros: list[BaseException] = []

    def rodar() -> None:
        try:
            alvo()
        except BaseException as erro:
            erros.append(erro)

    return threading.Thread(target=rodar), erros


class TestRedencoesConcorrentes:
    """CA7 — a segunda redenção espera o lock e reavalia contra a linha comitada."""

    @pytest.mark.parametrize("primeira_falha", [False, True], ids=["comita", "desfaz"])
    def test_segunda_redencao_espera_a_primeira_terminar(
        self, com_link: Engine, primeira_falha: bool
    ) -> None:
        segurador = _TokensQueSeguramAUnidade(com_link, falhar_depois=primeira_falha)
        primeira, erros_da_primeira = _em_thread(
            lambda: _definir_senha(com_link, Registro(), tokens=segurador).execute(
                SetPasswordWithTokenCommand(token=_VALOR_DO_LINK, plain_password="da-primeira")
            )
        )
        segunda, erros_da_segunda = _em_thread(
            lambda: _definir_senha(com_link, Registro()).execute(
                SetPasswordWithTokenCommand(token=_VALOR_DO_LINK, plain_password="da-segunda")
            )
        )

        primeira.start()
        assert segurador.consumiu.wait(_ESPERA)
        segunda.start()
        _esperar_alguem_bloqueado_por_lock(com_link)
        assert segunda.is_alive()

        segurador.liberar.set()
        primeira.join(_ESPERA)
        segunda.join(_ESPERA)

        if primeira_falha:
            assert [type(e) for e in erros_da_primeira] == [_FalhaInjetada]
            assert erros_da_segunda == []
            assert _hash_gravado(com_link) == FakePasswordHasher().hash("da-segunda")
        else:
            assert erros_da_primeira == []
            assert [type(e) for e in erros_da_segunda] == [InvalidSetupTokenError]
            assert _hash_gravado(com_link) == FakePasswordHasher().hash("da-primeira")


# ---------------------------------------------------------------------------
# invite_user — conta e token numa unidade; o e-mail sai depois do commit
# ---------------------------------------------------------------------------

_ESCRITAS_DO_CONVITE = ("users.add", "tokens.add")
_TABELAS_DO_CONVITE = (tables.users, tables.unit_memberships, tables.password_setup_tokens)


def _convidar(engine: Engine, registro: Registro) -> tuple[InviteUserUseCase, RecordingEmailSender]:
    sender = RecordingEmailSender()
    use_case = InviteUserUseCase(
        users=_Usuarios(engine, registro),
        restaurants=PostgresRestaurantRepository(engine),
        units=PostgresUnitRepository(engine),
        hasher=FakePasswordHasher(),
        tokens=_Tokens(engine, registro),
        # Emissor novo: o primeiro valor que ele emite é `setup-1`, o mesmo do link
        # semeado em `com_link` — é o que permite a falha originada no banco.
        token_issuer=FakeSetupTokenIssuer(),
        email_sender=sender,
        id_generator=FakeIdGenerator(),
        clock=FakeClock(_AGORA),
        invitation_ttl=timedelta(hours=72),
        base_url="https://app.exemplo.com",
        unit_of_work=PostgresUnitOfWork(engine),
    )
    return use_case, sender


def _convite() -> InviteUserCommand:
    return InviteUserCommand(
        email=Email("novo@x.com"),
        role=Role.MANAGER,
        tenant_id=RestaurantId("rest-a"),
        unit_ids=(UnitId("unit-a1"),),
    )


class TestConviteAtomico:
    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS_DO_CONVITE) + 1))
    def test_falha_na_escrita_n_deixa_as_tabelas_identicas(
        self, banco_limpo: Engine, n: int
    ) -> None:
        _semear_tenant_e_usuario(banco_limpo)
        antes = _linhas(banco_limpo, *_TABELAS_DO_CONVITE)
        registro = Registro(falhar_em=n)
        use_case, sender = _convidar(banco_limpo, registro)

        with pytest.raises(_FalhaInjetada):
            use_case.execute(_convite())

        assert tuple(registro.escritas) == _ESCRITAS_DO_CONVITE[:n]
        assert _linhas(banco_limpo, *_TABELAS_DO_CONVITE) == antes
        assert sender.sent == ()

    def test_fingerprint_repetido_no_banco_desfaz_a_conta(self, com_link: Engine) -> None:
        """Falha **originada no banco**: `uq_setup_tokens_fingerprint` recusa o `tokens.add`.

        O `users.add` já tinha passado dentro da unidade; o rollback o desfaz, e não
        nasce conta sem link (o órfão dentro de identity que a 3.5 declarou).
        """
        antes = _linhas(com_link, *_TABELAS_DO_CONVITE)
        registro = Registro()
        use_case, sender = _convidar(com_link, registro)

        with pytest.raises(IntegrityError):
            use_case.execute(_convite())

        assert registro.escritas == ["users.add"]
        assert _linhas(com_link, *_TABELAS_DO_CONVITE) == antes
        assert sender.sent == ()

    def test_sem_falha_grava_conta_vinculo_e_token(self, banco_limpo: Engine) -> None:
        _semear_tenant_e_usuario(banco_limpo)
        use_case, sender = _convidar(banco_limpo, Registro())

        use_case.execute(_convite())

        linhas = _linhas(banco_limpo, *_TABELAS_DO_CONVITE)
        assert sum(1 for linha in linhas["users"] if linha[0] != "user-1") == 1  # a conta nova
        assert len(linhas["unit_memberships"]) == 1
        assert len(linhas["password_setup_tokens"]) == 1
        assert len(sender.sent) == 1


# ---------------------------------------------------------------------------
# provision_account — a metade identity da travessia de staff (3.5 R17)
# ---------------------------------------------------------------------------


def _provisionar(engine: Engine, registro: Registro) -> ProvisionAccountUseCase:
    return ProvisionAccountUseCase(
        users=_Usuarios(engine, registro),
        restaurants=PostgresRestaurantRepository(engine),
        units=PostgresUnitRepository(engine),
        hasher=FakePasswordHasher(),
        tokens=_Tokens(engine, registro),
        token_issuer=FakeSetupTokenIssuer(),
        id_generator=FakeIdGenerator(),
        clock=FakeClock(_AGORA),
        invitation_ttl=timedelta(hours=72),
        handover_ttl=timedelta(hours=168),
        base_url="https://app.exemplo.com",
        unit_of_work=PostgresUnitOfWork(engine),
    )


def _provisao() -> ProvisionAccountCommand:
    return ProvisionAccountCommand(
        email=Email("funcionario@x.com"),
        role=Role.EMPLOYEE,
        tenant_id=RestaurantId("rest-a"),
        unit_ids=(UnitId("unit-a1"),),
        handed_over=True,
    )


class TestProvisaoAtomica:
    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS_DO_CONVITE) + 1))
    def test_falha_na_escrita_n_deixa_as_tabelas_identicas(
        self, banco_limpo: Engine, n: int
    ) -> None:
        _semear_tenant_e_usuario(banco_limpo)
        antes = _linhas(banco_limpo, *_TABELAS_DO_CONVITE)
        registro = Registro(falhar_em=n)

        with pytest.raises(_FalhaInjetada):
            _provisionar(banco_limpo, registro).execute(_provisao())

        assert tuple(registro.escritas) == _ESCRITAS_DO_CONVITE[:n]
        assert _linhas(banco_limpo, *_TABELAS_DO_CONVITE) == antes

    def test_fingerprint_repetido_no_banco_desfaz_a_conta(self, com_link: Engine) -> None:
        """Falha originada no banco (`uq_setup_tokens_fingerprint`) depois do `users.add`."""
        antes = _linhas(com_link, *_TABELAS_DO_CONVITE)
        registro = Registro()

        with pytest.raises(IntegrityError):
            _provisionar(com_link, registro).execute(_provisao())

        assert registro.escritas == ["users.add"]
        assert _linhas(com_link, *_TABELAS_DO_CONVITE) == antes
