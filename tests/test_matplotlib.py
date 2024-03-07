import pytest
from conftest import matplotlib_test_decorator
from pytest_pyodide import run_in_pyodide


@matplotlib_test_decorator
@run_in_pyodide(packages=["matplotlib"])
def test_plot(selenium_standalone_matplotlib):
    from matplotlib import pyplot as plt

    plt.figure()
    plt.plot([1, 2, 3])
    plt.show()


@pytest.mark.skip(reason="wrong version of matplotlib_pyodide in tests")
@matplotlib_test_decorator
@run_in_pyodide(packages=["matplotlib"])
def test_plot_with_pause(selenium_standalone_matplotlib):
    from matplotlib import pyplot as plt

    plt.figure()
    plt.plot([1, 2, 3])
    plt.pause(0.001)
    plt.show()


@matplotlib_test_decorator
@run_in_pyodide(packages=["matplotlib"])
def test_svg(selenium_standalone_matplotlib):
    import io

    from matplotlib import pyplot as plt

    plt.figure()
    plt.plot([1, 2, 3])
    fd = io.BytesIO()
    plt.savefig(fd, format="svg")

    content = fd.getvalue().decode("utf8")
    assert len(content) == 14998
    assert content.startswith("<?xml")


@matplotlib_test_decorator
@run_in_pyodide(packages=["matplotlib"])
def test_pdf(selenium_standalone_matplotlib):
    from matplotlib import pyplot as plt

    plt.figure()
    plt.plot([1, 2, 3])
    import io

    fd = io.BytesIO()
    plt.savefig(fd, format="pdf")


@run_in_pyodide(packages=["matplotlib"])
def test_font_manager(selenium_standalone_matplotlib):
    """
    Comparing vendored fontlist.json version with the one built
    by font_manager.py.

    If you try to update Matplotlib and this test fails, try to
    update fontlist.json.
    """
    import json
    import os

    from matplotlib import font_manager as fm

    # get fontlist form file
    fontist_file = os.path.join(os.path.dirname(fm.__file__), "fontlist.json")
    with open(fontist_file) as f:
        fontlist_vendor = json.loads(f.read())

    # get fontlist from build
    fontlist_built = json.loads(json.dumps(fm.FontManager(), cls=fm._JSONEncoder))

    # reodering list to compare
    for list in ("afmlist", "ttflist"):
        for fontlist in (fontlist_vendor, fontlist_built):
            fontlist[list].sort(key=lambda x: x["fname"])

    assert fontlist_built == fontlist_vendor


@matplotlib_test_decorator
@run_in_pyodide(packages=["matplotlib"])
def test_destroy(selenium_standalone_matplotlib):
    from matplotlib import pyplot as plt

    plt.figure()
    plt.plot([1, 2, 3])
    plt.show()
    plt.close()


@matplotlib_test_decorator
@run_in_pyodide(packages=["matplotlib"])
def test_call_close_multi_times(selenium_standalone_matplotlib):
    from matplotlib import pyplot as plt

    plt.figure()
    plt.plot([1, 2, 3])
    plt.show()
    plt.close()
    plt.close()


@matplotlib_test_decorator
@run_in_pyodide(packages=["matplotlib"])
def test_call_show_and_close_multi_times(selenium_standalone_matplotlib):
    from matplotlib import pyplot as plt

    plt.figure()
    plt.plot([1, 2, 3])
    plt.show()
    plt.close()
    plt.plot([1, 2, 3])
    plt.show()
    plt.close()
