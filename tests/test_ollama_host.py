"""OLLAMA_HOST uses the server's convention (bare host, host:port, bind address); clients
need a URL."""

import pytest

from osiris_cli.providers.ollama_compat import OllamaCompatibilityProvider, ollama_base_url


@pytest.mark.parametrize("raw, url", [
    ("", "http://localhost:11434"),
    ("http://localhost:11434/", "http://localhost:11434"),
    ("0.0.0.0", "http://127.0.0.1:11434"),
    ("0.0.0.0:11434", "http://127.0.0.1:11434"),
    ("127.0.0.1:8080", "http://127.0.0.1:8080"),
    ("gpu-box", "http://gpu-box:11434"),
    ("https://ollama.example", "https://ollama.example:443"),
    ("http://[::1]:11434", "http://[::1]:11434"),
    ("[::]", "http://127.0.0.1:11434"),
])
def test_ollama_base_url(raw, url):
    assert ollama_base_url(raw) == url


def test_provider_and_console_read_the_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0")
    assert OllamaCompatibilityProvider().host == "http://127.0.0.1:11434"
    assert OllamaCompatibilityProvider(host="http://h:1").host == "http://h:1"
