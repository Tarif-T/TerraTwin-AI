import socket

from streamlit.testing.v1 import AppTest

import terratwin.datasets
from terratwin.config import ROOT
from terratwin.datasets import load_prepared


def test_empty_app_is_offline_and_disables_science(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Application must not need network")

    monkeypatch.setattr(socket, "create_connection", no_network)

    def unavailable():
        raise ValueError("No validated scientific profiles loaded: test empty state")

    monkeypatch.setattr(terratwin.datasets, "load_prepared", unavailable)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert any("No validated scientific profiles loaded" in w.value for w in app.warning)
    assert app.button[0].disabled
    next(s for s in app.selectbox if s.label == "Planetary body").select("Moon").run()
    assert not app.exception
    assert app.button[0].disabled
    assert any("LOLA GDR" in caption.value for caption in app.caption)


def test_missing_products_block_loading(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="No validated"):
        load_prepared(tmp_path)
