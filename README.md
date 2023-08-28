# matplotlib-pyodide

[![PyPI Latest Release](https://img.shields.io/pypi/v/matplotlib-pyodide.svg)](https://pypi.org/project/matplotlib-pyodide/)
![GHA](https://github.com/pyodide/matplotlib-pyodide/actions/workflows/main.yml/badge.svg)
[![codecov](https://codecov.io/gh/pyodide/matplotlib-pyodide/branch/main/graph/badge.svg)](https://codecov.io/gh/pyodide/matplotlib-pyodide)


HTML5 backends for Matplotlib compatible with Pyodide

This package includes two matplotlib backends,

 - the `wasm_backend` which from allows rendering the Agg buffer as static images into an HTML canvas
 - an interactive HTML5 canvas backend `html5_canvas_backend` described in
   [this blog post](https://blog.pyodide.org/posts/canvas-renderer-matplotlib-in-pyodide/)


## Installation

This package will be installed as a dependency when you load `matplotlib` in Pyodide.

## Usage

To change the backend in matplotlib,
 - for the wasm backend,
   ```py
   import matplotlib
   matplotlib.use("module://matplotlib_pyodide.wasm_backend")
   ```
 - for the interactive HTML5 backend;
   ```py
   import matplotlib
   matplotlib.use("module://matplotlib_pyodide.html5_canvas_backend")
   ```

By default, matplotlib figures will be rendered inside a div that's appended to the end of `document.body`.
You can override this behavior by setting `document.pyodideMplTarget` to an HTML element. If you had an HTML
element with id "target", you could configure the backend to render visualizations inside it with this code:

```py
document.pyodideMplTarget = document.getElementById('target')
```

For more information see the [matplotlib documentation](https://matplotlib.org/stable/users/explain/backends.html).

## License

pyodide-cli uses the [Mozilla Public License Version
2.0](https://choosealicense.com/licenses/mpl-2.0/).
