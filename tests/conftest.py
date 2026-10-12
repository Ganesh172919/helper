"""Shared test fixtures isolate all app data and keep native Qt tests deterministic."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Provide one real Qt event loop for widget and worker integration tests."""
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    from maya.ui.widgets import STYLE

    app.setStyleSheet(STYLE)
    return app
