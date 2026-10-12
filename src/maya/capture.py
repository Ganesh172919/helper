"""Explicit physical-pixel screen acquisition and bounded image preparation."""

import hashlib
from io import BytesIO

import mss
from PIL import Image, ImageStat

from maya.core.types import ImageAttachment, MayaError


# --- Physical desktop bounds are independent of Qt logical coordinates. ---
def monitor_at(monitors: list[dict], point: tuple[int, int]) -> dict:
    """Select the monitor containing a point; a disconnected/outside point falls back to primary."""
    x, y = point
    return next(
        (
            monitor
            for monitor in monitors[1:]
            if monitor["left"] <= x < monitor["left"] + monitor["width"]
            and monitor["top"] <= y < monitor["top"] + monitor["height"]
        ),
        monitors[1],
    )


def capture(scope: str, point: tuple[int, int], window_rect=None) -> tuple[Image.Image, dict]:
    """Capture one requested scope with a thread-local MSS instance; raises on missing displays.

    Active-window mode captures its visible desktop rectangle, not hidden/occluded window surfaces.
    Secure or protected content is never bypassed. All-monitor captures may contain desktop gaps.
    """
    try:
        with mss.mss() as screen:
            monitors = screen.monitors
            if len(monitors) < 2:
                raise MayaError("No screen is available for capture.", "capture")
            bounds = dict(monitors[0] if scope == "all" else monitor_at(monitors, point))
            if scope == "window":
                if not window_rect:
                    raise MayaError(
                        "No external active window is available. Focus it before capturing.", "capture"
                    )
                left, top, right, bottom = window_rect
                desktop = monitors[0]
                left, top = max(left, desktop["left"]), max(top, desktop["top"])
                right = min(right, desktop["left"] + desktop["width"])
                bottom = min(bottom, desktop["top"] + desktop["height"])
                bounds = {"left": left, "top": top, "width": right - left, "height": bottom - top}
            if bounds["width"] <= 0 or bounds["height"] <= 0:
                raise MayaError("The window is outside the available desktop.", "capture")
            if bounds["width"] * bounds["height"] > 100_000_000:
                raise MayaError(
                    "This desktop is too large for one capture. Select a monitor or region.", "capture"
                )
            shot = screen.grab(bounds)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
            return image, bounds
    except (mss.exception.ScreenShotError, OSError) as exc:
        raise MayaError(
            "Could not capture this screen. Check the desktop session or try a different scope.", "capture"
        ) from exc


# --- Encoding controls image cost and avoids leaking useless protected/blank frames. ---
def prepare(
    image: Image.Image, max_edge: int = 1568, max_bytes: int = 4_000_000, check_blank: bool = True
) -> ImageAttachment:
    """Resize without upscaling, encode RGB, and enforce bytes; raise on near-uniform/protected images."""
    image = image.convert("RGB")
    if image.width < 8 or image.height < 8:
        raise MayaError("Select a larger region (at least 8 × 8 pixels).", "capture")
    sample = image.resize((64, 64))
    if check_blank and max(ImageStat.Stat(sample).stddev) < 1.2:
        raise MayaError(
            "The capture is blank or almost uniform. This application may block screenshots; try text context.",
            "capture",
        )
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    for attempt in range(8):
        output = BytesIO()
        fmt = "PNG" if attempt == 0 and max(image.size) <= 700 else "JPEG"
        image.save(
            output,
            format=fmt,
            **({"optimize": True} if fmt == "PNG" else {"quality": max(55, 85 - attempt * 5)}),
        )
        payload = output.getvalue()
        if len(payload) <= max_bytes:
            return ImageAttachment(
                payload,
                "image/png" if fmt == "PNG" else "image/jpeg",
                image.width,
                image.height,
                hashlib.sha256(payload).hexdigest(),
            )
        image = image.resize(
            (max(8, int(image.width * 0.8)), max(8, int(image.height * 0.8))), Image.Resampling.LANCZOS
        )
    raise MayaError("The screenshot is too large. Capture a smaller region.", "capture")
