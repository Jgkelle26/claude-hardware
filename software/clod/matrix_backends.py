"""Display backends for the 64x64 matrix: a tkinter mock and a real rpi-rgb-led-matrix backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from PIL import Image


class DisplayBackend(ABC):
    """Abstract display backend. Implementations may render to hardware or a preview window."""

    @property
    @abstractmethod
    def width(self) -> int: ...

    @property
    @abstractmethod
    def height(self) -> int: ...

    @abstractmethod
    def render(self, image: Image.Image) -> None: ...

    def close(self) -> None:  # default no-op
        return None


class MockMatrixBackend(DisplayBackend):
    """Tkinter-backed preview window that scales the 64x64 image 8x to 512x512.

    render() is safe to call from any thread; it schedules the actual display
    update on the tkinter main thread via root.after(0, ...).
    """

    SCALE = 8

    def __init__(self, rows: int = 64, cols: int = 64) -> None:
        import tkinter as tk
        from PIL import ImageTk

        self._rows = rows
        self._cols = cols
        self._tk = tk
        self._ImageTk = ImageTk

        self.root = tk.Tk()
        self.root.title("Clod - Mock Matrix Display")
        self.root.configure(bg="black")
        self.root.resizable(False, False)

        scaled_w = cols * self.SCALE
        scaled_h = rows * self.SCALE

        self._canvas = tk.Canvas(
            self.root,
            width=scaled_w,
            height=scaled_h,
            bg="black",
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack(padx=0, pady=0)

        # Seed with a black image so the canvas has something to draw immediately.
        initial = Image.new("RGB", (cols, rows), (0, 0, 0))
        self._photo = ImageTk.PhotoImage(
            initial.resize((scaled_w, scaled_h), Image.NEAREST)
        )
        self._image_id = self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._closed = False
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    @property
    def width(self) -> int:
        return self._cols

    @property
    def height(self) -> int:
        return self._rows

    def render(self, image: Image.Image) -> None:
        if self._closed:
            return
        # Schedule the display update on the tkinter main thread.
        try:
            self.root.after(0, self._update_display, image)
        except RuntimeError:
            # tk app torn down; ignore.
            pass

    def _update_display(self, image: Image.Image) -> None:
        if self._closed:
            return
        scaled = image.resize(
            (self._cols * self.SCALE, self._rows * self.SCALE), Image.NEAREST
        )
        photo = self._ImageTk.PhotoImage(scaled)
        self._canvas.itemconfigure(self._image_id, image=photo)
        # Keep a reference so tk doesn't GC it between frames.
        self._photo = photo

    def mainloop(self) -> None:
        """Run tkinter's mainloop. Must be called from the main thread."""
        self.root.mainloop()

    def _on_close(self) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.root.destroy()
        except Exception:
            pass


class RealMatrixBackend(DisplayBackend):
    """Backend for the physical 64x64 HUB75 matrix via rpi-rgb-led-matrix."""

    def __init__(
        self,
        rows: int = 64,
        cols: int = 64,
        brightness: int = 30,
        hardware_mapping: str = "regular",
        slowdown_gpio: int = 4,
    ) -> None:
        try:
            from rgbmatrix import RGBMatrix, RGBMatrixOptions  # type: ignore
        except ImportError as e:
            raise ImportError(
                "rgbmatrix is not available. RealMatrixBackend only works on "
                "a Raspberry Pi with Henner Zeller's rpi-rgb-led-matrix Python "
                "bindings installed. Use MockMatrixBackend on a Mac."
            ) from e

        options = RGBMatrixOptions()
        options.rows = rows
        options.cols = cols
        options.chain_length = 1
        options.parallel = 1
        options.hardware_mapping = hardware_mapping
        options.brightness = brightness
        options.gpio_slowdown = slowdown_gpio

        self._rows = rows
        self._cols = cols
        self.matrix: Any = RGBMatrix(options=options)

    @property
    def width(self) -> int:
        return self._cols

    @property
    def height(self) -> int:
        return self._rows

    def render(self, image: Image.Image) -> None:
        self.matrix.SetImage(image)

    def close(self) -> None:
        try:
            self.matrix.Clear()
        except Exception:
            pass
