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
    ProvisionRestaurantCommand,
    RefreshSessionCommand,
    RequestPasswordResetCommand,
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
from restaurant_hub.features.identity.application.dtos.tokens import IssuedRefreshToken
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    InvalidSetupTokenError,
    RefreshTokenReuseError,
    SessionFingerprintAlreadyExistsError,
)
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_account import (
    ProvisionAccountUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_restaurant import (
    ProvisionRestaurantUseCase,
)
from restaurant_hub.features.identity.application.use_cases.refresh_session import (
    RefreshSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.request_password_reset import (
    RequestPasswordResetUseCase,
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
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)

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


class _Restaurantes(PostgresRestaurantRepository):
    def __init__(self, engine: Engine, registro: Registro) -> None:
        super().__init__(engine)
        self._registro = registro

    def add(self, restaurant: Restaurant) -> None:
        super().add(restaurant)
        self._registro.escreveu("restaurants.add")


class _UsuariosQueNaoVeemOEmail(_Usuarios):
    """`exists_by_email` sempre `False`: a corrida em que outro cadastro do mesmo
    e-mail comita entre a checagem do use case e o `users.add`. Quem recusa é o
    índice `uq_users_email`, **dentro** da unidade e depois do `restaurants.add`."""

    def exists_by_email(self, email: Email) -> bool:
        return False


class _Sessoes(PostgresSessionRepository):
    def __init__(self, engine: Engine, registro: Registro) -> None:
        super().__init__(engine)
        self._registro = registro

    def revoke_all_for_user(self, user_id: UserId, revoked_at: datetime) -> None:
        super().revoke_all_for_user(user_id, revoked_at)
        self._registro.escreveu("sessions.revoke_all_for_user")

    def revoke(self, session_id: SessionId, revoked_at: datetime) -> bool:
        revogou = super().revoke(session_id, revoked_at)
        self._registro.escreveu("sessions.revoke")
        return revogou

    def add(self, session: Session) -> None:
        super().add(session)
        self._registro.escreveu("sessions.add")


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


def _esperar_bloqueio_em(engine: Engine, tabela: Table) -> None:
    """Espera até um `UPDATE` em `tabela` aparecer esperando **lock** (`wait_event_type`).

    É a prova de que a segunda thread está parada na linha travada pela primeira —
    e não apenas lenta (retirando conexão, lendo o fingerprint). Um `sleep` seguido
    de `is_alive()` passaria pelo motivo errado numa máquina carregada. O filtro
    pela tabela e pela própria sessão de fora evita contar um bloqueio alheio.
    """
    limite = time.monotonic() + _ESPERA
    consulta = text(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname = current_database() AND wait_event_type = 'Lock' "
        "AND pid <> pg_backend_pid() AND query ILIKE :padrao"
    )
    while time.monotonic() < limite:
        with engine.connect() as conexao:
            if conexao.execute(consulta, {"padrao": f"UPDATE {tabela.name} %"}).scalar_one() > 0:
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
        _esperar_bloqueio_em(com_link, tables.password_setup_tokens)
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


def _convidar(
    engine: Engine, registro: Registro, falha_no_envio: Exception | None = None
) -> tuple[InviteUserUseCase, RecordingEmailSender]:
    sender = RecordingEmailSender(fail_with=falha_no_envio)
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


# ---------------------------------------------------------------------------
# provision_restaurant — o tenant e o seu primeiro owner (issue #67, ADR 0.0.0014)
# ---------------------------------------------------------------------------

_ESCRITAS_DO_TENANT = ("restaurants.add", "users.add")
_TABELAS_DO_TENANT = (tables.restaurants, tables.users, tables.unit_memberships)
_EMAIL_DO_DONO = Email("dono@cantina.com")


def _provisionar_tenant(
    engine: Engine, registro: Registro, *, usuarios: _Usuarios | None = None
) -> ProvisionRestaurantUseCase:
    return ProvisionRestaurantUseCase(
        restaurants=_Restaurantes(engine, registro),
        users=usuarios if usuarios is not None else _Usuarios(engine, registro),
        hasher=FakePasswordHasher(),
        id_generator=FakeIdGenerator(),
        unit_of_work=PostgresUnitOfWork(engine),
    )


def _tenant(email: Email = _EMAIL_DO_DONO) -> ProvisionRestaurantCommand:
    return ProvisionRestaurantCommand(
        name="Cantina Nova", owner_email=email, owner_plain_password="s3nha"
    )


class TestProvisaoDoTenantAtomica:
    def test_sem_falha_grava_restaurante_e_dono_do_restaurante(self, banco_limpo: Engine) -> None:
        _semear_tenant_e_usuario(banco_limpo)
        registro = Registro()

        resultado = _provisionar_tenant(banco_limpo, registro).execute(_tenant())

        assert tuple(registro.escritas) == _ESCRITAS_DO_TENANT
        with banco_limpo.connect() as conexao:
            dono = conexao.execute(
                select(tables.users.c.role, tables.users.c.tenant_id).where(
                    tables.users.c.email == _EMAIL_DO_DONO.value
                )
            ).one()
            nome = conexao.execute(
                select(tables.restaurants.c.name).where(tables.restaurants.c.id == resultado.id)
            ).scalar_one()
        assert tuple(dono) == ("owner", resultado.id)
        assert nome == "Cantina Nova"

    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS_DO_TENANT) + 1))
    def test_falha_na_escrita_n_deixa_as_tabelas_identicas(
        self, banco_limpo: Engine, n: int
    ) -> None:
        """A falha dispara **depois** de a escrita N chegar ao banco: com N=1, o
        restaurante já foi inserido na unidade — e não sobrevive."""
        _semear_tenant_e_usuario(banco_limpo)
        antes = _linhas(banco_limpo, *_TABELAS_DO_TENANT)
        registro = Registro(falhar_em=n)

        with pytest.raises(_FalhaInjetada):
            _provisionar_tenant(banco_limpo, registro).execute(_tenant())

        assert tuple(registro.escritas) == _ESCRITAS_DO_TENANT[:n]
        assert _linhas(banco_limpo, *_TABELAS_DO_TENANT) == antes

    def test_email_tomado_no_banco_desfaz_o_restaurante(self, banco_limpo: Engine) -> None:
        """Falha originada no banco (`uq_users_email`) depois do `restaurants.add`."""
        _semear_tenant_e_usuario(banco_limpo)
        antes = _linhas(banco_limpo, *_TABELAS_DO_TENANT)
        registro = Registro()
        usuarios = _UsuariosQueNaoVeemOEmail(banco_limpo, registro)

        with pytest.raises(EmailAlreadyRegisteredError):
            _provisionar_tenant(banco_limpo, registro, usuarios=usuarios).execute(
                _tenant(Email("um@x.com"))
            )

        assert registro.escritas == ["restaurants.add"]
        assert _linhas(banco_limpo, *_TABELAS_DO_TENANT) == antes


# ---------------------------------------------------------------------------
# request_password_reset — invalidar e emitir numa unidade; toda falha absorvida
# ---------------------------------------------------------------------------

_ESCRITAS_DA_REDEFINICAO = ("tokens.invalidate_all_for_user", "tokens.add")


def _pedir_redefinicao(
    engine: Engine, registro: Registro, issuer: FakeSetupTokenIssuer | None = None
) -> tuple[RequestPasswordResetUseCase, RecordingEmailSender]:
    sender = RecordingEmailSender()
    use_case = RequestPasswordResetUseCase(
        users=PostgresUserRepository(engine),
        tokens=_Tokens(engine, registro),
        token_issuer=issuer if issuer is not None else FakeSetupTokenIssuer(),
        email_sender=sender,
        id_generator=FakeIdGenerator(),
        clock=FakeClock(_AGORA),
        reset_ttl=timedelta(minutes=30),
        base_url="https://app.exemplo.com",
        unit_of_work=PostgresUnitOfWork(engine),
    )
    return use_case, sender


def _emissor_a_partir_de(n: int) -> FakeSetupTokenIssuer:
    """Emissor que já "gastou" `n - 1` valores — para não colidir com os links semeados."""
    issuer = FakeSetupTokenIssuer()
    for _ in range(n - 1):
        issuer.issue()
    return issuer


_REDEFINIR = RequestPasswordResetCommand(email=Email("um@x.com"))


class TestRedefinicaoAtomica:
    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS_DA_REDEFINICAO) + 1))
    def test_falha_na_escrita_n_e_absorvida_e_deixa_a_tabela_identica(
        self, com_link: Engine, n: int
    ) -> None:
        antes = _linhas(com_link, tables.password_setup_tokens)
        registro = Registro(falhar_em=n)
        use_case, sender = _pedir_redefinicao(com_link, registro, _emissor_a_partir_de(10))

        assert use_case.execute(_REDEFINIR) is None

        assert tuple(registro.escritas) == _ESCRITAS_DA_REDEFINICAO[:n]
        assert _linhas(com_link, tables.password_setup_tokens) == antes
        assert sender.sent == ()

    def test_fingerprint_repetido_no_banco_e_absorvido_e_desfaz_a_invalidacao(
        self, com_link: Engine
    ) -> None:
        """Falha originada no banco: o emissor novo repete o fingerprint do link `tok-1`."""
        antes = _linhas(com_link, tables.password_setup_tokens)
        registro = Registro()
        use_case, sender = _pedir_redefinicao(com_link, registro)

        assert use_case.execute(_REDEFINIR) is None

        assert registro.escritas == ["tokens.invalidate_all_for_user"]
        assert _linhas(com_link, tables.password_setup_tokens) == antes
        assert sender.sent == ()

    def test_sem_falha_grava_o_token_pela_unidade_real(self, com_link: Engine) -> None:
        """CA8 — o caminho positivo: a unidade real comita e o e-mail sai."""
        use_case, sender = _pedir_redefinicao(com_link, Registro(), _emissor_a_partir_de(10))

        use_case.execute(_REDEFINIR)

        tokens = PostgresPasswordSetupTokenRepository(com_link)
        nova = tokens.find_by_fingerprint(FakeSetupTokenIssuer().fingerprint("setup-10"))
        anterior = tokens.find_by_fingerprint(FakeSetupTokenIssuer().fingerprint("setup-outro"))
        assert nova is not None and nova.consumed_at is None
        assert anterior is not None and anterior.consumed_at == _AGORA
        assert len(sender.sent) == 1


# ---------------------------------------------------------------------------
# refresh_session — rotação numa unidade; corrida perdida é reuso
# ---------------------------------------------------------------------------

_ESCRITAS_DA_ROTACAO = ("sessions.revoke", "sessions.add")
_REFRESH = "refresh-original"


@pytest.fixture
def com_sessao(banco_limpo: Engine) -> Engine:
    """Usuário com duas sessões ativas: a que vai rotacionar e a de outro dispositivo."""
    _semear_tenant_e_usuario(banco_limpo)
    sessoes = PostgresSessionRepository(banco_limpo)
    for session_id, valor in (("sess-1", _REFRESH), ("sess-2", "outro-dispositivo")):
        sessoes.add(
            Session(
                id=SessionId(session_id),
                user_id=UserId("user-1"),
                refresh_token_fingerprint=FakeTokenIssuer().fingerprint(valor),
                issued_at=_AGORA - timedelta(days=1),
                expires_at=_AGORA + timedelta(days=14),
            )
        )
    return banco_limpo


def _rotacionador(
    engine: Engine,
    registro: Registro,
    *,
    sessoes: PostgresSessionRepository | None = None,
    issuer: FakeTokenIssuer | None = None,
) -> RefreshSessionUseCase:
    return RefreshSessionUseCase(
        users=PostgresUserRepository(engine),
        sessions=sessoes if sessoes is not None else _Sessoes(engine, registro),
        token_issuer=issuer if issuer is not None else FakeTokenIssuer(),
        id_generator=FakeIdGenerator(),
        clock=FakeClock(_AGORA),
        access_token_ttl=timedelta(minutes=15),
        refresh_token_ttl=timedelta(days=14),
        unit_of_work=PostgresUnitOfWork(engine),
    )


def _sessoes_revogadas(engine: Engine) -> dict[str, bool]:
    with engine.connect() as conexao:
        linhas = conexao.execute(select(tables.sessions.c.id, tables.sessions.c.revoked_at)).all()
    return {str(linha.id): linha.revoked_at is not None for linha in linhas}


class _EmissorQueRepete(FakeTokenIssuer):
    """Emite como "novo" o refresh da sessão do outro dispositivo — colisão no banco."""

    def issue_refresh_token(self) -> IssuedRefreshToken:
        return IssuedRefreshToken(
            value="outro-dispositivo", fingerprint=self.fingerprint("outro-dispositivo")
        )


class TestRotacaoAtomica:
    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS_DA_ROTACAO) + 1))
    def test_falha_na_escrita_n_deixa_as_sessoes_identicas(
        self, com_sessao: Engine, n: int
    ) -> None:
        antes = _linhas(com_sessao, tables.sessions)
        registro = Registro(falhar_em=n)

        with pytest.raises(_FalhaInjetada):
            _rotacionador(com_sessao, registro).execute(
                RefreshSessionCommand(refresh_token=_REFRESH)
            )

        assert tuple(registro.escritas) == _ESCRITAS_DA_ROTACAO[:n]
        assert _linhas(com_sessao, tables.sessions) == antes

    def test_add_recusado_pelo_banco_deixa_o_refresh_antigo_valido(
        self, com_sessao: Engine
    ) -> None:
        """CA6 — falha **originada no banco** (`uq_sessions_fingerprint`) no `add` da nova.

        O emissor fixado devolve como "novo" o fingerprint da sessão do outro
        dispositivo; o banco recusa, a unidade desfaz o `revoke`, e uma rotação
        seguinte com o mesmo refresh funciona.
        """
        antes = _linhas(com_sessao, tables.sessions)

        with pytest.raises(SessionFingerprintAlreadyExistsError):
            _rotacionador(com_sessao, Registro(), issuer=_EmissorQueRepete()).execute(
                RefreshSessionCommand(refresh_token=_REFRESH)
            )

        assert _linhas(com_sessao, tables.sessions) == antes
        resultado = _rotacionador(com_sessao, Registro()).execute(
            RefreshSessionCommand(refresh_token=_REFRESH)
        )
        assert resultado.refresh_token

    def test_reuso_revoga_todas_as_sessoes_e_grava(self, com_sessao: Engine) -> None:
        """CA6 — o caminho de reuso fica fora da unidade: a revogação em massa comita."""
        _rotacionador(com_sessao, Registro()).execute(RefreshSessionCommand(refresh_token=_REFRESH))

        with pytest.raises(RefreshTokenReuseError):
            _rotacionador(com_sessao, Registro()).execute(
                RefreshSessionCommand(refresh_token=_REFRESH)
            )

        assert all(_sessoes_revogadas(com_sessao).values())


class _SessoesQueSeguramAUnidade(PostgresSessionRepository):
    """Depois do `revoke`, avisa e espera — a linha da sessão fica travada na unidade."""

    def __init__(self, engine: Engine, *, falhar_depois: bool) -> None:
        super().__init__(engine)
        self.revogou = threading.Event()
        self.liberar = threading.Event()
        self._falhar_depois = falhar_depois

    def revoke(self, session_id: SessionId, revoked_at: datetime) -> bool:
        revogou = super().revoke(session_id, revoked_at)
        self.revogou.set()
        assert self.liberar.wait(_ESPERA), "a thread principal não liberou a primeira rotação"
        if self._falhar_depois:
            raise _FalhaInjetada("depois do revoke")
        return revogou


class TestRotacoesConcorrentes:
    """CA13 — a segunda rotação espera o lock; se a primeira comita, é reuso."""

    @pytest.mark.parametrize("primeira_falha", [False, True], ids=["comita", "desfaz"])
    def test_segunda_rotacao_do_mesmo_refresh(
        self, com_sessao: Engine, primeira_falha: bool
    ) -> None:
        segurador = _SessoesQueSeguramAUnidade(com_sessao, falhar_depois=primeira_falha)
        resultados: dict[str, object] = {}

        def rotacionar(nome: str, sessoes: PostgresSessionRepository | None) -> Callable[[], None]:
            def alvo() -> None:
                resultados[nome] = _rotacionador(com_sessao, Registro(), sessoes=sessoes).execute(
                    RefreshSessionCommand(refresh_token=_REFRESH)
                )

            return alvo

        primeira, erros_da_primeira = _em_thread(rotacionar("primeira", segurador))
        segunda, erros_da_segunda = _em_thread(rotacionar("segunda", None))

        primeira.start()
        assert segurador.revogou.wait(_ESPERA)
        segunda.start()
        _esperar_bloqueio_em(com_sessao, tables.sessions)
        assert segunda.is_alive()

        segurador.liberar.set()
        primeira.join(_ESPERA)
        segunda.join(_ESPERA)

        if primeira_falha:
            assert [type(e) for e in erros_da_primeira] == [_FalhaInjetada]
            assert erros_da_segunda == []
            assert "segunda" in resultados
            revogadas = _sessoes_revogadas(com_sessao)
            assert revogadas["sess-1"] is True
            assert revogadas["sess-2"] is False
        else:
            assert erros_da_primeira == []
            assert [type(e) for e in erros_da_segunda] == [RefreshTokenReuseError]
            # Fail-closed: tudo do usuário revogado, inclusive o par que a primeira emitiu.
            assert all(_sessoes_revogadas(com_sessao).values())


def test_convite_com_envio_falhando_deixa_conta_e_token_comitados(banco_limpo: Engine) -> None:
    """CA8 contra o banco real: o envio sai depois do commit, e a falha dele sobe."""
    _semear_tenant_e_usuario(banco_limpo)
    use_case, _ = _convidar(banco_limpo, Registro(), falha_no_envio=EmailSenderFailure("fora"))

    with pytest.raises(EmailSenderFailure):
        use_case.execute(_convite())

    linhas = _linhas(banco_limpo, *_TABELAS_DO_CONVITE)
    assert sum(1 for linha in linhas["users"] if linha[0] != "user-1") == 1
    assert len(linhas["password_setup_tokens"]) == 1
