## DISCLAIMER

This project is no longer used in Pyodide as of Pyodide v0.28 (see [issue#65](https://github.com/pyodide/matplotlib-pyodide/issues/65#issuecomment-2532463697)).
We don't accept any new features or bug fixes. The project is archived and will not be maintained anymore.

The default matplotlib backend for Pyodide is now the patched version of `webagg` backend. If you were using `matplotlib_pyodide` in your code,
simply removing the `matplotlib.use('module://matplotlib_pyodide...')` line should be enough to make your code work with the new backend.

If it doesn't, try replacing it with `matplotlib.use('webagg')`.

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
