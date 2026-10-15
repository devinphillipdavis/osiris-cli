"""
Tests for DNAL Currency Card Kit v2 & 6-Gate Interposition
=========================================================
Verifies DNA-Lang organism synthesis, 6-gate fail-closed interposition,
and claims registration for DNAL Currency Card Kit v2.
"""

import hashlib
import pytest

from osiris_cli import claims
from osiris_cli.dnalang.currency_card_gene import (
    ERC1271_MAGIC_VALUE,
    CurrencyCard6GateValidator,
    generate_currency_card_gene,
)


def test_currency_card_gene_generation():
    gene = generate_currency_card_gene(
        enclave_pubkey_hash="a1b2c3d4e5f60718",
        account_address="0x1234567890123456789012345678901234567890",
    )
    assert "organism CurrencyCardV2" in gene
    assert "quantum_state" in gene
    assert "0x1626ba7e" in gene
    assert "bind_enclave" in gene


def test_6gate_validator_pass():
    validator = CurrencyCard6GateValidator()
    sender = "0x1234567890123456789012345678901234567890"
    pubkey_hash = hashlib.sha256(sender.encode("utf-8")).hexdigest()[:16]

    user_op = {
        "sender": sender,
        "nonce": 1,
        "callData": "0xa9059cbb000000000000000000000000",
        "callGasLimit": 200_000,
    }
    sig = "ed25519_sig_" + "0" * 64

    res = validator.validate_user_operation(
        user_op=user_op,
        enclave_signature=sig,
        expected_pubkey_hash=pubkey_hash,
        coherence_gamma=0.040,
    )
    assert res["status"] == "PASS"
    assert res["magic_value"] == ERC1271_MAGIC_VALUE
    assert res["pqc_hybrid_verified"] is True


def test_6gate_validator_gate1_blocked():
    validator = CurrencyCard6GateValidator()
    user_op = {"sender": "0x1234", "callGasLimit": 100_000}
    # Bad signature
    res = validator.validate_user_operation(user_op, enclave_signature="", expected_pubkey_hash="123")
    assert res["status"] == "BLOCKED"
    assert res["gate"] == 1


def test_6gate_validator_gate2_ast_blocked():
    validator = CurrencyCard6GateValidator()
    sender = "0x1234"
    pubkey_hash = hashlib.sha256(sender.encode("utf-8")).hexdigest()[:16]
    user_op = {
        "sender": sender,
        "callData": "execute os.system('malicious')",
        "callGasLimit": 100_000,
    }
    res = validator.validate_user_operation(user_op, enclave_signature="ed25519_sig_" + "0" * 64, expected_pubkey_hash=pubkey_hash)
    assert res["status"] == "BLOCKED"
    assert res["gate"] == 2


def test_6gate_validator_gate4_coherence_blocked():
    validator = CurrencyCard6GateValidator(coherence_floor=0.092)
    sender = "0x1234"
    pubkey_hash = hashlib.sha256(sender.encode("utf-8")).hexdigest()[:16]
    user_op = {"sender": sender, "callGasLimit": 100_000}
    res = validator.validate_user_operation(
        user_op,
        enclave_signature="ed25519_sig_" + "0" * 64,
        expected_pubkey_hash=pubkey_hash,
        coherence_gamma=0.150,  # Exceeds 0.092
    )
    assert res["status"] == "BLOCKED"
    assert res["gate"] == 4


def test_claims_currency_card_registered():
    matches = claims.match("DNAL Currency Card Kit v2 hardware enclave fail-closed execution")
    assert any(c.id == "CARD_V2_ENCLAVE" for c in matches)

    pqc_matches = claims.match("NIST PQC FIPS 204 ML-DSA migration")
    assert any(c.id == "CARD_V2_PQC" for c in pqc_matches)
