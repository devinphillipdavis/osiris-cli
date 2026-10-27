"""osiris.substrate: batch vs interactive horizons and a fixed telemetry shape."""

import platform

import pytest

from osiris import substrate

NODES = {"NODE_ALPHA_MOBILE", "NODE_BETA_COMPUTE", "NODE_GENERIC_EDGE"}


def test_node_type_is_known():
    assert substrate.node_type() in NODES


def test_batch_horizon_matches_the_node():
    expected = 1800.0 if substrate.node_type() == "NODE_BETA_COMPUTE" else 300.0
    assert substrate.execution_timeout_s() == expected
    assert substrate.execution_timeout_s(42) == 42.0


def test_interactive_horizon_default_and_override(monkeypatch):
    monkeypatch.delenv(substrate.INTERACTIVE_TIMEOUT_ENV, raising=False)
    assert substrate.interactive_timeout_s() == 120.0
    monkeypatch.setenv(substrate.INTERACTIVE_TIMEOUT_ENV, "45")
    assert substrate.interactive_timeout_s() == 45.0
    assert substrate.interactive_timeout_s(10) == 10.0


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "nan", "inf"])
def test_bad_interactive_values_fall_back_never_disable(monkeypatch, raw):
    monkeypatch.setenv(substrate.INTERACTIVE_TIMEOUT_ENV, raw)
    assert substrate.interactive_timeout_s() == 120.0


def test_interactive_never_exceeds_batch(monkeypatch):
    monkeypatch.setenv(substrate.INTERACTIVE_TIMEOUT_ENV, "999999")
    assert substrate.interactive_timeout_s() == substrate.execution_timeout_s()


def test_fallback_without_the_mesh(monkeypatch):
    monkeypatch.setattr(substrate, "_mesh", None)
    assert substrate.mesh_available() is False
    assert substrate.node_type() in NODES
    assert substrate.execution_timeout_s() in (300.0, 1800.0)


def test_telemetry_frame_shape():
    ctx = substrate.get_substrate_context()
    assert set(substrate.TELEMETRY_KEYS) <= set(ctx)
    assert ctx["horizon_s"] == substrate.execution_timeout_s()
    assert ctx["w2_distance"] is None and ctx["shannon_entropy"] is None
    assert not platform.node() or platform.node() not in ctx["node_id"]
    assert substrate.get_substrate_context(0.1, 2.0)["shannon_entropy"] == 2.0
    with pytest.raises(ValueError):
        substrate.get_substrate_context(w2_distance=-1)
