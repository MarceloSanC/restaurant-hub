"""Mapa exceção → status HTTP do BC staff — CA17, CA18 e a metade estrutural de CA19.

O teste que carrega o arquivo é `test_ca17_o_mapa_e_total_sobre_staff_error`. Sem
ele, um erro adicionado numa Stage futura cairia no default 422 em silêncio — que
é precisamente como um 409 vira 422 sem ninguém notar.

**A totalidade sozinha não basta, e é por isso que CA18 existe.** As duas guardas
estruturais (toda classe tem entrada; toda entrada tem classe) só perguntam "há
entrada?" e nunca leem o **valor**: trocar duas entradas dentro de uma faixa já
exercitada sobrevive às duas. A verificação par a par é o que mata essa mutação,
e está provada por mutação real no relatório da Stage.
"""

import json

import pytest
from fastapi import FastAPI

from restaurant_hub.features.staff.adapters.inbound.http import error_handlers as handlers
from restaurant_hub.features.staff.application import errors as application_errors
from restaurant_hub.features.staff.application.errors import StaffApplicationError
from restaurant_hub.features.staff.domain.exceptions import errors as domain_errors
from restaurant_hub.features.staff.domain.exceptions.errors import StaffError

pytestmark = pytest.mark.unit

# Piso de contagem: 11 concretas no domínio + 12 na aplicação (concept 3.6 §6.1
# mais as cinco recusas de login da 3.5 §6.1 — duas de domínio, três de aplicação). É
# tripwire contra a enumeração encolher em silêncio — `__subclasses__` só enxerga
# o que foi importado, então um módulo de erro novo que ninguém importasse aqui
# faria a varredura passar sobre um universo menor do que o real.
_TOTAL_DE_ERROS_DE_STAFF = 23
_TOTAL_DE_MODULOS_DE_ERRO = 2

# Os dois módulos são importados acima de propósito, e não por acaso: é o import
# que popula `__subclasses__`. Referenciá-los aqui impede que um "unused import"
# seja removido por engano, levando o guarda junto.
_MODULOS_DE_ERRO = (domain_errors, application_errors)


def _subclasses_concretas() -> set[type[Exception]]:
    """Todas as subclasses das duas raízes de staff definidas no código de produção.

    **O filtro por `restaurant_hub.` não é cosmético.** `__subclasses__()` é um
    registro global e vivo: a subclasse-cobaia que este arquivo define para
    testar a resolução por MRO entraria na varredura, sem entrada própria no
    mapa, e reprovaria a totalidade de forma determinística. Quem topasse com
    essa falha provavelmente afrouxaria a exigência de "entrada própria" — que é
    justamente o gate.
    """
    encontradas: set[type[Exception]] = set()

    def _descer(classe: type[Exception]) -> None:
        for sub in classe.__subclasses__():
            if sub.__module__.startswith("restaurant_hub."):
                encontradas.add(sub)
            _descer(sub)

    _descer(StaffError)
    _descer(StaffApplicationError)
    return encontradas


def test_a_varredura_de_erros_nao_encolheu() -> None:
    """Guarda do guarda — ver o comentário do piso."""
    assert len(_MODULOS_DE_ERRO) == _TOTAL_DE_MODULOS_DE_ERRO
    assert len(_subclasses_concretas()) >= _TOTAL_DE_ERROS_DE_STAFF


def test_ca17_o_mapa_e_total_sobre_staff_error() -> None:
    """CA17 — toda subclasse concreta tem entrada **própria**, não herdada.

    Herdar a entrada do pai não basta: um erro novo tem de ser classificado
    deliberadamente. É a diferença entre "o sistema respondeu alguma coisa" e
    "alguém decidiu o que o sistema responde".
    """
    sem_entrada = sorted(
        classe.__name__
        for classe in _subclasses_concretas()
        if classe not in handlers.STAFF_ERROR_STATUS
    )

    assert sem_entrada == [], f"erros sem entrada própria no mapa de status: {sem_entrada}"


def test_o_mapa_nao_tem_entrada_orfa() -> None:
    """O inverso: entrada para classe que não existe mais é lixo que engana."""
    conhecidas = _subclasses_concretas()

    orfas = sorted(c.__name__ for c in handlers.STAFF_ERROR_STATUS if c not in conhecidas)

    assert orfas == []


def test_o_mapa_tem_exatamente_as_vinte_e_tres_entradas_do_concept() -> None:
    """A contagem é asserção: 23 entradas, 11 do domínio e 12 da aplicação."""
    assert len(handlers.STAFF_ERROR_STATUS) == _TOTAL_DE_ERROS_DE_STAFF


# **As 23 entradas, par a par.** É CA18, e é o único teste deste arquivo que lê o
# **valor** do mapa. Trocar `JobFunctionInUseError` por 422 e
# `SameUnitCopyError` por 409 — duas entradas, faixas ambas já exercitadas —
# sobrevive a tudo o que está acima e morre aqui.
_STATUS_ESPERADO = [
    (application_errors.JobFunctionNotFoundError("jf1"), 404),
    (application_errors.EmployeeNotFoundError("e1"), 404),
    (application_errors.JobFunctionNameAlreadyExistsError("Garçom"), 409),
    (application_errors.JobFunctionAlreadyExistsError("jf1"), 409),
    (application_errors.EmployeeAlreadyExistsError("e1"), 409),
    (application_errors.JobFunctionInUseError("jf1"), 409),
    (application_errors.EmployeeInUseError("e1"), 409),
    (domain_errors.InvalidNameError("funcionário"), 422),
    (domain_errors.InvalidIdentifierError("funcionário"), 422),
    (domain_errors.InvalidWeeklyHoursError("abc"), 422),
    (domain_errors.InvalidDayPeriodError("xpto"), 422),
    (domain_errors.EmptyShiftPreferenceError(), 422),
    (domain_errors.EmptyJobFunctionsError(), 422),
    (domain_errors.InvalidUnavailabilityPeriodError("início deve anteceder o fim"), 422),
    (domain_errors.OverlappingUnavailabilityError(), 422),
    (domain_errors.UnavailabilityNotFoundError(), 422),
    (application_errors.EmployeeRelocationError("e1", "u1", "u2"), 422),
    (application_errors.SameUnitCopyError("u1"), 422),
    # Stage 3.5 — as cinco recusas de login (concept 3.5 §6.1).
    (domain_errors.EmployeeAlreadyHasLoginError("e1"), 409),
    (domain_errors.TerminatedEmployeeLoginError("e1"), 409),
    (application_errors.LoginEmailAlreadyInUseError("ana@x.com"), 409),
    (application_errors.EmployeeHasLoginError("e1"), 409),
    (application_errors.InvalidLoginEmailError("nao-e-email"), 422),
]


def test_ca18_a_verificacao_par_a_par_cobre_as_vinte_e_tres_entradas() -> None:
    """A tabela deste arquivo tem de cobrir o mapa inteiro, senão CA18 é amostra."""
    cobertas = {type(excecao) for excecao, _ in _STATUS_ESPERADO}

    assert cobertas == set(handlers.STAFF_ERROR_STATUS)


@pytest.mark.parametrize(("excecao", "status_esperado"), _STATUS_ESPERADO)
def test_ca18_status_de_cada_excecao(excecao: StaffError, status_esperado: int) -> None:
    """CA18 — o mapa inteiro, exceção a exceção, testado e não presumido."""
    assert handlers.resolve_status(excecao) == status_esperado


# ---------------------------------------------------------------------------
# CA19 (metade estrutural) — a MRO de `UnavailabilityNotFoundError`
# ---------------------------------------------------------------------------


def test_ca19_o_periodo_inexistente_fica_no_dominio_e_e_422() -> None:
    """`UnavailabilityNotFoundError` é regra do agregado, não lookup (ADR 3.9.0001 §3).

    O período é um valor **dentro** do agregado, não um recurso endereçável, e o
    funcionário existe e foi encontrado. Ele fica sob `StaffError` — e não sob a raiz
    de aplicação, onde estão os dois "não encontrado" de recurso — e o mapa o
    classifica como 422.
    """
    assert issubclass(domain_errors.UnavailabilityNotFoundError, StaffError)
    assert not issubclass(domain_errors.UnavailabilityNotFoundError, StaffApplicationError)
    assert (
        handlers.resolve_status(domain_errors.UnavailabilityNotFoundError())
        == handlers.HTTP_UNPROCESSABLE
    )


def test_ca19_os_dois_erros_de_404_sao_de_aplicacao_e_o_mapa_os_diz_404() -> None:
    """A outra ponta: o 404 vem do mapa, e a classe diz só o que ela é (lookup)."""
    for classe in (
        application_errors.JobFunctionNotFoundError,
        application_errors.EmployeeNotFoundError,
    ):
        assert classe.__bases__ == (StaffApplicationError,)
        assert handlers.STAFF_ERROR_STATUS[classe] == handlers.HTTP_NOT_FOUND


# ---------------------------------------------------------------------------
# Resolução por MRO e o default
# ---------------------------------------------------------------------------


def test_resolucao_por_mro_para_subclasse_nao_mapeada() -> None:
    """Subclasse futura herda a classificação do pai em vez de virar 500.

    Isto **não** relaxa a totalidade: CA17 continua exigindo entrada própria de
    toda classe concreta de produção. A herança é a rede de segurança de runtime,
    para o caso de o gate ser burlado.
    """

    class ErroDerivadoDeTeste(application_errors.JobFunctionInUseError):
        """Definida no módulo de teste — excluída da varredura pelo filtro."""

    assert handlers.resolve_status(ErroDerivadoDeTeste("jf1")) == handlers.HTTP_CONFLICT


def test_staff_error_cru_cai_no_default() -> None:
    """A raiz não é entrada do mapa (concept §6.1) — cai no default 422."""
    assert handlers.resolve_status(StaffError("qualquer coisa")) == handlers.HTTP_UNPROCESSABLE


# ---------------------------------------------------------------------------
# O corpo — o discriminador que separa staff do 422 do framework
# ---------------------------------------------------------------------------


def test_o_corpo_de_erro_carrega_o_discriminador_de_staff() -> None:
    """`"type": "staff_error"` é infraestrutura de teste, não enfeite.

    Na faixa 422 esta app tem **duas** origens: um erro de staff e o
    `RequestValidationError` do framework, que o handler compartilhado renderiza
    com corpo constante (`type: "validation_error"`). Sem este discriminador, uma
    varredura que asserisse só `status == 422` ficaria verde contra o erro
    **errado** — e a rota que esquecesse o validador de identificador passaria no
    próprio teste.
    """
    resposta = handlers.build_error_response(domain_errors.InvalidIdentifierError("funcionário"))

    assert resposta.status_code == handlers.HTTP_UNPROCESSABLE
    assert b'"type":"staff_error"' in resposta.body


@pytest.mark.parametrize(("excecao", "status_esperado"), _STATUS_ESPERADO)
def test_o_discriminador_e_o_mesmo_nas_tres_faixas(
    excecao: StaffError, status_esperado: int
) -> None:
    """As três faixas de staff usam **um** discriminador, e o status é que difere.

    Um `type` por faixa daria ao cliente uma segunda forma de distinguir 404 de
    409 de 422 — e a distinção já é o status, que é onde ela pertence.
    """
    resposta = handlers.build_error_response(excecao)

    assert resposta.status_code == status_esperado
    assert b'"type":"staff_error"' in resposta.body


def test_o_corpo_preserva_a_mensagem_da_excecao() -> None:
    """Não há corpo constante em staff, e a assimetria com identity é deliberada.

    As faixas que exigem corpo constante são 401 e 403 — que staff **não**
    produz. As de staff falam de um recurso que o próprio cliente endereçou ou de
    uma invariante que o payload dele violou, e a autorização já correu antes.
    """
    excecao = application_errors.JobFunctionNotFoundError("jf-42")

    assert str(excecao).encode() in handlers.build_error_response(excecao).body


# ---------------------------------------------------------------------------
# Staff não registra 401 nem 403
# ---------------------------------------------------------------------------


def test_staff_nao_registra_entrada_nas_faixas_de_identity() -> None:
    """Uma entrada 401/403 aqui criaria uma segunda faixa **distinguível**.

    As duas faixas são de identity, cujo handler está registrado sobre a app e é
    alcançado por MRO — as exceções sobem cruas do port (L-AG1/L-AG2). Um 403 de
    staff distinguível de um 403 de identity é o oráculo que as duas leis compram
    ao proibir a tradução, e este teste é o que impede alguém de reabri-lo por
    conveniência de mensagem.
    """
    faixas = set(handlers.STAFF_ERROR_STATUS.values())

    assert faixas == {404, 409, 422}


def test_o_registrador_instala_um_handler_unico_sobre_as_duas_raizes() -> None:
    """Um handler, sobre as raízes do BC (ADR 3.9.0001 §4) — não um por classe.

    Registrar por classe faria a totalidade do mapa deixar de importar: a
    exceção sem handler cairia no genérico de `shared` em silêncio, e a Stage
    teria dois lugares capazes de divergir sobre o mesmo erro.
    """
    app = FastAPI()
    handlers.register_staff_error_handlers(app)

    raizes = (StaffError, StaffApplicationError)
    registrados = [chave for chave in app.exception_handlers if chave in raizes]

    assert sorted(registrados, key=lambda c: c.__name__) == sorted(raizes, key=lambda c: c.__name__)
    assert app.exception_handlers[StaffError] is app.exception_handlers[StaffApplicationError]
    assert not [
        chave
        for chave in app.exception_handlers
        if isinstance(chave, type) and issubclass(chave, raizes) and chave not in raizes
    ]


async def test_o_handler_registrado_devolve_a_mesma_resposta_que_o_construtor() -> None:
    """O handler instalado **é** `build_error_response`, e não um segundo caminho.

    Sem esta asserção, o corpo do handler ficaria sem execução até o e2e da
    Task 12 — e um `return JSONResponse(...)` escrito à mão lá dentro, divergindo
    do construtor, passaria por toda a suíte unitária deste arquivo. As duas
    respostas têm de ser byte a byte a mesma coisa.
    """
    app = FastAPI()
    handlers.register_staff_error_handlers(app)
    excecao = application_errors.EmployeeNotFoundError("e-42")

    resposta = await app.exception_handlers[StaffError](None, excecao)

    esperada = handlers.build_error_response(excecao)
    assert resposta.status_code == esperada.status_code
    assert resposta.body == esperada.body


# ---------------------------------------------------------------------------
# Corpo exato para toda classe das duas raízes (Stage 3.9, CA8)
# ---------------------------------------------------------------------------

_MENSAGEM_PLANTADA = "detalhe-plantado"


def _instancia_com_mensagem(classe: type[Exception]) -> Exception:
    """Instância com mensagem conhecida, sem passar pelo `__init__` da classe."""
    excecao = classe.__new__(classe)
    Exception.__init__(excecao, _MENSAGEM_PLANTADA)
    return excecao


@pytest.mark.parametrize(
    "classe", sorted(_subclasses_concretas(), key=lambda c: c.__name__), ids=lambda c: c.__name__
)
def test_corpo_exato_para_toda_classe_das_duas_raizes(classe: type[Exception]) -> None:
    """O oráculo de que a troca de raiz não mudou um byte do corpo (ADR 3.9.0001 §4).

    O discriminador é escrito por extenso, e não lido de `STAFF_ERROR_TYPE`: um
    oráculo que importasse a constante concordaria com ela mesmo que ela mudasse.
    """
    excecao = _instancia_com_mensagem(classe)
    assert isinstance(excecao, StaffError | StaffApplicationError)
    resposta = handlers.build_error_response(excecao)

    assert resposta.status_code == handlers.STAFF_ERROR_STATUS[classe]
    assert json.loads(resposta.body) == {"detail": _MENSAGEM_PLANTADA, "type": "staff_error"}
