"""
Render the Jinja templates the way the application does.

Every detail pane in the UI is HTML produced by ``PydConcrete.to_html`` and shown
inside a ``QWebEngineView``. That matters for testing because a template error
inside a WebEngine view is close to invisible: Jinja's ``Undefined`` renders as an
empty string rather than raising, a JavaScript exception goes to a console nobody
is watching, and a broken pane just looks blank.

So these tests go through the real path -- ``sql -> to_pydantic -> to_html`` --
rather than rendering templates with hand-built context. Hand-built context tends
to be shaped like the template already expects, which is precisely the assumption
worth testing.

``test_undefined_variables_are_caught`` re-renders under a strict environment,
where referencing a name the context does not provide is an error instead of an
empty string. That is the check that finds typo'd variable names.
"""
from __future__ import annotations

import pytest


def _templates_dir():
    from tools import jinja_template_loading

    env = jinja_template_loading()
    from pathlib import Path

    return Path(env.loader.searchpath[0])


# --------------------------------------------------------------------------- #
# The real render path.                                                        #
# --------------------------------------------------------------------------- #
def test_run_details_render(graph):
    html = graph["runs"][0].to_pydantic().to_html()
    assert html.strip(), "run details rendered empty"
    assert graph["runs"][0].rsl_plate_number in html


def test_clientsubmission_details_render(graph):
    submission = graph["submissions"][0]
    html = submission.to_pydantic().to_html()
    assert html.strip(), "submission details rendered empty"
    assert submission.submitter_plate_id in html


def test_sample_details_render(graph):
    html = graph["samples"][0].to_pydantic().to_html()
    assert html.strip(), "sample details rendered empty"


def test_every_seeded_run_renders(graph):
    """A template that only works for the first row is not working."""
    failures = []
    for run in graph["runs"]:
        try:
            if not run.to_pydantic().to_html().strip():
                failures.append(f"{run.rsl_plate_number}: rendered empty")
        except Exception as exc:
            failures.append(f"{run.rsl_plate_number}: {type(exc).__name__}: {exc}")
    assert not failures, "run rendering failed:\n  " + "\n  ".join(failures)


def test_every_seeded_submission_renders(graph):
    failures = []
    for submission in graph["submissions"]:
        try:
            if not submission.to_pydantic().to_html().strip():
                failures.append(f"{submission.submitter_plate_id}: rendered empty")
        except Exception as exc:
            failures.append(f"{submission.submitter_plate_id}: "
                            f"{type(exc).__name__}: {exc}")
    assert not failures, "submission rendering failed:\n  " + "\n  ".join(failures)


# --------------------------------------------------------------------------- #
# Template hygiene.                                                            #
# --------------------------------------------------------------------------- #
def test_all_templates_parse():
    """
    Every template must at least compile.

    A syntax error in a template that is only reached from one pane would
    otherwise sit undiscovered until someone opened that pane.
    """
    from jinja2 import TemplateSyntaxError

    from tools import jinja_template_loading

    env = jinja_template_loading()
    root = _templates_dir()
    failures = []
    for path in sorted(root.rglob("*.html")):
        name = path.relative_to(root).as_posix()
        try:
            env.get_template(name)
        except TemplateSyntaxError as exc:
            failures.append(f"{name}:{exc.lineno}: {exc.message}")
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, "templates failed to parse:\n  " + "\n  ".join(failures)


def test_run_details_renders_under_strict_undefined(graph):
    """
    Re-render ``run_details.html`` with ``StrictUndefined``.

    By default Jinja turns an unknown name into an empty string, so a renamed or
    misspelled context key produces a silently blank patch of the page instead of
    an error. Under ``StrictUndefined`` the same reference raises, which is what
    turns "this pane looks a bit empty" into an actionable failure.
    """
    from jinja2 import StrictUndefined, UndefinedError

    from tools import jinja_template_loading

    env = jinja_template_loading()
    env.undefined = StrictUndefined

    pyd = run_pyd = graph["runs"][0].to_pydantic()
    # ``to_html`` supplies css/js alongside the object dict; mirror that so the
    # only undefined names left are genuine mistakes in the template.
    details = pyd.clean_details_for_render(pyd.improved_dict)
    template = env.get_template("run_details.html")
    try:
        template.render(css=[], js=[], child=False, run=details)
    except UndefinedError as exc:
        pytest.fail(f"run_details.html references an undefined name: {exc}")


# --------------------------------------------------------------------------- #
# The sign-off button, which has been wrong in both directions.                #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "signed_by,permission,expect_visible",
    [
        (None,     True,  True),    # unsigned, allowed  -> offer to sign
        ("",       True,  True),    # unset via the pydantic default
        ("lwark",  True,  False),   # already signed      -> nothing to do
        (None,     False, False),   # not a power user
        ("lwark",  False, False),
    ],
)
def test_sign_off_button_visibility(signed_by, permission, expect_visible):
    """
    The Sign Off button must appear exactly when the run is unsigned and the user
    is allowed to sign it.

    This condition has been wrong twice: first testing ``!= "NA"`` (which showed
    the button only on runs that were *already* signed), then comparing against a
    sentinel the getter had stopped producing (which showed it on every run).

    Both falsy spellings that actually reach the template are checked: ``None``
    from the model and ``""`` from ``PydRun``'s default. The legacy ``"NA"``
    sentinel is deliberately *not* in this table -- the current condition is a
    truthiness test, so ``"NA"`` would read as signed. See
    ``test_live_render_never_yields_the_na_sentinel`` for why that is safe today.
    """
    from tools import jinja_template_loading

    env = jinja_template_loading()
    template = env.get_template("run_details.html")
    html = template.render(
        run={
            "rsl_plate_number": "RSL-TEST-0001",
            "permission": permission,
            "signed_by": signed_by,
            "excluded": [],
            "sample": [],
            "procedure": [],
            "comment": [],
        },
        child=False,
    )
    button_line = next(line for line in html.splitlines() if 'id="sign_btn"' in line)
    visible = " hidden" not in button_line
    assert visible is expect_visible, (
        f"signed_by={signed_by!r} permission={permission}: "
        f"button {'shown' if visible else 'hidden'}, expected "
        f"{'shown' if expect_visible else 'hidden'}"
    )


def test_sign_off_script_is_guarded_for_nested_runs():
    """
    ``clientsubmission_details.html`` includes ``run_details.html`` with
    ``child=True``, which suppresses the button but still emits the script block.
    The click handler therefore has to tolerate the button being absent, or every
    nested run throws a null dereference in the WebEngine console.
    """
    from tools import jinja_template_loading

    env = jinja_template_loading()
    template = env.get_template("run_details.html")
    context = {
        "rsl_plate_number": "RSL-TEST-0001", "permission": True, "signed_by": None,
        "excluded": [], "sample": [], "procedure": [], "comment": [],
    }

    child_html = template.render(run=context, child=True)
    assert 'id="sign_btn"' not in child_html, "the button should be suppressed for a child"

    if 'getElementById("sign_btn")' in child_html:
        assert "if (signBtn)" in child_html or "?." in child_html, (
            "run_details.html binds a click handler to sign_btn without checking "
            "that it exists; nested runs will throw a TypeError in the console"
        )


def test_live_render_never_yields_the_na_sentinel(graph):
    """
    An unsigned run must reach the template with a falsy ``signed_by``.

    The button condition is a truthiness test, so the string ``"NA"`` would read
    as "already signed" and hide the button on every unsigned run. Nothing on the
    live path produces it today -- ``Run.signed_by`` returns ``None`` and neither
    ``details_dict`` nor ``PydRun.improved_dict`` coerces it -- but ``"NA"`` is
    still manufactured elsewhere in the codebase (the ``handle_results`` filter,
    ``coerce_none_to_na``), so this pins the one place it must not appear.
    """
    run = graph["runs"][0]
    run._signed_by = None

    assert not run.signed_by
    assert not run.details_dict.get("signed_by")
    assert not run.to_pydantic().improved_dict.get("signed_by")


def test_unsigned_run_renders_a_visible_sign_button(graph):
    """
    End-to-end through ``to_html``: an unsigned run offers the button, a signed
    one does not.

    ``to_html`` merges its keyword arguments into the render context, which is how
    ``permission`` is forced here without depending on who is running the tests.
    """
    def button_line(run, signed_by):
        run._signed_by = signed_by
        html = run.to_pydantic().to_html(permission=True)
        return next(l for l in html.splitlines() if 'id="sign_btn"' in l and "<button" in l)

    run = graph["runs"][0]
    assert " hidden" not in button_line(run, None), \
        "an unsigned run must offer the Sign Off button"
    assert " hidden" in button_line(run, "lwark"), \
        "a signed run must not offer the Sign Off button"
