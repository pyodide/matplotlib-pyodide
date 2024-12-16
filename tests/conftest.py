from functools import reduce
from pathlib import Path

import pytest
from pytest_pyodide import spawn_web_server

DECORATORS = [
    pytest.mark.xfail_browsers(node="No supported matplotlib backends on node"),
    pytest.mark.skip_refcount_check,
    pytest.mark.skip_pyproxy_check,
    pytest.mark.driver_timeout(60),
]


def matplotlib_test_decorator(f):
    return reduce(lambda x, g: g(x), DECORATORS, f)


@pytest.fixture(scope="module")
def wheel_path(tmp_path_factory):
    # Build a micropip wheel for testing
    import build
    from build.env import DefaultIsolatedEnv

    output_dir = tmp_path_factory.mktemp("wheel")

    with DefaultIsolatedEnv() as env:
        builder = build.ProjectBuilder(
            source_dir=Path(__file__).parent.parent,
            python_executable=env.python_executable,
        )
        env.install(builder.build_system_requires)
        builder.build("wheel", output_directory=output_dir)

    yield output_dir


@pytest.fixture
def selenium_standalone_matplotlib(selenium_standalone, wheel_path):
    wheel_dir = Path(wheel_path)
    wheel_files = list(wheel_dir.glob("*.whl"))

    if not wheel_files:
        pytest.exit("No wheel files found in wheel/ directory")

    wheel_file = wheel_files[0]
    with spawn_web_server(wheel_dir) as server:
        server_hostname, server_port, _ = server
        base_url = f"http://{server_hostname}:{server_port}/"
        selenium_standalone.run_js(
            f"""
            await pyodide.loadPackage({base_url + wheel_file.name!r});
            await pyodide.loadPackage(["matplotlib"]);
            pyodide.runPython("import matplotlib");
            """
        )

    yield selenium_standalone
