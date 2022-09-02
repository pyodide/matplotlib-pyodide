from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("matplotlib_pyodide")
except PackageNotFoundError:
    # package is not installed
    pass
