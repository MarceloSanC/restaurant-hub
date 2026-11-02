"""Todo erro de um BC tem status HTTP declarado — Gate 3 da issue #45.

**Por que na raiz de `tests/unit/`, e não dentro de um BC.** A regra é sobre a
relação entre duas coisas que todo bounded context tem: a sua hierarquia de erro
e o seu mapa de status. Ela não é regra de identity nem de staff — é a mesma
regra aplicada a cada um, e o sujeito é o conjunto. É o raciocínio de
`tests/unit/features/staff/test_bc_independence.py`, que sobe ao nível cuja
fronteira a regra descreve.

**Por que existe, se `test_http_error_handlers.py` já faz isto para identity.**
Porque aquele arquivo faz isto **para identity**, e a forma como ele o faz — três
imports literais do BC no topo — não se estende: um BC novo entra sem gate e
nada fica vermelho. Foi exatamente o que aconteceu com o teste de composition
root, cuja varredura ancorada no próprio pacote de adapters deixou o BC seguinte
descoberto (documentado na docstring de `composition_root.py`). Aqui a
enumeração de bounded contexts é **varredura de pasta**, com lista explícita ao
lado: o BC que nascer sem mapa reprova no dia em que registrar a primeira rota,
sem ninguém lembrar de escrever teste.

**O que um erro sem entrada custa.** O `resolve_status` de cada BC percorre o
`__mro__` e cai num default 422 quando não acha. Um erro de autorização novo,
esquecido no mapa, vira 422 em vez de 403 — silenciosamente, com a suíte verde,
porque nenhum teste de rota o exercita ainda. Isso não é imprecisão de status:
422 diz *"o conteúdo que você enviou viola uma invariante"*, o que é uma
afirmação sobre o payload, e 403 diz *"você não pode"*. Um cliente que
distingue os dois passa a ver uma negação de acesso como erro de formulário.

**A parametrização vazia é o falso-verde deste arquivo, e há guarda contra ela.**
`pytest.mark.parametrize` sobre lista vazia produz **zero** testes e reporta
sucesso. Se a descoberta de BCs com borda HTTP quebrasse — um caminho errado,
uma pasta renomeada —, todas as asserções de exaustividade sumiriam sem deixar
rastro. `test_ha_pelo_menos_um_bc_com_borda_http` é o que impede isso.
"""

import importlib
import pathlib
import types

import pytest
from fastapi import FastAPI

from restaurant_hub.shared.application.errors import ApplicationError
from restaurant_hub.shared.domain.exceptions.base import DomainError

pytestmark = pytest.mark.unit

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "restaurant_hub"
_FEATURES = _SRC / "features"

# Os bounded contexts de hoje. A lista é **explícita** e a asserção seguinte a
# cobra contra a pasta — o par de `test_composition_root_staff.py`. Derivada
# sozinha, ela concordaria com uma varredura quebrada que devolvesse vazio;
# escrita à mão, ela envelhece. As duas juntas resolvem.
_BOUNDED_CONTEXTS = ("identity", "scheduling", "staff")

# Piso de contagem por BC — tripwire contra a enumeração encolher em silêncio.
# `__subclasses__()` só enxerga o que foi importado, então um módulo de erro novo
# que ninguém importasse aqui faria a varredura passar sobre um universo menor
# que o real, e a exaustividade seria verdadeira sobre menos erros do que existem.
#
# Medidos em 2026-08-31: identity 28 (8 de domínio + 20 de aplicação), staff 18.
# Medido em 2026-09-27 (Stage 4.1, Task 01): scheduling 20 — as 20 subclasses de
# `SchedulingError` do concept §4, todas de domínio; `application/errors.py` não
# existe até a 4.3. A raiz não conta (`_subclasses_concretas` desce dela).
# Medido em 2026-10-19 (Stage 4.2, Task 01): scheduling 22 — mais as duas da
# validação (`InvalidValidationConfigError`, `InvalidEvaluationInputError`).
# Medido em 2026-11-01 (Stage 4.3, Task 02): scheduling 34 — mais as 12 de
# `application/errors.py` (concept 4.3 §4).
_TOTAIS_MINIMOS = {"identity": 28, "scheduling": 34, "staff": 18}

# Os módulos de erro que um BC pode ter. É o import deles que popula
# `__subclasses__`, então a lista não é documentação: é o que faz a varredura ver
# o universo inteiro.
#
# **O sufixo é opcional, e a tolerância é estreita.** Um BC anterior à sua camada
# de aplicação não tem `application/errors.py` — foi o caso de scheduling na
# Stage 4.1, cujo `application/` é placeholder vazio até a 4.3. O import cru
# daria `ModuleNotFoundError` e reprovaria o BC novo por não ter código que
# ninguém escreveu ainda. Quem faz a tolerância é `_importar_modulos_de_erro`,
# **por módulo inexistente** e não por falha de import qualquer — e
# `test_cada_bc_tem_ao_menos_um_modulo_de_erro` é o que impede a tolerância de
# esvaziar a varredura.
_MODULOS_DE_ERRO = ("domain.exceptions.errors", "application.errors")

_PACOTE_HTTP = "adapters.inbound.http"
_MODULO_DE_HANDLERS = "error_handlers"


def _bounded_contexts_na_pasta() -> tuple[str, ...]:
    """Os BCs que existem em `features/`, por varredura."""
    return tuple(
        sorted(
            pasta.name
            for pasta in _FEATURES.iterdir()
            if pasta.is_dir() and not pasta.name.startswith(("_", "."))
        )
    )


def _caminho_dos_handlers(bc: str) -> pathlib.Path:
    return _FEATURES / bc / "adapters" / "inbound" / "http" / f"{_MODULO_DE_HANDLERS}.py"


def _tem_borda_http(bc: str) -> bool:
    """True se o BC registra rotas — isto é, se tem mapa de status a cobrar."""
    return _caminho_dos_handlers(bc).exists()


_COM_BORDA_HTTP = tuple(bc for bc in _BOUNDED_CONTEXTS if _tem_borda_http(bc))
_SEM_BORDA_HTTP = tuple(bc for bc in _BOUNDED_CONTEXTS if not _tem_borda_http(bc))


def _raiz_de_erro(bc: str) -> type[DomainError]:
    """A raiz **de domínio** do BC: a única que herda de `DomainError` diretamente.

    Derivada, e não escrita como `{"identity": IdentityError, ...}`: um mapa
    literal exigiria import estático de cada BC neste arquivo, que é exatamente
    a forma que não se estende — e o BC seguinte entraria descoberto.
    """
    modulo = importlib.import_module(f"restaurant_hub.features.{bc}.domain.exceptions.errors")
    raizes = [
        valor
        for valor in vars(modulo).values()
        if isinstance(valor, type)
        and issubclass(valor, DomainError)
        and DomainError in valor.__bases__
    ]
    assert len(raizes) == 1, (
        f"{bc}: esperava uma raiz de erro, achei {[r.__name__ for r in raizes]}"
    )
    return raizes[0]


def _raiz_de_aplicacao(bc: str) -> type[ApplicationError] | None:
    """A raiz **de aplicação** do BC, se houver: subclasse direta de `ApplicationError`.

    Desde a Stage 3.9 (ADR 3.9.0001 §2) cada BC tem até duas raízes, uma por
    significado. Esta é opcional — um BC anterior à sua camada de aplicação não a
    tem —, mas **única** quando existe: duas raízes de aplicação no mesmo BC
    partiriam o que o handler do BC precisa registrar, e a segunda escaparia.
    Derivada pela forma, pelo mesmo motivo de `_raiz_de_erro`.
    """
    nome = f"restaurant_hub.features.{bc}.application.errors"
    modulo = next((m for m in _importar_modulos_de_erro(bc) if m.__name__ == nome), None)
    if modulo is None:
        return None
    raizes = [
        valor
        for valor in vars(modulo).values()
        if isinstance(valor, type)
        and valor.__module__ == nome
        and ApplicationError in valor.__bases__
    ]
    assert len(raizes) <= 1, (
        f"{bc}: esperava no máximo uma raiz de aplicação, achei {[r.__name__ for r in raizes]}"
    )
    return raizes[0] if raizes else None


def _raizes(bc: str) -> tuple[type[Exception], ...]:
    """As raízes do BC — a de domínio sempre, a de aplicação quando existe."""
    aplicacao = _raiz_de_aplicacao(bc)
    dominio: tuple[type[Exception], ...] = (_raiz_de_erro(bc),)
    return dominio if aplicacao is None else (*dominio, aplicacao)


def _importar_modulos_de_erro(bc: str) -> tuple[types.ModuleType, ...]:
    """Popula `__subclasses__` e devolve os módulos de erro que **existem**.

    Sem o import a varredura vê um universo parcial; sem o valor de retorno, cada
    sítio que precisa percorrer os módulos repetiria a lógica de tolerância e os
    dois divergiriam no dia em que um terceiro sufixo entrasse.

    **A tolerância é por módulo inexistente, não por falha de import.** Um
    `ModuleNotFoundError` cujo `name` é exatamente o módulo procurado significa
    "este BC ainda não tem esta camada" (scheduling antes da 4.3). Qualquer outra
    falha — inclusive um `ModuleNotFoundError` de uma dependência *de dentro* do
    módulo, que é o sintoma de um import quebrado — continua propagando: engoli-la
    transformaria erro de código em varredura silenciosamente menor.
    """
    existentes: list[types.ModuleType] = []
    for sufixo in _MODULOS_DE_ERRO:
        nome = f"restaurant_hub.features.{bc}.{sufixo}"
        try:
            existentes.append(importlib.import_module(nome))
        except ModuleNotFoundError as erro:
            if erro.name != nome:
                raise
    return tuple(existentes)


def _subclasses_concretas(bc: str) -> set[type[Exception]]:
    """Todas as subclasses da raiz do BC definidas em código de produção.

    O filtro por `restaurant_hub.` não é cosmético: `__subclasses__()` é um
    registro global e vivo, e uma classe-cobaia definida por outro arquivo de
    teste entraria na varredura sem entrada no mapa, reprovando a exaustividade
    por um motivo que não é o dela.
    """
    _importar_modulos_de_erro(bc)
    encontradas: set[type[Exception]] = set()

    def _descer(classe: type[Exception]) -> None:
        for sub in classe.__subclasses__():
            if sub.__module__.startswith("restaurant_hub."):
                encontradas.add(sub)
            _descer(sub)

    for raiz in _raizes(bc):
        _descer(raiz)
    return encontradas


def _modulo_de_handlers(bc: str) -> types.ModuleType:
    """`adapters/inbound/http/error_handlers.py` do BC.

    Por `importlib` porque o caminho é **calculado** a partir do bounded
    context: é o que faz este arquivo valer para o BC seguinte sem edição.
    """
    return importlib.import_module(
        f"restaurant_hub.features.{bc}.{_PACOTE_HTTP}.{_MODULO_DE_HANDLERS}"
    )


def _mapa_de_status(bc: str) -> dict[type[Exception], int]:
    """O mapa exceção → status do BC, achado pela forma e não pelo nome.

    Procurar `dict` cujas chaves são todas classes de exceção — em vez de
    `getattr(modulo, f"{bc.upper()}_ERROR_STATUS")` — é o que faz este arquivo
    valer para um BC cuja constante se chame outra coisa. A convenção de nome é
    exatamente o tipo de coisa que o BC seguinte quebra sem má intenção, e o
    custo seria o gate sumir em vez de reprovar.
    """
    candidatos = [
        valor
        for valor in vars(_modulo_de_handlers(bc)).values()
        if isinstance(valor, dict)
        and valor
        and all(isinstance(chave, type) and issubclass(chave, Exception) for chave in valor)
    ]
    assert len(candidatos) == 1, f"{bc}: esperava um mapa de status, achei {len(candidatos)}"
    return candidatos[0]


def _raizes_sem_handler(
    raizes: tuple[type[Exception], ...], registrados: dict[object, object]
) -> list[str]:
    """As raízes do BC que o registro da borda deixou sem handler.

    Isolada, como `_sem_entrada`, para que o violador plantado a exercite sem
    gravar em `src/` um registro incompleto. Não há rede genérica para
    `ApplicationError` (ADR 3.9.0001 §5): uma raiz sem handler é um erro do BC que
    responde 500.
    """
    return sorted(raiz.__name__ for raiz in raizes if raiz not in registrados)


def _violacoes_de_raiz_unica(
    classes: list[type[Exception]], raizes: tuple[type[Exception], ...]
) -> list[str]:
    """As classes que não têm **uma** base e **uma** raiz do BC (concept 3.9 §5.1).

    Isolada para que os violadores plantados a exercitem sem gravar em `src/` uma
    classe com duas raízes — que é exatamente a forma que a Stage 3.9 removeu.
    """
    violacoes: list[str] = []
    for classe in classes:
        if classe in raizes:
            continue
        alcancadas = [raiz.__name__ for raiz in raizes if issubclass(classe, raiz)]
        if len(classe.__bases__) != 1 or len(alcancadas) != 1:
            bases = [base.__name__ for base in classe.__bases__]
            violacoes.append(f"{classe.__name__} (bases {bases}; raízes {alcancadas})")
    return sorted(violacoes)


def _classes_dos_modulos_de_erro(bc: str) -> list[type[Exception]]:
    """Toda classe de exceção **definida** nos módulos de erro do BC."""
    return [
        valor
        for modulo in _importar_modulos_de_erro(bc)
        for valor in vars(modulo).values()
        if isinstance(valor, type)
        and issubclass(valor, Exception)
        and valor.__module__ == modulo.__name__
    ]


def _registro_da_borda(bc: str) -> FastAPI:
    """Uma app com **só** o registro de handlers do BC aplicado.

    A função de registro é achada pela forma — a única função `register_*` definida
    no módulo de handlers —, pelo mesmo motivo de `_mapa_de_status`.
    """
    modulo = _modulo_de_handlers(bc)
    funcoes = [
        valor
        for nome, valor in vars(modulo).items()
        if nome.startswith("register_")
        and callable(valor)
        and getattr(valor, "__module__", None) == modulo.__name__
    ]
    assert len(funcoes) == 1, f"{bc}: esperava uma função de registro, achei {len(funcoes)}"
    app = FastAPI()
    funcoes[0](app)
    return app


def _sem_entrada(classes: set[type[Exception]], mapa: dict[type[Exception], int]) -> list[str]:
    """A comparação do Gate 3, isolada da descoberta.

    Ela é uma função à parte para que o violador plantado possa exercitá-la com
    um universo montado à mão. Embutida no teste, a única forma de plantar um
    erro sem status seria gravá-lo em `src/` — e o idioma deste repositório é
    que o código violador nunca entra no repositório, onde seria copiado por
    analogia.
    """
    return sorted(classe.__name__ for classe in classes if classe not in mapa)


# ---------------------------------------------------------------------------
# A enumeração de bounded contexts, e as guardas dela
# ---------------------------------------------------------------------------


def test_a_lista_de_bounded_contexts_cobre_a_pasta_features() -> None:
    """Um BC novo reprova aqui antes de escapar de todas as asserções abaixo.

    Sem esta asserção, um terceiro bounded context entraria sem mapa de status e
    sem ninguém notar: as parametrizações são construídas a partir da lista, e a
    lista não o conheceria.
    """
    assert set(_bounded_contexts_na_pasta()) == set(_BOUNDED_CONTEXTS)


def test_ha_pelo_menos_um_bc_com_borda_http() -> None:
    """A guarda contra a parametrização vazia — o falso-verde deste arquivo.

    `parametrize` sobre lista vazia produz zero testes e reporta sucesso. Se a
    descoberta quebrasse (caminho errado, pasta renomeada — foi `adapters/in/`
    virando `adapters/inbound/` na própria #45), toda a exaustividade sumiria
    em silêncio, e o
    relatório do pytest diria exatamente o mesmo de antes.
    """
    assert _COM_BORDA_HTTP, (
        f"nenhum BC de {_BOUNDED_CONTEXTS} tem "
        f"adapters/inbound/http/{_MODULO_DE_HANDLERS}.py — a descoberta quebrou, e "
        f"sem esta asserção as demais teriam sumido sem sintoma"
    )


def test_bc_sem_mapa_de_status_tambem_nao_tem_borda_http() -> None:
    """A ausência é verificada, não presumida.

    Um BC pode legitimamente não ter mapa de status — enquanto não registrar
    rota nenhuma. O que não pode é ter `adapters/inbound/` **e** escapar da
    exaustividade: seria o mapa faltando exatamente onde ele passa a importar.

    **Não é parametrizado, e a escolha é sobre o relatório.** `_SEM_BORDA_HTTP`
    era `("staff",)` até a Stage 3.6, ficou vazio quando os dois BCs ganharam
    borda, e voltou a `("scheduling",)` na Stage 4.1 — o BC novo é domínio puro, e
    o mapa de status dele é da 4.5. Com `parametrize`, um conjunto vazio vira uma
    linha `SKIPPED` no relatório, e neste repositório teste pulado é o sintoma que
    se aprendeu a investigar (o "verde por não ter olhado" da Stage 1.2). Aqui não
    há nada pulado: a afirmação é sobre um conjunto que pode estar vazio, e quem
    garante que o **outro** lado não esvaziou é
    `test_ha_pelo_menos_um_bc_com_borda_http`.
    """
    com_borda_sem_mapa = sorted(
        bc for bc in _SEM_BORDA_HTTP if (_FEATURES / bc / "adapters" / "inbound").exists()
    )

    assert com_borda_sem_mapa == [], (
        f"BCs com adapters/inbound/ e sem {_MODULO_DE_HANDLERS}.py: "
        f"{com_borda_sem_mapa}. As rotas deles respondem pelo handler genérico, "
        f"que só conhece DomainError (422) e não responde por ApplicationError"
    )


# ---------------------------------------------------------------------------
# Gate 3 — a exaustividade do mapa, por bounded context
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bc", _BOUNDED_CONTEXTS)
def test_cada_bc_tem_ao_menos_um_modulo_de_erro(bc: str) -> None:
    """A guarda da tolerância a sufixo ausente — o outro falso-verde deste arquivo.

    `_importar_modulos_de_erro` passou a ignorar o módulo de erro que não existe,
    para que um BC anterior à sua camada de aplicação (scheduling até a 4.3) não
    reprovasse por código que ninguém escreveu. O preço é que um BC que
    **renomeasse os dois** sufixos ficaria com universo vazio: `_raiz_de_erro`
    reprovaria por não achar raiz — mas só porque hoje ele importa o módulo de
    domínio por conta própria, e essa coincidência não é a propriedade que se quer
    garantir. Aqui a propriedade é direta, e é irmã de
    `test_ha_pelo_menos_um_bc_com_borda_http`: a tolerância nunca esvazia a
    varredura.
    """
    assert _importar_modulos_de_erro(bc), (
        f"{bc}: nenhum dos módulos {_MODULOS_DE_ERRO} existe — a tolerância a "
        f"sufixo ausente esvaziou a varredura, e a exaustividade abaixo passaria "
        f"a ser verdade vácua"
    )


@pytest.mark.parametrize("bc", _BOUNDED_CONTEXTS)
def test_a_varredura_de_erros_do_bc_nao_encolheu(bc: str) -> None:
    """Guarda do guarda, e vale para BC sem borda HTTP também.

    A exaustividade é uma afirmação sobre um universo, e `__subclasses__()` só
    enxerga o que foi importado. Um módulo de erro novo que ninguém importasse
    aqui faria a varredura passar sobre menos erros do que existem, e o mapa
    seria "total" sobre um recorte.
    """
    assert len(_subclasses_concretas(bc)) >= _TOTAIS_MINIMOS[bc]


@pytest.mark.parametrize("bc", _BOUNDED_CONTEXTS)
def test_toda_excecao_definida_nos_modulos_de_erro_do_bc_herda_da_raiz(bc: str) -> None:
    """O universo da exaustividade é "toda exceção do BC", não "toda subclasse da raiz".

    `_subclasses_concretas` desce da raiz (`IdentityError`, `StaffError`). Um erro
    futuro em `application/errors.py` que herdasse direto de `DomainError` — sem
    passar pela raiz — ficaria **fora** desse universo, e cairia no 422 do handler
    genérico com a exaustividade verde. Este teste fecha o quantificador do Gate 3
    pelo outro lado: toda classe de exceção **definida** nos módulos de erro do BC
    é subclasse da raiz dele, e portanto entra na varredura.

    Hoje cada BC prova isso no seu próprio `test_errors.py`, por varredura de
    módulo — a forma que não se estende ao terceiro BC. Aqui é por bounded
    context, com a mesma enumeração de pasta das outras asserções.
    """
    raizes = _raizes(bc)
    fora: list[str] = []
    for modulo in _importar_modulos_de_erro(bc):
        fora.extend(
            f"{modulo.__name__}.{nome}"
            for nome, valor in vars(modulo).items()
            if isinstance(valor, type)
            and issubclass(valor, Exception)
            and valor.__module__ == modulo.__name__
            and valor not in raizes
            and not issubclass(valor, raizes)
        )

    assert fora == [], (
        f"{bc}: exceções definidas fora das raízes {[r.__name__ for r in raizes]}: {fora}. "
        f"Elas não entram na varredura de exaustividade e nenhum handler do BC as alcança."
    )


@pytest.mark.parametrize("bc", _COM_BORDA_HTTP)
def test_todo_bc_com_borda_registra_handler_em_cada_raiz(bc: str) -> None:
    """A segunda raiz só é segura se o handler do BC também estiver nela.

    Desde a Stage 3.9 um BC tem duas raízes, e o handler único precisa ser
    registrado sobre **cada** uma: uma subclasse da raiz esquecida não acharia
    handler algum. O mapa total não basta — ele diz que status cada erro teria, não
    que alguém o consulta.
    """
    registrados = dict(_registro_da_borda(bc).exception_handlers)

    assert _raizes_sem_handler(_raizes(bc), registrados) == [], (
        f"{bc}: raiz de erro sem handler registrado na borda"
    )


def test_uma_raiz_sem_handler_reprova() -> None:
    """O violador plantado do registro: a guarda já viu um positivo."""
    bc = _COM_BORDA_HTTP[0]
    raizes = _raizes(bc)
    dominio_e_aplicacao = 2
    assert len(raizes) == dominio_e_aplicacao, f"{bc}: o plantio pressupõe as duas raízes"
    so_a_primeira = {raizes[0]: object()}

    assert _raizes_sem_handler(raizes, so_a_primeira) == [raizes[1].__name__]


@pytest.mark.parametrize("bc", _COM_BORDA_HTTP)
def test_o_mapa_do_bc_e_total_sobre_a_raiz_de_erro(bc: str) -> None:
    """Gate 3 — toda subclasse concreta tem entrada **própria**, não herdada.

    "Própria" é o ponto. `resolve_status` percorre o `__mro__`, então uma
    subclasse sem entrada herda a classificação do pai em runtime — o que é
    desejável como degradação, e péssimo como gate: um erro de autorização novo
    herdando de um pai 422 vira 422, e nada reclama.
    """
    faltando = _sem_entrada(_subclasses_concretas(bc), _mapa_de_status(bc))

    assert faltando == [], (
        f"{bc}: erro sem status declarado: {faltando}. Sem entrada própria "
        f"eles caem no default 422 — inclusive um 403, que passaria a se "
        f"apresentar ao cliente como erro de conteúdo do payload."
    )


@pytest.mark.parametrize("bc", _COM_BORDA_HTTP)
def test_o_mapa_do_bc_nao_tem_entrada_orfa(bc: str) -> None:
    """A outra direção: entrada para erro que já não existe.

    Órfã não reprova nada e nunca reprovará, e ainda faz o mapa parecer mais
    cuidadoso do que é. É a mesma falha de uma allowlist com entrada morta.
    """
    conhecidas = _subclasses_concretas(bc)
    orfas = sorted(classe.__name__ for classe in _mapa_de_status(bc) if classe not in conhecidas)

    assert orfas == [], f"{bc}: mapa declara status para erro inexistente: {orfas}"


@pytest.mark.parametrize("bc", _COM_BORDA_HTTP)
def test_o_mapa_do_bc_so_declara_status_da_familia_4xx(bc: str) -> None:
    """Nenhum erro de negócio é classificado como sucesso nem como 5xx.

    Um `200` no mapa transformaria uma exceção em resposta bem-sucedida, e um
    `500` diria ao cliente que a culpa foi do servidor num caso em que o BC sabe
    exatamente o que houve — que é o modo de falha do `ValueError` cru que a #45
    também fechou do lado de `shared/` (Gate 7).
    """
    minimo, maximo = 400, 499
    fora = sorted(
        (classe.__name__, status)
        for classe, status in _mapa_de_status(bc).items()
        if not minimo <= status <= maximo
    )

    assert fora == [], f"{bc}: status fora da família 4xx: {fora}"


# ---------------------------------------------------------------------------
# O violador plantado
# ---------------------------------------------------------------------------


def test_um_erro_sem_entrada_no_mapa_reprova() -> None:
    """Guarda que nunca viu um positivo não é guarda.

    A asserção de exaustividade é uma varredura que devolve lista vazia quando o
    código está limpo — e devolveria lista vazia também se estivesse quebrada.
    Aqui `_sem_entrada` recebe o universo real **mais** uma subclasse plantada,
    que é exatamente o que uma Stage futura produz por esquecimento: um erro
    novo que ninguém acrescentou ao mapa.

    A cobaia é criada com `type()`, num módulo fora de `restaurant_hub.` — que é
    o filtro de `_subclasses_concretas`. Sem isso ela ficaria registrada em
    `__subclasses__()` e reprovaria os testes reais por um motivo que não é o
    deles; a última asserção cobra essa propriedade em vez de confiar nela.
    """
    bc = _COM_BORDA_HTTP[0]
    plantado = type("ErroPlantadoSemStatus", (_raiz_de_erro(bc),), {})
    universo = _subclasses_concretas(bc) | {plantado}

    assert _sem_entrada(universo, _mapa_de_status(bc)) == ["ErroPlantadoSemStatus"]
    assert not plantado.__module__.startswith("restaurant_hub."), (
        "a cobaia entraria na varredura real e reprovaria a exaustividade por um "
        "motivo que não é o dela"
    )


def test_um_erro_com_entrada_no_mapa_nao_reprova() -> None:
    """A outra direção: `_sem_entrada` não acusa quem está declarado.

    Sem este caso, uma implementação que devolvesse **todos** os nomes passaria
    no teste acima. Falso positivo num gate de exaustividade é pior que falso
    negativo: a saída de quem o vê é remover a exigência de entrada própria, que
    é o gate inteiro.
    """
    bc = _COM_BORDA_HTTP[0]
    plantado = type("ErroPlantadoComStatus", (_raiz_de_erro(bc),), {})
    universo = _subclasses_concretas(bc) | {plantado}
    mapa = {**_mapa_de_status(bc), plantado: 418}

    assert _sem_entrada(universo, mapa) == []


# ---------------------------------------------------------------------------
# Raiz única (Stage 3.9, concept §5.1 e CA2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bc", _BOUNDED_CONTEXTS)
def test_toda_classe_de_erro_do_bc_tem_uma_base_e_uma_raiz_do_proprio_bc(bc: str) -> None:
    """Nenhuma classe herda de duas raízes — nem para ordenar a MRO para o framework.

    Até a Stage 3.9 os erros de "não encontrado" herdavam `(RaizDoBC, NotFoundError)`
    nesta ordem, para que o lookup de handler achasse um antes do outro. O status hoje
    sai do mapa do adapter (ADR 3.9.0001), e a hierarquia diz só o que o erro é.
    """
    assert _violacoes_de_raiz_unica(_classes_dos_modulos_de_erro(bc), _raizes(bc)) == []


def test_uma_classe_com_duas_raizes_reprova() -> None:
    """Violador plantado: a herança dupla que a Stage 3.9 removeu."""
    bc = _COM_BORDA_HTTP[0]
    dominio, aplicacao = _raizes(bc)
    plantado = type("ErroPlantadoComDuasRaizes", (dominio, aplicacao), {})

    assert _violacoes_de_raiz_unica([plantado], (dominio, aplicacao)) == [
        f"ErroPlantadoComDuasRaizes (bases {[dominio.__name__, aplicacao.__name__]}; "
        f"raízes {[dominio.__name__, aplicacao.__name__]})"
    ]


def test_uma_classe_sob_application_error_direto_reprova() -> None:
    """Violador plantado: pular a raiz do BC deixa o erro fora do handler dele."""
    bc = _COM_BORDA_HTTP[0]
    plantado = type("ErroPlantadoSemRaizDoBC", (ApplicationError,), {})

    assert _violacoes_de_raiz_unica([plantado], _raizes(bc)) == [
        "ErroPlantadoSemRaizDoBC (bases ['ApplicationError']; raízes [])"
    ]


def test_uma_classe_com_uma_raiz_nao_reprova() -> None:
    """A outra direção: a forma correta não é acusada."""
    bc = _COM_BORDA_HTTP[0]
    dominio, aplicacao = _raizes(bc)
    plantadas: list[type[Exception]] = [
        type("ErroPlantadoDeDominio", (dominio,), {}),
        type("ErroPlantadoDeAplicacao", (aplicacao,), {}),
    ]

    assert _violacoes_de_raiz_unica(plantadas, (dominio, aplicacao)) == []


@pytest.mark.parametrize("bc", _BOUNDED_CONTEXTS)
def test_as_raizes_do_bc_tem_so_a_base_de_shared(bc: str) -> None:
    """A raiz também tem uma base só: `DomainError` ou `ApplicationError`.

    `_violacoes_de_raiz_unica` pula as raízes, e `_raiz_de_erro` só exige que
    `DomainError` esteja entre as bases — uma raiz `(DomainError, ValueError)`
    passaria pelos dois.
    """
    raizes = _raizes(bc)

    assert raizes[0].__bases__ == (DomainError,)
    assert all(raiz.__bases__ == (ApplicationError,) for raiz in raizes[1:])
