"""Configuração compartilhada da suíte (fork Clippa)."""

import pytest


@pytest.fixture(autouse=True)
def _no_network_translation(monkeypatch):
    """A tradução PT→EN dos termos (app/services/translate.py) chama MyMemory/Google
    pela rede. Teste unitário não pode depender disso: devolve os termos intactos."""
    from app.services import translate

    monkeypatch.setattr(translate, "translate_terms_to_english", lambda terms: list(terms))
