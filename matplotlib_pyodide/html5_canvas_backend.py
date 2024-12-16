#
# HTMl5 Canvas backend for Matplotlib to use when running Matplotlib in Pyodide, first
# introduced via a Google Summer of Code 2019 project:
# https://summerofcode.withgoogle.com/archive/2019/projects/4683094261497856
#
# Associated blog post:
# https://blog.pyodide.org/posts/canvas-renderer-matplotlib-in-pyodide
#
# TODO: As of release 0.2.3, this backend is not yet fully functional following
# an update from Matplotlib 3.5.2 to 3.8.4 in Pyodide in-tree, please refer to
# https://github.com/pyodide/pyodide/pull/4510.
#
# This backend has been redirected to use the WASM backend in the meantime, which
# is now fully functional. The source code for the HTML5 Canvas backend is still
# available in this file, and shall be updated to work in a future release.
#
# Readers are advised to look at https://github.com/pyodide/matplotlib-pyodide/issues/64
# and at https://github.com/pyodide/matplotlib-pyodide/pull/65 for information
# around the status of this backend and on how to contribute to its restoration
# for future releases. Thank you!

import base64
import io
import math
from functools import lru_cache

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import __version__, figure, interactive
from matplotlib._enums import CapStyle
from matplotlib.backend_bases import (
    FigureManagerBase,
    GraphicsContextBase,
    RendererBase,
    _Backend,
)
from matplotlib.backends import backend_agg
from matplotlib.colors import colorConverter, rgb2hex
from matplotlib.font_manager import findfont
from matplotlib.ft2font import LOAD_NO_HINTING, FT2Font
from matplotlib.mathtext import MathTextParser
from matplotlib.path import Path
from matplotlib.transforms import Affine2D
from PIL import Image
from PIL.PngImagePlugin import PngInfo

# Redirect to the WASM backend
from matplotlib_pyodide.browser_backend import FigureCanvasWasm, NavigationToolbar2Wasm
from matplotlib_pyodide.wasm_backend import FigureCanvasAggWasm, FigureManagerAggWasm

try:
    from js import FontFace, ImageData, document
except ImportError as err:
    raise ImportError(
        "html5_canvas_backend is only supported in the browser in the main thread"
    ) from err

from pyodide.ffi import create_proxy

_capstyle_d = {"projecting": "square", "butt": "butt", "round": "round"}

# The URLs of fonts that have already been loaded into the browser
_font_set = set()

_base_fonts_url = "/fonts/"

interactive(True)


class FigureCanvasHTMLCanvas(FigureCanvasWasm):
    def __init__(self, *args, **kwargs):
        FigureCanvasWasm.__init__(self, *args, **kwargs)

    def draw(self):
        # Render the figure using custom renderer
        self._idle_scheduled = True
        orig_dpi = self.figure.dpi
        if self._ratio != 1:
            self.figure.dpi *= self._ratio
        try:
            width, height = self.get_width_height()
            canvas = self.get_element("canvas")
            if canvas is None:
                return
            ctx = canvas.getContext("2d")
            renderer = RendererHTMLCanvas(ctx, width, height, self.figure.dpi, self)
            self.figure.draw(renderer)
        except Exception as e:
            raise RuntimeError("Rendering failed") from e
        finally:
            self.figure.dpi = orig_dpi
            self._idle_scheduled = False

    def get_pixel_data(self):
        """
        Directly getting the underlying pixel data (using `getImageData()`)
        results in a different (but similar) image than the reference image.
        The method below takes a longer route
        (pixels --> encode PNG --> decode PNG --> pixels)
        but gives us the exact pixel data that the reference image has allowing
        us to do a fair comparison test.
        """
        canvas = self.get_element("canvas")
        img_URL = canvas.toDataURL("image/png")[21:]
        canvas_base64 = base64.b64decode(img_URL)
        return np.asarray(Image.open(io.BytesIO(canvas_base64)))

    def print_png(
        self, filename_or_obj, *args, metadata=None, pil_kwargs=None, **kwargs
    ):
        if metadata is None:
            metadata = {}
        if pil_kwargs is None:
            pil_kwargs = {}
        metadata = {
            "Software": f"matplotlib version{__version__}, http://matplotlib.org/",
            **metadata,
        }

        if "pnginfo" not in pil_kwargs:
            pnginfo = PngInfo()
            for k, v in metadata.items():
                pnginfo.add_text(k, v)
            pil_kwargs["pnginfo"] = pnginfo
        pil_kwargs.setdefault("dpi", (self.figure.dpi, self.figure.dpi))

        data = self.get_pixel_data()

        (Image.fromarray(data).save(filename_or_obj, format="png", **pil_kwargs))


class NavigationToolbar2HTMLCanvas(NavigationToolbar2Wasm):
    def download(self, format, mimetype):
        """
        Creates a temporary `a` element with a URL containing the image
        content, and then virtually clicks it. Kind of magical, but it
        works...
        """
        element = document.createElement("a")
        data = io.BytesIO()

        if format == "png":
            FigureCanvasHTMLCanvas.print_png(self.canvas, data)
        else:
            try:
                self.canvas.figure.savefig(data, format=format)
            except Exception:
                raise

        element.setAttribute(
            "href",
            "data:{};base64,{}".format(
                mimetype, base64.b64encode(data.getvalue()).decode("ascii")
            ),
        )
        element.setAttribute("download", f"plot.{format}")
        element.style.display = "none"

        document.body.appendChild(element)
        element.click()
        document.body.removeChild(element)


class GraphicsContextHTMLCanvas(GraphicsContextBase):
    def __init__(self, renderer):
        super().__init__()
        self.stroke = True
        self.renderer = renderer

    def restore(self):
        self.renderer.ctx.restore()

    def set_capstyle(self, cs):
        """
        Set the cap style for lines in the graphics context.

        Parameters
        ----------
        cs : CapStyle or str
            The cap style to use. Can be a CapStyle enum value or a string
            that can be converted to a CapStyle.
        """
        if isinstance(cs, str):
            cs = CapStyle(cs)

        # Convert the JoinStyle enum to its name if needed
        if hasattr(cs, "name"):
            cs = cs.name.lower()

        if cs in ["butt", "round", "projecting"]:
            self._capstyle = cs
            self.renderer.ctx.lineCap = _capstyle_d[cs]
        else:
            raise ValueError(f"Unrecognized cap style. Found {cs}")

    def get_capstyle(self):
        return self._capstyle

    def set_clip_rectangle(self, rectangle):
        self.renderer.ctx.save()
        if not rectangle:
            self.renderer.ctx.restore()
            return
        x, y, w, h = np.round(rectangle.bounds)
        self.renderer.ctx.beginPath()
        self.renderer.ctx.rect(x, self.renderer.height - y - h, w, h)
        self.renderer.ctx.clip()

    def set_clip_path(self, path):
        self.renderer.ctx.save()
        if not path:
            self.renderer.ctx.restore()
            return
        tpath, affine = path.get_transformed_path_and_affine()
        affine = affine + Affine2D().scale(1, -1).translate(0, self.renderer.height)
        self.renderer._path_helper(self.renderer.ctx, tpath, affine)
        self.renderer.ctx.clip()

    def set_dashes(self, dash_offset, dash_list):
        self._dashes = dash_offset, dash_list
        if dash_offset is not None:
            self.renderer.ctx.lineDashOffset = dash_offset
        if dash_list is None:
            self.renderer.ctx.setLineDash([])
        else:
            dln = np.asarray(dash_list)
            dl = list(self.renderer.points_to_pixels(dln))
            self.renderer.ctx.setLineDash(dl)

    def set_joinstyle(self, js):
        if js in ["miter", "round", "bevel"]:
            self._joinstyle = js
            self.renderer.ctx.lineJoin = js
        else:
            raise ValueError(f"Unrecognized join style. Found {js}")

    def set_linewidth(self, w):
        self.stroke = w != 0
        self._linewidth = float(w)
        self.renderer.ctx.lineWidth = self.renderer.points_to_pixels(float(w))


class RendererHTMLCanvas(RendererBase):
    def __init__(self, ctx, width, height, dpi, fig):
        super().__init__()
        self.fig = fig
        self.ctx = ctx
        self.width = width
        self.height = height
        self.ctx.width = self.width
        self.ctx.height = self.height
        self.dpi = dpi

        # Create path-based math text parser; as the bitmap parser
        # was deprecated in 3.4 and removed after 3.5
        self.mathtext_parser = MathTextParser("path")

        self._get_font_helper = lru_cache(maxsize=50)(self._get_font_helper)

        # Keep the state of fontfaces that are loading
        self.fonts_loading = {}

    def new_gc(self):
        return GraphicsContextHTMLCanvas(renderer=self)

    def points_to_pixels(self, points):
        return (points / 72.0) * self.dpi

    def _matplotlib_color_to_CSS(self, color, alpha, alpha_overrides, is_RGB=True):
        if not is_RGB:
            R, G, B, alpha = colorConverter.to_rgba(color)
            color = (R, G, B)

        if (len(color) == 4) and (alpha is None):
            alpha = color[3]

        if alpha is None:
            CSS_color = rgb2hex(color[:3])

        else:
            R = int(color[0] * 255)
            G = int(color[1] * 255)
            B = int(color[2] * 255)
            if len(color) == 3 or alpha_overrides:
                CSS_color = f"""rgba({R:d}, {G:d}, {B:d}, {alpha:.3g})"""
            else:
                CSS_color = """rgba({:d}, {:d}, {:d}, {:.3g})""".format(
                    R, G, B, color[3]
                )

        return CSS_color

    def _math_to_rgba(self, s, prop, rgb):
        """Convert math text to an RGBA array using path parser and figure"""
        from io import BytesIO

        # Get the text dimensions and generate a figure
        # of the right rize.
        width, height, depth, _, _ = self.mathtext_parser.parse(s, dpi=72, prop=prop)

        fig = figure.Figure(figsize=(width / 72, height / 72))

        # Add text to the figure
        # Note: depth/height gives us the baseline position
        fig.text(0, depth / height, s, fontproperties=prop, color=rgb)

        backend_agg.FigureCanvasAgg(fig)

        buf = BytesIO()  # render to PNG
        fig.savefig(buf, dpi=self.dpi, format="png", transparent=True)
        buf.seek(0)

        rgba = plt.imread(buf)
        return rgba, depth

    def _draw_math_text_path(self, gc, x, y, s, prop, angle):
        """Draw mathematical text using paths directly on the canvas.

        This method renders math text by drawing the actual glyph paths
        onto the canvas, rather than creating a temporary image.

        Parameters
        ----------
        gc : GraphicsContextHTMLCanvas
            The graphics context to use for drawing
        x, y : float
            The position of the text baseline in pixels
        s : str
            The text string to render
        prop : FontProperties
            The font properties to use for rendering
        angle : float
            The rotation angle in degrees
        """
        width, height, depth, glyphs, rects = self.mathtext_parser.parse(
            s, dpi=self.dpi, prop=prop
        )

        self.ctx.save()

        self.ctx.translate(x, self.height - y)
        if angle != 0:
            self.ctx.rotate(-math.radians(angle))

        self.ctx.fillStyle = self._matplotlib_color_to_CSS(
            gc.get_rgb(), gc.get_alpha(), gc.get_forced_alpha()
        )

        for font, fontsize, _, ox, oy in glyphs:
            self.ctx.save()
            self.ctx.translate(ox, -oy)

            font.set_size(fontsize, self.dpi)
            verts, codes = font.get_path()

            verts = verts * fontsize / font.units_per_EM

            path = Path(verts, codes)

            transform = Affine2D().scale(1.0, -1.0)
            self._path_helper(self.ctx, path, transform)
            self.ctx.fill()

            self.ctx.restore()

        for x1, y1, x2, y2 in rects:
            self.ctx.fillRect(x1, -y2, x2 - x1, y2 - y1)

        self.ctx.restore()

    def _draw_math_text(self, gc, x, y, s, prop, angle):
        """Draw mathematical text using the most appropriate method.

        This method tries direct path rendering first, and falls back to
        the image-based approach if needed.

        Parameters
        ----------
        gc : GraphicsContextHTMLCanvas
            The graphics context to use for drawing
        x, y : float
            The position of the text baseline in pixels
        s : str
            The text string to render
        prop : FontProperties
            The font properties to use for rendering
        angle : float
            The rotation angle in degrees
        """
        try:
            self._draw_math_text_path(gc, x, y, s, prop, angle)
        except Exception as e:
            # If path rendering fails, we fall back to image-based approach
            print(f"Path rendering failed, falling back to image: {str(e)}")

            rgba, depth = self._math_to_rgba(s, prop, gc.get_rgb())

            angle = math.radians(angle)
            if angle != 0:
                self.ctx.save()
                self.ctx.translate(x, y)
                self.ctx.rotate(-angle)
                self.ctx.translate(-x, -y)

            self.draw_image(gc, x, -y - depth, np.flipud(rgba))

            if angle != 0:
                self.ctx.restore()

    def _set_style(self, gc, rgbFace=None):
        if rgbFace is not None:
            self.ctx.fillStyle = self._matplotlib_color_to_CSS(
                rgbFace, gc.get_alpha(), gc.get_forced_alpha()
            )

        capstyle = gc.get_capstyle()
        if capstyle:
            # Get the string name if it's an enum
            if hasattr(capstyle, "name"):
                capstyle = capstyle.name.lower()
            self.ctx.lineCap = _capstyle_d[capstyle]

        self.ctx.strokeStyle = self._matplotlib_color_to_CSS(
            gc.get_rgb(), gc.get_alpha(), gc.get_forced_alpha()
        )

        self.ctx.lineWidth = self.points_to_pixels(gc.get_linewidth())

    def _path_helper(self, ctx, path, transform, clip=None):
        ctx.beginPath()
        for points, code in path.iter_segments(transform, remove_nans=True, clip=clip):
            if code == Path.MOVETO:
                ctx.moveTo(points[0], points[1])
            elif code == Path.LINETO:
                ctx.lineTo(points[0], points[1])
            elif code == Path.CURVE3:
                ctx.quadraticCurveTo(*points)
            elif code == Path.CURVE4:
                ctx.bezierCurveTo(*points)
            elif code == Path.CLOSEPOLY:
                ctx.closePath()

    def draw_path(self, gc, path, transform, rgbFace=None):
        self._set_style(gc, rgbFace)
        if rgbFace is None and gc.get_hatch() is None:
            figure_clip = (0, 0, self.width, self.height)

        else:
            figure_clip = None

        transform += Affine2D().scale(1, -1).translate(0, self.height)
        self._path_helper(self.ctx, path, transform, figure_clip)

        if rgbFace is not None:
            self.ctx.fill()
            self.ctx.fillStyle = "#000000"

        if gc.stroke:
            self.ctx.stroke()

    def draw_markers(self, gc, marker_path, marker_trans, path, trans, rgbFace=None):
        super().draw_markers(gc, marker_path, marker_trans, path, trans, rgbFace)

    def draw_image(self, gc, x, y, im, transform=None):
        im = np.flipud(im)
        h, w, d = im.shape
        y = self.ctx.height - y - h
        im = np.ravel(np.uint8(np.reshape(im, (h * w * d, -1)))).tobytes()
        pixels_proxy = create_proxy(im)
        pixels_buf = pixels_proxy.getBuffer("u8clamped")
        img_data = ImageData.new(pixels_buf.data, w, h)
        self.ctx.save()
        in_memory_canvas = document.createElement("canvas")
        in_memory_canvas.width = w
        in_memory_canvas.height = h
        in_memory_canvas_context = in_memory_canvas.getContext("2d")
        in_memory_canvas_context.putImageData(img_data, 0, 0)
        self.ctx.drawImage(in_memory_canvas, x, y, w, h)
        self.ctx.restore()
        pixels_proxy.destroy()
        pixels_buf.release()

    def _get_font_helper(self, prop):
        """Cached font lookup

        We wrap this in an lru-cache in the constructor.
        """
        fname = findfont(prop)
        font = FT2Font(str(fname))
        font_file_name = fname.rpartition("/")[-1]
        return (font, font_file_name)

    def _get_font(self, prop):
        result = self._get_font_helper(prop)
        font = result[0]
        font.clear()
        font.set_size(prop.get_size_in_points(), self.dpi)
        return result

    def get_text_width_height_descent(self, s, prop, ismath):
        w: float
        h: float
        d: float
        if ismath:
            # Use the path parser to get exact metrics
            width, height, depth, _, _ = self.mathtext_parser.parse(
                s, dpi=72, prop=prop
            )
            return width, height, depth
        else:
            font, _ = self._get_font(prop)
            font.set_text(s, 0.0, flags=LOAD_NO_HINTING)
            w, h = font.get_width_height()
            w /= 64.0
            h /= 64.0
            d = font.get_descent() / 64.0
            return w, h, d

    def draw_text(self, gc, x, y, s, prop, angle, ismath=False, mtext=None):
        if ismath:
            self._draw_math_text(gc, x, y, s, prop, angle)
            return

        angle = math.radians(angle)
        width, height, descent = self.get_text_width_height_descent(s, prop, ismath)
        x -= math.sin(angle) * descent
        y -= math.cos(angle) * descent - self.ctx.height
        font_size = self.points_to_pixels(prop.get_size_in_points())

        _, font_file_name = self._get_font(prop)

        font_face_arguments = (
            prop.get_name(),
            f"url({_base_fonts_url + font_file_name})",
        )

        # The following snippet loads a font into the browser's
        # environment if it wasn't loaded before. This check is necessary
        # to help us avoid loading the same font multiple times. Further,
        # it helps us to avoid the infinite loop of
        # load font --> redraw --> load font --> redraw --> ....

        if font_face_arguments not in _font_set:
            _font_set.add(font_face_arguments)
            f = FontFace.new(*font_face_arguments)

            font_url = font_face_arguments[1]
            self.fonts_loading[font_url] = f
            f.load().add_done_callback(
                lambda result: self.load_font_into_web(result, font_url)
            )

        font_property_string = "{} {} {:.3g}px {}, {}".format(
            prop.get_style(),
            prop.get_weight(),
            font_size,
            prop.get_name(),
            prop.get_family()[0],
        )
        if angle != 0:
            self.ctx.save()
            self.ctx.translate(x, y)
            self.ctx.rotate(-angle)
            self.ctx.translate(-x, -y)
        self.ctx.font = font_property_string
        self.ctx.fillStyle = self._matplotlib_color_to_CSS(
            gc.get_rgb(), gc.get_alpha(), gc.get_forced_alpha()
        )
        self.ctx.fillText(s, x, y)
        self.ctx.fillStyle = "#000000"
        if angle != 0:
            self.ctx.restore()

    def load_font_into_web(self, loaded_face, font_url):
        fontface = loaded_face.result()
        document.fonts.add(fontface)
        self.fonts_loading.pop(font_url, None)

        # Redraw figure after font has loaded
        self.fig.draw()
        return fontface


class FigureManagerHTMLCanvas(FigureManagerBase):
    def __init__(self, canvas, num):
        super().__init__(canvas, num)
        self.set_window_title("Figure %d" % num)
        self.toolbar = NavigationToolbar2HTMLCanvas(canvas)

    def show(self, *args, **kwargs):
        self.canvas.show(*args, **kwargs)

    def destroy(self, *args, **kwargs):
        self.canvas.destroy(*args, **kwargs)

    def resize(self, w, h):
        pass

    def set_window_title(self, title):
        self.canvas.set_window_title(title)


@_Backend.export
class _BackendHTMLCanvas(_Backend):
    # FigureCanvas = FigureCanvasHTMLCanvas
    # FigureManager = FigureManagerHTMLCanvas
    # Note: with release 0.2.3, we've redirected the HTMLCanvas backend to use the WASM backend
    # for now, as the changes to the HTMLCanvas backend are not yet fully functional.
    # This will be updated in a future release.
    FigureCanvas = FigureCanvasAggWasm
    FigureManager = FigureManagerAggWasm

    @staticmethod
    def show(*args, **kwargs):
        from matplotlib import pyplot as plt

        plt.gcf().canvas.show(*args, **kwargs)

    @staticmethod
    def destroy(*args, **kwargs):
        from matplotlib import pyplot as plt

        plt.gcf().canvas.destroy(*args, **kwargs)
