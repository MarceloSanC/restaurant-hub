"""Testes do adapter `Sha256SetupTokenIssuer` (Stage 2.5, CA3)."""

import hashlib

from restaurant_hub.features.identity.adapters.out.security.setup_token_issuer import (
    Sha256SetupTokenIssuer,
)
from restaurant_hub.features.identity.application.ports.out.setup_token_issuer import (
    SetupTokenIssuer,
)

# ~43 caracteres para 32 bytes em base64url. A asserção é sobre a ordem de
# grandeza, não sobre o número exato: `token_urlsafe` remove o padding, então o
# comprimento varia com o conteúdo.
_MINIMO_DE_CARACTERES = 40


def test_adapter_conforma_ao_port() -> None:
    issuer: SetupTokenIssuer = Sha256SetupTokenIssuer()

    assert issuer is not None


class TestIssue:
    def test_lei_do_port_vale_para_o_adapter_real(self) -> None:
        """CA3 — `fingerprint(t.value) == t.fingerprint`.

        Asserido **via o método**, e não comparando dois campos entre si: o
        defeito que a lei existe para pegar é justamente a fórmula duplicada,
        que uma comparação de campos não enxergaria.
        """
        issuer = Sha256SetupTokenIssuer()

        emitido = issuer.issue()

        assert issuer.fingerprint(emitido.value) == emitido.fingerprint

    def test_duas_emissoes_produzem_valores_distintos(self) -> None:
        issuer = Sha256SetupTokenIssuer()

        assert issuer.issue().value != issuer.issue().value

    def test_valor_tem_entropia_suficiente(self) -> None:
        """Um token curto seria enumerável numa rota pública sem rate limit."""
        emitido = Sha256SetupTokenIssuer().issue()

        assert len(emitido.value) >= _MINIMO_DE_CARACTERES

    def test_valor_e_seguro_para_url(self) -> None:
        """O token viaja num link de e-mail; caractere que exige escape quebra."""
        valor = Sha256SetupTokenIssuer().issue().value

        assert all(caractere.isalnum() or caractere in "-_" for caractere in valor)

    def test_fingerprint_nao_e_o_valor(self) -> None:
        """Se fossem iguais, o banco guardaria o token utilizável."""
        emitido = Sha256SetupTokenIssuer().issue()

        assert emitido.fingerprint != emitido.value


class TestFingerprint:
    def test_e_deterministico(self) -> None:
        issuer = Sha256SetupTokenIssuer()

        assert issuer.fingerprint("abc") == issuer.fingerprint("abc")

    def test_valores_diferentes_produzem_fingerprints_diferentes(self) -> None:
        issuer = Sha256SetupTokenIssuer()

        assert issuer.fingerprint("abc") != issuer.fingerprint("abd")

    def test_e_sha256_hexadecimal(self) -> None:
        """Pinar o algoritmo é o que torna a migration reproduzível.

        Se a derivação mudasse, todo token em voo deixaria de ser encontrável —
        e a falha apareceria como "todo convite é inválido", que parece bug de
        autenticação e não de configuração.
        """
        issuer = Sha256SetupTokenIssuer()

        esperado = hashlib.sha256(b"abc").hexdigest()

        assert issuer.fingerprint("abc") == esperado

    def test_aceita_valor_com_caractere_nao_ascii(self) -> None:
        """`encode("utf-8")` explícito — sem ele, o default dependeria do locale."""
        issuer = Sha256SetupTokenIssuer()

        assert issuer.fingerprint("ação") == hashlib.sha256("ação".encode()).hexdigest()
