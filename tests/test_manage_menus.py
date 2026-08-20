"""
Pin the "Manage Abstracts" / "Manage Concrete" menu bar entries.

Neither menu is written out by hand.  ``App._createActions`` builds one
``QAction`` per class yielded by ``PydAbstract.get_managables()`` /
``PydConcrete.get_managables()``, labels it ``Manage <ClassName minus "Pyd">``,
and ``_connectActions`` wires each one to ``cls.manage(parent)`` -- which opens an
``OmniManager`` for that type.  Three things can silently break a menu item:

* the label a class produces and the label the connect-time lookup searches for
  drift apart (``.replace('Pyd', '')`` on one side, a hand-written string on the
  other), so the action ends up connected to nothing and clicking it does zilch;
* ``get_managables`` starts yielding something unmanageable (an association row,
  or a class with no described fields), so the menu grows an item whose manager
  is empty or blows up; and
* a manager fails to build or to render its ``--New--`` form for one particular
  type, which only shows up when someone picks that one menu entry.

These tests cover all three.  The contract half needs no Qt; the wiring and
manager halves build the real ``App`` / ``OmniManager`` under offscreen Qt and so
skip cleanly when PyQt6 + WebEngine are unavailable, exactly like
``test_widgets``.
"""
from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _managable_groups():
    """(abstract, concrete) lists of managable pydantic classes."""
    from backend.validators.pydant import PydAbstract, PydConcrete

    return list(PydAbstract.get_managables()), list(PydConcrete.get_managables())


def _label(cls) -> str:
    """The menu label App builds for a managable class."""
    return f"Manage {cls.__name__.replace('Pyd', '')}"


# --------------------------------------------------------------------------- #
# 1. The get_managables contract -- no Qt required.                           #
# --------------------------------------------------------------------------- #
def test_both_menus_offer_managable_classes():
    """Each menu is populated, and never from association rows."""
    abstract, concrete = _managable_groups()
    assert abstract, "Manage Abstracts would be empty"
    assert concrete, "Manage Concrete would be empty"
    for cls in abstract + concrete:
        assert "association" not in cls.__name__.lower(), (
            f"{cls.__name__} is an association class and should not be managable"
        )


def test_every_managable_has_fields_to_edit():
    """
    A managable with no described fields opens a manager with nothing in it.
    ``get_managables`` filters on ``described_fields`` for exactly this reason;
    pin that the survivors really do carry fields.
    """
    abstract, concrete = _managable_groups()
    empty = [cls.__name__ for cls in abstract + concrete if len(cls.described_fields) == 0]
    assert not empty, f"managable classes with no editable fields: {empty}"


def test_abstract_and_concrete_menus_do_not_overlap():
    """A class belongs to one menu or the other, never both."""
    abstract, concrete = _managable_groups()
    shared = {c.__name__ for c in abstract} & {c.__name__ for c in concrete}
    assert not shared, f"classes claimed by both menus: {shared}"


# --------------------------------------------------------------------------- #
# Qt fixture, shared by the wiring and manager tests below.                    #
# --------------------------------------------------------------------------- #
pytest.importorskip("PyQt6.QtWidgets", reason="PyQt6 is required for the menu tests")
pytest.importorskip("PyQt6.QtWebEngineWidgets", reason="PyQt6-WebEngine is required")


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["", "--no-sandbox"])
    yield app
    app.processEvents()


@pytest.fixture()
def main_window(qapp, graph):
    """The real main window, built against the seeded database."""
    import tools
    from frontend.widgets.app import App

    window = App(ctx=tools.ctx)
    try:
        yield window
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


# --------------------------------------------------------------------------- #
# 2. The menu bar App actually builds.                                        #
# --------------------------------------------------------------------------- #
def test_menu_bar_has_both_manage_menus(main_window):
    """Both menus are present on the bar."""
    titles = [a.menu().title() for a in main_window.menuBar().actions() if a.menu()]
    assert any("Manage Abstract" in t for t in titles), f"no Manage Abstracts menu among {titles}"
    assert any("Manage Concrete" in t for t in titles), f"no Manage Concrete menu among {titles}"


def test_each_menu_has_one_action_per_managable(main_window):
    """
    The actions App built match ``get_managables`` one for one, by label.

    Uses the same ``.replace('Pyd', '')`` label the app uses, so a change to the
    naming scheme on either side surfaces here.
    """
    abstract, concrete = _managable_groups()
    assert [a.text() for a in main_window.abstractActions] == [_label(c) for c in abstract]
    # NB: the attribute is spelled ``concreateActions`` in the app.
    assert [a.text() for a in main_window.concreateActions] == [_label(c) for c in concrete]


def test_every_manage_action_resolves_to_a_class(main_window):
    """
    Every action's label must match exactly one managable class.

    This mirrors the ``next(...)`` lookup in ``App._connectActions``: if the label
    the action carries is not reproduced by any class's ``Manage <name>``, that
    lookup returns ``None`` and the action is wired to nothing -- a menu entry
    that does nothing when clicked.
    """
    abstract, concrete = _managable_groups()
    orphans = []
    for action, classes in ((main_window.abstractActions, abstract),
                            (main_window.concreateActions, concrete)):
        for act in action:
            match = next((c for c in classes if _label(c) == act.text()), None)
            if match is None:
                orphans.append(act.text())
    assert not orphans, f"menu actions that resolve to no class (dead items): {orphans}"


def test_abstract_actions_are_power_user_gated(main_window):
    """
    Managing abstract catalog types is restricted to power users; managing
    concrete records is not.  ``_createMenuBar`` disables the abstract actions
    when ``is_power_user()`` is false.
    """
    from tools import is_power_user

    expected = is_power_user()
    assert all(a.isEnabled() == expected for a in main_window.abstractActions), (
        f"abstract actions should be enabled == is_power_user() ({expected})"
    )
    assert all(a.isEnabled() for a in main_window.concreateActions), (
        "concrete actions should always be enabled"
    )


# --------------------------------------------------------------------------- #
# 3. The manager each menu item opens.                                        #
#                                                                              #
#    Clicking an item calls ``cls.manage(parent)`` -> ``OmniManager(parent,    #
#    object_type=cls)``.  Build that manager directly (no ``exec``, which would #
#    block) for every managable, so a type that cannot open its own manager     #
#    fails here instead of the first time a user selects it.                   #
# --------------------------------------------------------------------------- #
def test_every_managable_opens_its_manager(qapp, graph):
    from PyQt6.QtWidgets import QDialog, QWidget
    from frontend.widgets.omni_manager_pydant import OmniManager

    abstract, concrete = _managable_groups()
    parent = QWidget()
    failures = []
    try:
        for cls in abstract + concrete:
            try:
                dlg = OmniManager(parent=parent, object_type=cls)
                assert isinstance(dlg, QDialog)
                assert dlg.sql_type.__name__ == cls.__name__.replace("Pyd", ""), (
                    f"{cls.__name__}: manager bound to {dlg.sql_type.__name__}"
                )
                assert dlg.windowTitle() == f"Manage {dlg.sql_type.__name__}"
                dlg.deleteLater()
            except Exception as exc:  # noqa: BLE001 - report which type broke
                failures.append(f"{cls.__name__}: {type(exc).__name__}: {exc}")
    finally:
        parent.deleteLater()
        qapp.processEvents()
    assert not failures, "managers failed to open:\n  " + "\n  ".join(failures)


def test_every_managable_renders_a_new_entry_form(qapp, graph):
    """
    Selecting ``--New--`` builds a blank entry via ``object_type()`` and renders
    ``pydant.html_form``.  Empty construction or a broken form template for one
    type would otherwise only fail when a user picks that one manager and clicks
    New.
    """
    from PyQt6.QtWidgets import QWidget
    from frontend.widgets.omni_manager_pydant import OmniManager

    abstract, concrete = _managable_groups()
    parent = QWidget()
    failures = []
    try:
        for cls in abstract + concrete:
            try:
                dlg = OmniManager(parent=parent, object_type=cls)
                html = dlg.update_selection("--New--")
                if not (html and html.strip()):
                    failures.append(f"{cls.__name__}: --New-- form rendered empty")
                dlg.deleteLater()
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{cls.__name__}: {type(exc).__name__}: {exc}")
    finally:
        parent.deleteLater()
        qapp.processEvents()
    assert not failures, "--New-- forms failed:\n  " + "\n  ".join(failures)
