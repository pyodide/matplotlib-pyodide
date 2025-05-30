import math

from js import document
from matplotlib.backend_bases import FigureCanvasBase, NavigationToolbar2, TimerBase

from pyodide.ffi.wrappers import (
    add_event_listener,
    clear_interval,
    clear_timeout,
    set_interval,
    set_timeout,
)

try:
    from js import devicePixelRatio as DEVICE_PIXEL_RATIO
except ImportError:
    DEVICE_PIXEL_RATIO = 1


class FigureCanvasWasm(FigureCanvasBase):
    supports_blit = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._idle_scheduled = False
        self._id = "matplotlib_" + hex(id(self))[2:]
        self._title = ""
        self._ratio = 1
        matplotlib_figure_styles = self._add_matplotlib_styles()
        if document.getElementById("matplotlib-figure-styles") is None:
            document.head.appendChild(matplotlib_figure_styles)

    def _add_matplotlib_styles(self):
        toolbar_buttons_css_content = """
            button.matplotlib-toolbar-button {
                font-size: 14px;
                color: #495057;
                text-transform: uppercase;
                background: #e9ecef;
                padding: 9px 18px;
                border: 1px solid #fff;
                border-radius: 4px;
                transition-duration: 0.4s;
            }

            button.matplotlib-toolbar-button#text {
                font-family: -apple-system, BlinkMacSystemFont,
                "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell,
                "Fira Sans", "Droid Sans", "Helvetica Neue", Arial,
                sans-serif, "Apple Color Emoji", "Segoe UI Emoji",
                "Segoe UI Symbol";
            }

            button.matplotlib-toolbar-button:hover {
                color: #fff;
                background: #495057;
            }
        """
        toolbar_buttons_style_element = document.createElement("style")
        toolbar_buttons_style_element.id = "matplotlib-figure-styles"
        toolbar_buttons_css = document.createTextNode(toolbar_buttons_css_content)
        toolbar_buttons_style_element.appendChild(toolbar_buttons_css)
        return toolbar_buttons_style_element

    def get_element(self, name):
        """
        Looks up an HTMLElement created for this figure.
        """
        # TODO: Should we store a reference here instead of always looking it
        # up? I'm a little concerned about weird Python/JS
        # cross-memory-management issues...
        return document.getElementById(self._id + name)

    def get_dpi_ratio(self, context):
        """
        Gets the ratio of physical pixels to logical pixels for the given HTML
        Canvas context.

        This is typically 2 on a HiDPI ("Retina") display, and 1 otherwise.
        """
        backing_store = (
            getattr(context, "backingStorePixelRatio", 0)
            or getattr(context, "webkitBackingStorePixel", 0)
            or getattr(context, "mozBackingStorePixelRatio", 0)
            or getattr(context, "msBackingStorePixelRatio", 0)
            or getattr(context, "oBackingStorePixelRatio", 0)
            or getattr(context, "backendStorePixelRatio", 0)
            or 1
        )
        return DEVICE_PIXEL_RATIO / backing_store

    def show(self, *args, **kwargs):
        # If we've already shown this canvas elsewhere, don't create a new one,
        # just reuse it and scroll to the existing one.
        existing = self.get_element("")
        if existing is not None:
            self.draw_idle()
            existing.scrollIntoView()
            return

        # Disable the right-click context menu.
        # Doesn't work in all browsers.
        def ignore(event):
            event.preventDefault()
            return False

        # Create the main canvas and determine the physical to logical pixel
        # ratio
        canvas = document.createElement("canvas")
        context = canvas.getContext("2d")
        self._ratio = self.get_dpi_ratio(context)

        width, height = self.get_width_height()
        width *= self._ratio
        height *= self._ratio
        div = self._create_root_element()
        add_event_listener(div, "contextmenu", ignore)
        div.setAttribute(
            "style",
            "margin: 0 auto; text-align: center;" + f"width: {width / self._ratio}px",
        )
        div.id = self._id

        # The top bar
        top = document.createElement("div")
        top.id = self._id + "top"
        top.setAttribute("style", "font-weight: bold; text-align: center")
        top.textContent = self._title
        div.appendChild(top)

        # A div containing two canvases stacked on top of one another:
        #   - The bottom for rendering matplotlib content
        #   - The top for rendering interactive elements, such as the zoom
        #     rubberband
        canvas_div = document.createElement("div")
        canvas_div.setAttribute("style", "position: relative")

        canvas.id = self._id + "canvas"
        canvas.setAttribute("width", width)
        canvas.setAttribute("height", height)
        canvas.setAttribute(
            "style",
            "left: 0; top: 0; z-index: 0; outline: 0;"
            + "width: {}px; height: {}px".format(
                width / self._ratio, height / self._ratio
            ),
        )
        canvas_div.appendChild(canvas)

        rubberband = document.createElement("canvas")
        rubberband.id = self._id + "rubberband"
        rubberband.setAttribute("width", width)
        rubberband.setAttribute("height", height)
        rubberband.setAttribute(
            "style",
            "position: absolute; left: 0; top: 0; z-index: 0; "
            + "outline: 0; width: {}px; height: {}px".format(
                width / self._ratio, height / self._ratio
            ),
        )
        # Canvas must have a "tabindex" attr in order to receive keyboard
        # events
        rubberband.setAttribute("tabindex", "0")
        # Event handlers are added to the canvas "on top", even though most of
        # the activity happens in the canvas below.
        # TODO: with 0.2.3, we temporarily disable event listeners for the rubberband canvas.
        # This shall be revisited in a future release.
        # add_event_listener(rubberband, "mousemove", self.onmousemove)
        # add_event_listener(rubberband, "mouseup", self.onmouseup)
        # add_event_listener(rubberband, "mousedown", self.onmousedown)
        # add_event_listener(rubberband, "mouseenter", self.onmouseenter)
        # add_event_listener(rubberband, "mouseleave", self.onmouseleave)
        # add_event_listener(rubberband, "keyup", self.onkeyup)
        # add_event_listener(rubberband, "keydown", self.onkeydown)
        context = rubberband.getContext("2d")
        context.strokeStyle = "#000000"
        context.setLineDash([2, 2])
        canvas_div.appendChild(rubberband)

        div.appendChild(canvas_div)

        # The bottom bar, with toolbar and message display
        bottom = document.createElement("div")

        # Check if toolbar exists before trying to get its element
        # c.f. https://github.com/pyodide/pyodide/pull/4510
        if self.toolbar is not None:
            toolbar = self.toolbar.get_element()
            bottom.appendChild(toolbar)

        message = document.createElement("div")
        message.id = self._id + "message"
        message.setAttribute("style", "min-height: 1.5em")
        bottom.appendChild(message)
        div.appendChild(bottom)

        self.draw()

    def destroy(self, *args, **kwargs):
        div = document.getElementById(self._id)
        parentElement = div.parentNode
        if parentElement:
            parentElement.removeChild(div)
        div.removeChild(div.firstChild)

    def draw(self):
        pass

    def draw_idle(self):
        if not self._idle_scheduled:
            self._idle_scheduled = True
            set_timeout(self.draw, 1)

    def set_message(self, message):
        message_display = self.get_element("message")
        if message_display is not None:
            message_display.textContent = message

    def _convert_mouse_event(self, event):
        width, height = self.get_width_height()
        x = event.offsetX
        y = height - event.offsetY
        button = event.button + 1
        # Disable the right-click context menu in some browsers
        if button == 3:
            event.preventDefault()
            event.stopPropagation()
        if button == 2:
            button = 3
        return x, y, button

    def onmousemove(self, event):
        x, y, button = self._convert_mouse_event(event)
        self.motion_notify_event(x, y, guiEvent=event)

    def onmouseup(self, event):
        x, y, button = self._convert_mouse_event(event)
        self.button_release_event(x, y, button, guiEvent=event)

    def onmousedown(self, event):
        x, y, button = self._convert_mouse_event(event)
        self.button_press_event(x, y, button, guiEvent=event)

    def onmouseenter(self, event):
        # When the mouse is over the figure, get keyboard focus
        self.get_element("rubberband").focus()
        self.enter_notify_event(guiEvent=event)

    def onmouseleave(self, event):
        # When the mouse leaves the figure, drop keyboard focus
        self.get_element("rubberband").blur()
        self.leave_notify_event(guiEvent=event)

    def onscroll(self, event):
        x, y, button = self._convert_mouse_event(event)
        self.scroll_event(x, y, event.deltaX, guiEvent=event)

    _cursor_map = {0: "pointer", 1: "default", 2: "crosshair", 3: "move"}

    def set_cursor(self, cursor):
        rubberband = self.get_element("rubberband")
        if rubberband is not None:
            rubberband.style.cursor = self._cursor_map.get(cursor, 0)

    # http://www.cambiaresearch.com/articles/15/javascript-char-codes-key-codes
    _SHIFT_LUT = {
        59: ":",
        61: "+",
        173: "_",
        186: ":",
        187: "+",
        188: "<",
        189: "_",
        190: ">",
        191: "?",
        192: "~",
        219: "{",
        220: "|",
        221: "}",
        222: '"',
    }

    _LUT = {
        8: "backspace",
        9: "tab",
        13: "enter",
        16: "shift",
        17: "control",
        18: "alt",
        19: "pause",
        20: "caps",
        27: "escape",
        32: " ",
        33: "pageup",
        34: "pagedown",
        35: "end",
        36: "home",
        37: "left",
        38: "up",
        39: "right",
        40: "down",
        45: "insert",
        46: "delete",
        91: "super",
        92: "super",
        93: "select",
        106: "*",
        107: "+",
        109: "-",
        110: ".",
        111: "/",
        144: "num_lock",
        145: "scroll_lock",
        186: ":",
        187: "=",
        188: ",",
        189: "-",
        190: ".",
        191: "/",
        192: "`",
        219: "[",
        220: "\\",
        221: "]",
        222: "'",
    }

    def _create_root_element(self):
        div = document.createElement("div")
        mpl_target = getattr(document, "pyodideMplTarget", document.body)
        mpl_target.appendChild(div)
        return div

    def _convert_key_event(self, event):
        code = int(event.which)
        value = chr(code)
        shift = event.shiftKey and code != 16
        ctrl = event.ctrlKey and code != 17
        alt = event.altKey and code != 18

        # letter keys
        if 65 <= code <= 90:
            if not shift:
                value = value.lower()
            else:
                shift = False
        # number keys
        elif 48 <= code <= 57:
            if shift:
                value = ")!@#$%^&*("[int(value)]
                shift = False
        # function keys
        elif 112 <= code <= 123:
            value = "f%s" % (code - 111)
        # number pad keys
        elif 96 <= code <= 105:
            value = "%s" % (code - 96)
        # keys with shift alternatives
        elif code in self._SHIFT_LUT and shift:
            value = self._SHIFT_LUT[code]
            shift = False
        elif code in self._LUT:
            value = self._LUT[code]

        key = []
        if shift:
            key.append("shift")
        if ctrl:
            key.append("ctrl")
        if alt:
            key.append("alt")
        key.append(value)
        return "+".join(key)

    def onkeydown(self, event):
        key = self._convert_key_event(event)
        self.key_press_event(key, guiEvent=event)

    def onkeyup(self, event):
        key = self._convert_key_event(event)
        self.key_release_event(key, guiEvent=event)

    def get_window_title(self):
        top = self.get_element("top")
        return top.textContent

    def set_window_title(self, title):
        top = self.get_element("top")
        self._title = title
        if top is not None:
            top.textContent = title

    # def resize_event(self):
    #     # TODO
    #     pass

    # def close_event(self):
    #     # TODO
    #     pass

    def draw_rubberband(self, x0, y0, x1, y1):
        rubberband = self.get_element("rubberband")
        width, height = self.get_width_height()
        y0 = height - y0
        y1 = height - y1
        x0 = math.floor(x0) + 0.5
        y0 = math.floor(y0) + 0.5
        x1 = math.floor(x1) + 0.5
        y1 = math.floor(y1) + 0.5
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        context = rubberband.getContext("2d")
        context.clearRect(0, 0, width * self._ratio, height * self._ratio)
        context.strokeRect(
            x0 * self._ratio,
            y0 * self._ratio,
            (x1 - x0) * self._ratio,
            (y1 - y0) * self._ratio,
        )

    def remove_rubberband(self):
        rubberband = self.get_element("rubberband")
        width, height = self.get_width_height()
        context = rubberband.getContext("2d")
        context.clearRect(0, 0, width * self._ratio, height * self._ratio)

    def new_timer(self, *args, **kwargs):
        return TimerWasm(*args, **kwargs)


_FONTAWESOME_ICONS = {
    "home": "fa-home",
    "back": "fa-arrow-left",
    "forward": "fa-arrow-right",
    "zoom_to_rect": "fa-search-plus",
    "move": "fa-arrows",
    "download": "fa-download",
    None: None,
}


FILE_TYPES = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"}


class NavigationToolbar2Wasm(NavigationToolbar2):
    def _init_toolbar(self):
        pass

    def get_element(self):
        # Create the HTML content for the toolbar
        div = document.createElement("span")

        def add_spacer():
            span = document.createElement("span")
            span.style.minWidth = "16px"
            span.textContent = "\u00a0"
            div.appendChild(span)

        for _text, _tooltip_text, image_file, name_of_method in self.toolitems:
            if image_file in _FONTAWESOME_ICONS:
                if image_file is None:
                    add_spacer()
                else:
                    button = document.createElement("button")
                    button.classList.add("fa")
                    button.classList.add(_FONTAWESOME_ICONS[image_file])
                    button.classList.add("matplotlib-toolbar-button")
                    add_event_listener(button, "click", getattr(self, name_of_method))
                    div.appendChild(button)

        for format, _mimetype in sorted(list(FILE_TYPES.items())):
            button = document.createElement("button")
            button.classList.add("fa")
            button.textContent = format
            button.classList.add("matplotlib-toolbar-button")
            button.id = "text"
            add_event_listener(button, "click", self.ondownload)
            div.appendChild(button)

        return div

    def ondownload(self, event):
        format = event.target.textContent
        self.download(format, FILE_TYPES[format])

    def download(self, format, mimetype):
        pass

    def set_message(self, message):
        self.canvas.set_message(message)

    def set_cursor(self, cursor):
        self.canvas.set_cursor(cursor)

    def draw_rubberband(self, event, x0, y0, x1, y1):
        self.canvas.draw_rubberband(x0, y0, x1, y1)

    def remove_rubberband(self):
        self.canvas.remove_rubberband()


class TimerWasm(TimerBase):
    def _timer_start(self):
        self._timer_stop()
        if self._single:
            self._timer: int | None = set_timeout(self._on_timer, self.interval)
        else:
            self._timer = set_interval(self._on_timer, self.interval)

    def _timer_stop(self):
        if self._timer is None:
            return
        elif self._single:
            clear_timeout(self._timer)
            self._timer = None
        else:
            clear_interval(self._timer)
            self._timer = None

    def _timer_set_interval(self):
        # Only stop and restart it if the timer has already been started
        if self._timer is not None:
            self._timer_stop()
            self._timer_start()
