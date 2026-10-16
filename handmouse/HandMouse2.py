"""HandMouse 2 — webcam hand control for Windows, rebuilt around Apple's input ideas.

Gestures (one hand, palm roughly facing the camera):
  move your hand ............ cursor follows the base of your index finger
  thumb + index, tap ........ left click  (two taps = double-click)
  thumb + index, hold ....... drag, release to drop
  thumb + middle, tap ....... right click
  thumb + middle, hold ...... scroll: move hand up / down
Ctrl+Alt+H pauses / resumes. Right-click the pill for the menu.

Design notes (why it works the way it does):
  * The cursor is anchored to the palm (index + middle knuckles), not a fingertip,
    so pinching doesn't drag the pointer off target. As your fingers close, the
    pointer slows and then locks, so a click lands where you aimed.
  * One Euro filter: heavy smoothing when the hand is still (no jitter), light
    smoothing when it moves fast (no lag). A 120 Hz glide fills in between camera frames.
  * Only pinches act. Nothing happens from just moving or holding a pose.
"""
import json, math, os, sys, threading, time

APP = "HandMouse 2"
VERSION = "2.0"

DEFAULTS = {
    "camera_index": 0,
    "frame_w": 640, "frame_h": 480,
    # part of the camera image that maps to the whole screen (normalised 0..1)
    "box_left": 0.22, "box_right": 0.78, "box_top": 0.18, "box_bottom": 0.62,
    # One Euro filter, in screen pixels
    "filter_min_cutoff": 0.8, "filter_beta": 0.004, "filter_d_cutoff": 1.0,
    "glide_ms": 30,                       # 120 Hz easing between camera frames
    # pinch distance = fingertip gap / palm length
    "pinch_close": 0.19, "pinch_open": 0.28, "pinch_far": 0.50,
    "hold_to_drag_s": 0.22, "drag_move_px": 14,
    "engage_s": 0.20,                     # hand must be visible this long before the cursor moves
    "scroll_gain": 2.2, "natural_scroll": True,
    "pill_x": None, "pill_y": None,
    "tutorial_done": False,
}

# ----------------------------------------------------------------------------- settings

def app_dir():
    return os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))

SETTINGS_PATH = os.path.join(app_dir(), "HandMouse2_settings.json")

def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except Exception:
        pass
    return s

def save_settings(s):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass

def _stub_matplotlib():
    """mediapipe imports matplotlib only for its drawing helpers, which we don't use.
    A stub keeps ~30 MB of plotting library out of the app."""
    import types
    if "matplotlib" not in sys.modules:
        m = types.ModuleType("matplotlib"); m.pyplot = types.ModuleType("matplotlib.pyplot")
        sys.modules["matplotlib"] = m; sys.modules["matplotlib.pyplot"] = m.pyplot

# ----------------------------------------------------------------------------- filtering

class LowPass:
    def __init__(self):
        self.y = None
    def __call__(self, x, a):
        self.y = x if self.y is None else a * x + (1 - a) * self.y
        return self.y

class OneEuro:
    """Casiez, Roussel & Vogel (2012). Adaptive low-pass: cutoff rises with speed."""
    def __init__(self, min_cutoff, beta, d_cutoff):
        self.mc, self.beta, self.dc = min_cutoff, beta, d_cutoff
        self.x, self.dx, self.t = LowPass(), LowPass(), None
    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)
    def reset(self):
        self.x, self.dx, self.t = LowPass(), LowPass(), None
    def __call__(self, v, t):
        if self.t is None:
            self.t = t
            self.dx(0.0, 1.0)
            return self.x(v, 1.0)
        dt = max(t - self.t, 1e-3)
        self.t = t
        prev = self.x.y
        d = self.dx((v - prev) / dt, self._alpha(self.dc, dt))
        cutoff = self.mc + self.beta * abs(d)
        return self.x(v, self._alpha(cutoff, dt))

# ----------------------------------------------------------------------------- gesture engine (pure, testable)

WRIST, THUMB_TIP, INDEX_MCP, INDEX_TIP, MIDDLE_MCP, MIDDLE_TIP = 0, 4, 5, 8, 9, 12

def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v

class GestureEngine:
    """Turns hand landmarks into a pointer position and mouse events.

    update() takes landmarks as a list of (x, y) in normalised image coords (already
    mirrored), or None when no hand is visible. It returns a dict:
      state:    'nohand' | 'tracking' | 'drag' | 'scroll'
      pointer:  (sx, sy) target in screen pixels, or None if the cursor should not move
      pinch:    0..1 how closed the thumb-index pinch is (for the ring)
      events:   list of 'down','up','click','rclick',('wheel', n)
      label:    short text for the UI
    """
    def __init__(self, S, screen_w, screen_h, aspect=4 / 3):
        self.S, self.W, self.H, self.aspect = S, screen_w, screen_h, aspect
        self.fx = OneEuro(S["filter_min_cutoff"], S["filter_beta"], S["filter_d_cutoff"])
        self.fy = OneEuro(S["filter_min_cutoff"], S["filter_beta"], S["filter_d_cutoff"])
        self.reset()

    def reset(self):
        self.seen_since = None
        self.ptr = None            # pointer, screen px (float)
        self.prev_anchor = None    # filtered anchor, screen px
        self.pinch = None          # None | 'index' | 'middle'
        self.pinch_t = 0.0
        self.pinch_anchor = None
        self.mode = None           # None | 'drag' | 'scroll'
        self.scroll_rest = 0.0
        self.flash = ("", 0.0)
        self.fx.reset(); self.fy.reset()

    def _dist(self, a, b):
        return math.hypot((a[0] - b[0]) * self.aspect, a[1] - b[1])

    def _to_screen(self, x, y):
        S = self.S
        u = _clamp((x - S["box_left"]) / (S["box_right"] - S["box_left"]))
        v = _clamp((y - S["box_top"]) / (S["box_bottom"] - S["box_top"]))
        return u * (self.W - 1), v * (self.H - 1)

    def update(self, lm, t):
        S, ev = self.S, []
        if lm is None:
            if self.mode == "drag":
                ev.append("up")
            self.reset()
            return dict(state="nohand", pointer=None, pinch=0.0, events=ev, label="Show your hand")

        if self.seen_since is None:
            self.seen_since = t
        palm = max(self._dist(lm[WRIST], lm[MIDDLE_MCP]), 1e-4)
        d_idx = self._dist(lm[THUMB_TIP], lm[INDEX_TIP]) / palm
        d_mid = self._dist(lm[THUMB_TIP], lm[MIDDLE_TIP]) / palm
        span = S["pinch_far"] - S["pinch_close"]
        p_idx = _clamp((S["pinch_far"] - d_idx) / span)
        p_mid = _clamp((S["pinch_far"] - d_mid) / span)

        # palm anchor: midpoint of index and middle knuckles barely moves when you pinch
        ax = (lm[INDEX_MCP][0] + lm[MIDDLE_MCP][0]) / 2
        ay = (lm[INDEX_MCP][1] + lm[MIDDLE_MCP][1]) / 2
        sx, sy = self._to_screen(ax, ay)
        fx, fy = self.fx(sx, t), self.fy(sy, t)

        if t - self.seen_since < S["engage_s"]:
            self.prev_anchor = (fx, fy)
            return dict(state="tracking", pointer=None, pinch=0.0, events=ev, label="Hand found")

        if self.ptr is None:
            self.ptr = [fx, fy]
        dx, dy = (fx - self.prev_anchor[0], fy - self.prev_anchor[1]) if self.prev_anchor else (0.0, 0.0)
        self.prev_anchor = (fx, fy)

        # ---- pinch state machine with hysteresis
        if self.pinch is None:
            if d_idx < S["pinch_close"] and d_idx <= d_mid:
                self.pinch, self.pinch_t, self.pinch_anchor = "index", t, (fx, fy)
            elif d_mid < S["pinch_close"] and d_mid < d_idx:
                self.pinch, self.pinch_t, self.pinch_anchor = "middle", t, (fx, fy)
        else:
            d = d_idx if self.pinch == "index" else d_mid
            held = t - self.pinch_t
            moved = math.hypot(fx - self.pinch_anchor[0], fy - self.pinch_anchor[1])
            if d > S["pinch_open"]:                              # released
                if self.mode == "drag":
                    ev.append("up"); self.flash = ("Dropped", t)
                elif self.mode is None:
                    ev.append("click" if self.pinch == "index" else "rclick")
                    self.flash = ("Click" if self.pinch == "index" else "Right click", t)
                self.pinch, self.mode = None, None
            elif self.mode is None and (held >= S["hold_to_drag_s"] or moved > S["drag_move_px"]):
                if self.pinch == "index":
                    self.mode = "drag"; ev.append("down")
                else:
                    self.mode = "scroll"; self.scroll_rest = 0.0

        # ---- pointer: slows as the pinch closes, locks while pinched (unless dragging)
        if self.mode == "drag":
            gain = 1.0
        elif self.pinch is not None:
            gain = 0.0
        else:
            gain = (1.0 - _clamp((max(p_idx, p_mid) - 0.25) / 0.55)) ** 2
        self.ptr[0] += dx * gain
        self.ptr[1] += dy * gain
        if gain >= 0.999 and self.mode is None:      # drift back onto the absolute mapping
            k = 0.12
            self.ptr[0] += (fx - self.ptr[0]) * k
            self.ptr[1] += (fy - self.ptr[1]) * k
        self.ptr[0] = _clamp(self.ptr[0], 0, self.W - 1)
        self.ptr[1] = _clamp(self.ptr[1], 0, self.H - 1)

        if self.mode == "scroll":
            amt = dy * S["scroll_gain"] * (1 if S["natural_scroll"] else -1) + self.scroll_rest
            n = int(amt)
            self.scroll_rest = amt - n
            if n:
                ev.append(("wheel", n))

        state = self.mode or "tracking"
        if self.mode == "drag":
            label = "Release to drop"
        elif self.mode == "scroll":
            label = "Move up or down"
        elif self.flash[0] and t - self.flash[1] < 0.6:
            label = self.flash[0]
        else:
            label = "Pinch to click"
        pinch_ui = 1.0 if self.mode else max(p_idx, p_mid)
        return dict(state=state, pointer=(self.ptr[0], self.ptr[1]), pinch=pinch_ui, events=ev, label=label,
                    which=self.pinch)

# ----------------------------------------------------------------------------- rendering (pure PIL)

from PIL import Image, ImageDraw, ImageFont, ImageFilter

INK = (236, 237, 239)        # primary text
SUB = (142, 145, 154)        # secondary text
BG = (24, 25, 30)            # pill surface
LINE = (255, 255, 255, 22)   # hairline
ROSE = (232, 93, 140)        # the one accent
SS = 3                       # supersampling for clean anti-aliasing

def _font(names, size):
    roots = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
             "/usr/share/fonts/opentype/inter", "/usr/share/fonts/truetype/dejavu"]
    for n in names:
        for r in roots:
            p = os.path.join(r, n)
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass
    return ImageFont.load_default()

class Fonts:
    def __init__(self, scale):
        z = scale * SS
        self.title = _font(["SegUIVar.ttf", "seguisb.ttf", "segoeui.ttf", "Inter-SemiBold.otf", "DejaVuSans.ttf"], int(13.5 * z))
        self.sub = _font(["SegUIVar.ttf", "segoeui.ttf", "Inter-Regular.otf", "DejaVuSans.ttf"], int(12 * z))
        self.mono = _font(["CascadiaMono.ttf", "consola.ttf", "DejaVuSansMono.ttf"], int(11 * z))
        try:   # Segoe UI Variable: pick weights from the variable axis
            self.title.set_variation_by_axes([600])
            self.sub.set_variation_by_axes([400])
        except Exception:
            pass

def _shadowed(card, radius, scale):
    """Soft shadow tinted to the surface (never pure black), then the card on top."""
    pad = int(14 * scale * SS)
    W, H = card.size[0] + 2 * pad, card.size[1] + 2 * pad
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([pad, pad + int(3 * scale * SS), W - pad, H - pad + int(3 * scale * SS)],
                                         radius, fill=(8, 9, 14, 110))
    sh = sh.filter(ImageFilter.GaussianBlur(8 * scale * SS))
    out.alpha_composite(sh)
    out.alpha_composite(card, (pad, pad))
    return out, pad

def _ring(d, cx, cy, r, w, p, col, track=(255, 255, 255, 40)):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=track, width=w)
    if p > 0.01:
        d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 360 * min(p, 1.0), fill=col, width=w)

STATE_TEXT = {
    "nohand": "No hand", "tracking": "Tracking", "drag": "Dragging", "scroll": "Scrolling",
    "paused": "Paused", "nocam": "No camera", "starting": "Starting",
}

def render_pill(ui, scale, fonts, expanded=False, preview=None, box=None, lm=None):
    """ui: dict(state, label, pinch, fps, ms). Returns (RGBA image, shadow pad in px)."""
    w, h = int(244 * scale), int(46 * scale)
    pw, ph = w, h
    if expanded:
        ph = h + int(214 * scale)
    W, H = pw * SS, ph * SS
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    rad = (h * SS) // 2 if not expanded else int(18 * scale * SS)
    d.rounded_rectangle([0, 0, W - 1, H - 1], rad, fill=BG + (238,), outline=LINE, width=max(1, SS))

    st = ui.get("state", "starting")
    cx, cy, r = int(23 * scale * SS), (h * SS) // 2, int(8.5 * scale * SS)
    if st in ("tracking", "drag", "scroll"):
        _ring(d, cx, cy, r, int(2.2 * scale * SS), ui.get("pinch", 0.0), ROSE + (255,))
        if st != "tracking" or ui.get("pinch", 0) >= 0.99:
            d.ellipse([cx - r * 0.45, cy - r * 0.45, cx + r * 0.45, cy + r * 0.45], fill=ROSE + (255,))
    else:   # quiet hollow ring for idle states
        _ring(d, cx, cy, r, int(2.2 * scale * SS), 0.0, ROSE, track=(255, 255, 255, 70 if st != "nocam" else 30))

    tx = int(42 * scale * SS)
    d.text((tx, cy - int(1 * scale * SS)), STATE_TEXT.get(st, st.title()), font=fonts.title, fill=INK + (255,), anchor="ls")
    d.text((tx, cy + int(3 * scale * SS)), ui.get("label", ""), font=fonts.sub, fill=SUB + (255,), anchor="lt")
    if ui.get("fps"):
        d.text((W - int(16 * scale * SS), cy), f"{ui['fps']:.0f} fps", font=fonts.mono, fill=SUB + (255,), anchor="rm")

    if expanded:
        y0 = h * SS
        d.line([int(14 * scale * SS), y0, W - int(14 * scale * SS), y0], fill=LINE, width=max(1, SS // 2))
        m = int(12 * scale * SS)
        vw = W - 2 * m
        vh = int(vw * 3 / 4)
        vy = y0 + m
        if preview is not None:
            pv = preview.convert("L").resize((vw, vh), Image.BILINEAR)
            pv = Image.eval(pv, lambda v: int(v * 0.55) + 8).convert("RGBA")
        else:
            pv = Image.new("RGBA", (vw, vh), (16, 17, 21, 255))
        mask = Image.new("L", (vw, vh), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, vw - 1, vh - 1], int(10 * scale * SS), fill=255)
        card.paste(pv, (m, vy), mask)
        if box:
            bl, bt, br, bb = box
            d.rounded_rectangle([m + bl * vw, vy + bt * vh, m + br * vw, vy + bb * vh], int(6 * scale * SS),
                                outline=(255, 255, 255, 70), width=max(1, SS // 2 + 1))
        if lm:
            bones = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
                     (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]
            P = [(m + x * vw, vy + y * vh) for x, y in lm]
            for a, b in bones:
                d.line([P[a], P[b]], fill=(255, 255, 255, 120), width=int(1.4 * scale * SS))
            for i in (4, 8, 12):
                x, y = P[i]; rr = 3 * scale * SS
                d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=ROSE + (255,))
            ax, ay = (P[5][0] + P[9][0]) / 2, (P[5][1] + P[9][1]) / 2
            rr = 4 * scale * SS
            d.ellipse([ax - rr, ay - rr, ax + rr, ay + rr], outline=INK + (255,), width=int(1.5 * scale * SS))
        ty = vy + vh + int(9 * scale * SS)
        ms = ui.get("ms")
        stats = f"{ui.get('fps', 0):.0f} fps · {ms:.0f} ms" if ms else "waiting for camera"
        d.text((m, ty), stats, font=fonts.mono, fill=SUB + (255,), anchor="lt")
        d.text((W - m, ty), "Ctrl+Alt+H  pause", font=fonts.mono, fill=SUB + (255,), anchor="rt")

    out, pad = _shadowed(card, rad, scale)
    out = out.resize((out.size[0] // SS, out.size[1] // SS), Image.LANCZOS)
    return out, pad // SS

def render_cursor_ring(p, mode, scale, alpha=1.0):
    """Small ring that wraps the cursor while you pinch: closes as the fingers meet."""
    s = int(44 * scale)
    W = s * SS
    im = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, r, w = W / 2, W * 0.36, int(2.6 * scale * SS)
    a = int(255 * alpha)
    d.ellipse([c - r - w, c - r - w, c + r + w, c + r + w], outline=(10, 11, 16, int(90 * alpha)), width=w)
    _ring(d, c, c, r, w, 1.0 if mode else p, ROSE + (a,), track=(255, 255, 255, int(70 * alpha)))
    return im.resize((s, s), Image.LANCZOS)

# ----------------------------------------------------------------------------- first-run tutorial (pure, testable)

TUTORIAL_STEPS = [
    ("raise",  "Raise your hand",   "Hold one hand up with your palm facing the screen, about an arm's length away."),
    ("move",   "Move the pointer",  "Move your hand gently. The pointer follows your palm, so small movements are enough."),
    ("click",  "Tap to click",      "Touch your thumb to your index finger, then let go."),
    ("drag",   "Hold to drag",      "Pinch and hold, move your hand, then let go to drop."),
    ("rclick", "Right-click",       "Tap your thumb to your middle finger."),
    ("scroll", "Scroll",            "Pinch your thumb and middle finger, hold, then move your hand up or down."),
]
DONE_TITLE = "You're all set"
DONE_BODY = "Press Ctrl+Alt+H to pause at any time. Click the pill at the top of the screen to see the camera."

class Tutorial:
    """Advances only when you actually perform each gesture. While it runs, clicks,
    drags and scrolls are kept away from your desktop so practising is safe."""
    def __init__(self, screen_w):
        self.step = 0
        self.moved = 0.0
        self.wheel = 0
        self.last_ptr = None
        self.dragging = False
        self.success_t = None     # time the current step was completed
        self.done_t = None        # time the final screen appeared
        self.need_move = 0.35 * screen_w

    @property
    def kind(self):
        return TUTORIAL_STEPS[self.step][0] if self.step < len(TUTORIAL_STEPS) else "done"

    def feed(self, out, t):
        """Feed one engine output. Returns True when the whole tutorial is finished."""
        if self.done_t is not None:
            return t - self.done_t > 4.0
        if self.success_t is not None:          # brief tick before moving on
            if t - self.success_t > 0.9:
                self.step += 1
                self.success_t = None
                self.moved, self.wheel, self.dragging = 0.0, 0, False
                if self.step >= len(TUTORIAL_STEPS):
                    self.done_t = t
            return False
        k, ok = self.kind, False
        p = out.get("pointer")
        if p and self.last_ptr:
            self.moved += math.hypot(p[0] - self.last_ptr[0], p[1] - self.last_ptr[1])
        self.last_ptr = p
        ev = out.get("events", [])
        if k == "raise":
            ok = p is not None
        elif k == "move":
            ok = self.moved >= self.need_move
        elif k == "click":
            ok = "click" in ev
        elif k == "drag":
            if "down" in ev:
                self.dragging = True
            ok = self.dragging and "up" in ev
        elif k == "rclick":
            ok = "rclick" in ev
        elif k == "scroll":
            self.wheel += sum(abs(e[1]) for e in ev if isinstance(e, tuple))
            ok = self.wheel >= 240
        if ok:
            self.success_t = t
        return False

def _ease(x):
    x = _clamp(x)
    return x * x * (3 - 2 * x)

def _hand_pose(kind, ph):
    """Stylised hand for the illustration. ph is the loop phase 0..1.
    Returns (offset_x, offset_y, thumb_target 'index'|'middle'|None, closeness 0..1, alpha)."""
    ox = oy = 0.0
    target, close, alpha = None, 0.0, 1.0
    if kind == "raise":
        rise = _ease(ph / 0.5)
        oy, alpha = 60 * (1 - rise), rise
    elif kind == "move":
        a = ph * 2 * math.pi
        ox, oy = 55 * math.sin(a), 22 * math.sin(2 * a)
    elif kind in ("click", "rclick"):
        target = "index" if kind == "click" else "middle"
        close = _ease((ph - 0.25) / 0.2) - _ease((ph - 0.55) / 0.2)
    elif kind == "drag":
        target = "index"
        close = _ease((ph - 0.1) / 0.15) - _ease((ph - 0.75) / 0.15)
        ox = -45 + 90 * _ease((ph - 0.3) / 0.4)
    elif kind == "scroll":
        target = "middle"
        close = _ease((ph - 0.1) / 0.15) - _ease((ph - 0.8) / 0.12)
        oy = 30 - 60 * _ease((ph - 0.3) / 0.45)
    return ox, oy, target, close, alpha

def render_hand(kind, ph, size, scale):
    """Clean, flat hand drawing (palm facing you) in the app's two-tone style."""
    W, H = int(size[0] * SS), int(size[1] * SS)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    u = 1.3 * scale * SS
    ox, oy, target, close, alpha = _hand_pose(kind, ph)
    cx, cy = W / 2 + ox * u * 0.8, H / 2 + 30 * u + oy * u * 0.8
    a = int(255 * alpha)
    skin = (226, 228, 233, a)
    line = (24, 25, 30, a)
    # palm
    pw, phh = 62 * u, 58 * u
    d.rounded_rectangle([cx - pw / 2, cy - phh / 2, cx + pw / 2, cy + phh / 2], 22 * u, fill=skin)
    # four fingers (index .. pinky), straight up
    fw = 13.5 * u
    xs = [-22, -7.5, 7.5, 22]
    lens = [54, 60, 56, 44]
    tips = []
    for i, (fx, L) in enumerate(zip(xs, lens)):
        bx, by = cx + fx * u, cy - phh / 2 + 10 * u
        tx, ty = bx + (fx * 0.06) * u, by - L * u
        if target and ((target == "index" and i == 0) or (target == "middle" and i == 1)):
            ty += 10 * u * close          # finger curls slightly to meet the thumb
        d.line([bx, by, tx, ty], fill=skin, width=int(fw))
        d.ellipse([tx - fw / 2, ty - fw / 2, tx + fw / 2, ty + fw / 2], fill=skin)
        d.ellipse([bx - fw / 2, by - fw / 2, bx + fw / 2, by + fw / 2], fill=skin)
        tips.append((tx, ty))
    # thumb: from lower-left of the palm, swings to the target fingertip
    tb = (cx - pw / 2 + 4 * u, cy + 8 * u)
    rest_tip = (cx - pw / 2 - 30 * u, cy - 26 * u)
    if target:
        goal = tips[0] if target == "index" else tips[1]
        goal = (goal[0] - 3 * u, goal[1] + 9 * u)
        tip = (rest_tip[0] + (goal[0] - rest_tip[0]) * close, rest_tip[1] + (goal[1] - rest_tip[1]) * close)
    else:
        tip = rest_tip
    knuckle = (tb[0] + (tip[0] - tb[0]) * 0.45 - 10 * u, tb[1] + (tip[1] - tb[1]) * 0.45)
    tw = 15 * u
    d.line([tb, knuckle, tip], fill=skin, width=int(tw), joint="curve")
    for p in (tb, knuckle, tip):
        d.ellipse([p[0] - tw / 2, p[1] - tw / 2, p[0] + tw / 2, p[1] + tw / 2], fill=skin)
    # subtle palm crease so it reads as a hand, not a blob
    d.arc([cx - 20 * u, cy - 6 * u, cx + 22 * u, cy + 22 * u], 200, 330, fill=(190, 192, 200, a), width=int(1.6 * u))
    # contact ring when the pinch closes
    if target and close > 0.85:
        g = tips[0] if target == "index" else tips[1]
        g = (g[0] - 3 * u, g[1] + 4 * u)
        rr = (14 + 6 * (close - 0.85) / 0.15) * u
        d.ellipse([g[0] - rr, g[1] - rr, g[0] + rr, g[1] + rr], outline=ROSE + (a,), width=int(2.4 * u))
    # motion hints
    if kind == "scroll" and close > 0.5:
        x0 = cx + 52 * u
        for k in range(3):
            yy = cy - 30 * u + k * 13 * u
            d.line([x0, yy, x0, yy + 7 * u], fill=ROSE + (int(a * (0.4 + 0.2 * k)),), width=int(2.4 * u))
    del line
    return im.resize((int(size[0]), int(size[1])), Image.LANCZOS)

def _wrap(d, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if d.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w_
    if cur:
        lines.append(cur)
    return lines

class TutorialFonts:
    def __init__(self, scale):
        z = scale * SS
        self.title = _font(["SegUIVar.ttf", "seguisb.ttf", "segoeui.ttf", "Inter-SemiBold.otf", "DejaVuSans.ttf"], int(24 * z))
        self.body = _font(["SegUIVar.ttf", "segoeui.ttf", "Inter-Regular.otf", "DejaVuSans.ttf"], int(14.5 * z))
        self.small = _font(["SegUIVar.ttf", "segoeui.ttf", "Inter-Regular.otf", "DejaVuSans.ttf"], int(13 * z))
        self.mono = _font(["CascadiaMono.ttf", "consola.ttf", "DejaVuSansMono.ttf"], int(11 * z))
        try:
            self.title.set_variation_by_axes([650]); self.body.set_variation_by_axes([400])
            self.small.set_variation_by_axes([500])
        except Exception:
            pass

TUT_W, TUT_H, TUT_ART_H = 440, 420, 236

def tutorial_stage(scale):
    """(x, y, w, h) of the illustration stage inside the card, in final pixels (before shadow pad)."""
    return 8 * scale, 8 * scale, TUT_W * scale - 16 * scale, TUT_ART_H * scale - 8 * scale

def tutorial_period(kind):
    return 2.4 if kind in ("drag", "scroll") else 1.8

def tutorial_skip_rect(scale, pad):
    """Where 'Skip' sits inside the tutorial window (window pixels)."""
    w, h = TUT_W * scale, TUT_H * scale
    return (pad + w - 92 * scale, pad + h - 52 * scale, pad + w - 14 * scale, pad + h - 14 * scale)

def render_tutorial(tut, t, scale, fonts, live_pinch=0.0, art=True):
    W, H = int(TUT_W * scale * SS), int(TUT_H * scale * SS)
    u = scale * SS
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    rad = int(22 * u)
    d.rounded_rectangle([0, 0, W - 1, H - 1], rad, fill=BG + (246,), outline=LINE, width=max(1, SS))
    # illustration stage, a touch lighter than the card
    ah = int(TUT_ART_H * u)
    stage = Image.new("RGBA", (W - int(16 * u), ah - int(8 * u)), (34, 35, 42, 255))
    m = Image.new("L", stage.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, stage.size[0] - 1, stage.size[1] - 1], int(16 * u), fill=255)
    card.paste(stage, (int(8 * u), int(8 * u)), m)

    n = len(TUTORIAL_STEPS)
    finished = tut.done_t is not None
    ticking = tut.success_t is not None
    cx, cy = W / 2, int(8 * u) + stage.size[1] / 2
    if finished or ticking:
        p = _ease((t - (tut.done_t if finished else tut.success_t)) / 0.35)
        r = 34 * u * (0.8 + 0.2 * p)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ROSE + (int(255 * p),))
        # tick, drawn progressively
        pts = [(cx - 13 * u, cy + 1 * u), (cx - 3 * u, cy + 11 * u), (cx + 15 * u, cy - 10 * u)]
        seg = _ease((t - (tut.done_t if finished else tut.success_t) - 0.12) / 0.3)
        if seg > 0:
            l1 = math.dist(pts[0], pts[1]); l2 = math.dist(pts[1], pts[2]); L = (l1 + l2) * seg
            path = [pts[0]]
            if L <= l1:
                f = L / l1; path.append((pts[0][0] + (pts[1][0] - pts[0][0]) * f, pts[0][1] + (pts[1][1] - pts[0][1]) * f))
            else:
                f = (L - l1) / l2; path += [pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * f, pts[1][1] + (pts[2][1] - pts[1][1]) * f)]
            d.line(path, fill=(255, 255, 255, 255), width=int(4.5 * u), joint="curve")
    elif art:
        period = 2.4 if tut.kind in ("drag", "scroll") else 1.8
        hand = render_hand(tut.kind, (t % period) / period, (stage.size[0] / SS, stage.size[1] / SS), scale)
        hand = hand.resize(stage.size, Image.BICUBIC)
        card.alpha_composite(hand, (int(8 * u), int(8 * u)))
        # live feedback: your own pinch, as the same ring used around the cursor
        if tut.kind in ("click", "drag", "rclick", "scroll") and live_pinch > 0.05:
            rx, ry, rr = W - int(34 * u), int(34 * u), int(10 * u)
            _ring(d, rx, ry, rr, int(2.4 * u), live_pinch, ROSE + (255,))

    # text block
    x0 = int(32 * u)
    y = ah + int(22 * u)
    if finished:
        title, body = DONE_TITLE, DONE_BODY
    else:
        _, title, body = TUTORIAL_STEPS[min(tut.step, n - 1)]
        d.text((x0, y), f"{min(tut.step, n - 1) + 1} of {n}", font=fonts.mono, fill=SUB + (255,), anchor="lt")
    y += int(22 * u)
    d.text((x0, y), title, font=fonts.title, fill=INK + (255,), anchor="lt")
    y += int(38 * u)
    for ln in _wrap(d, body, fonts.body, W - 2 * x0):
        d.text((x0, y), ln, font=fonts.body, fill=SUB + (255,), anchor="lt")
        y += int(21 * u)

    # footer: progress dots + skip
    fy = H - int(33 * u)
    for i in range(n):
        done_i = i < tut.step or finished or (i == tut.step and ticking)
        cur_i = i == tut.step and not finished
        r = (3.6 if cur_i else 3.0) * u
        dx = x0 + i * 15 * u + r
        col = ROSE + (255,) if done_i else ((255, 255, 255, 200) if cur_i else (255, 255, 255, 55))
        d.ellipse([dx - r, fy - r, dx + r, fy + r], fill=col)
    if not finished:
        d.text((W - int(32 * u), fy), "Skip", font=fonts.small, fill=SUB + (255,), anchor="rm")
    else:
        d.text((W - int(32 * u), fy), "Done", font=fonts.small, fill=ROSE + (255,), anchor="rm")

    out, pad = _shadowed(card, rad, scale)
    out = out.resize((out.size[0] // SS, out.size[1] // SS), Image.LANCZOS)
    return out, pad // SS

# ----------------------------------------------------------------------------- Windows app

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes as wt

    user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
    user32.DefWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.CreateWindowExW.restype = wt.HWND
    user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
    gdi32.CreateDIBSection.restype = wt.HBITMAP
    gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
    gdi32.SelectObject.restype = wt.HGDIOBJ
    gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    gdi32.CreateCompatibleDC.restype = wt.HDC
    gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
    gdi32.DeleteDC.argtypes = [wt.HDC]
    user32.GetDC.restype = wt.HDC
    user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HDC,
                                           ctypes.POINTER(wt.POINT), wt.COLORREF, ctypes.c_void_p, wt.DWORD]
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.mouse_event.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
    user32.CreatePopupMenu.restype = wt.HMENU
    user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
    user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, ctypes.c_void_p]
    user32.DestroyMenu.argtypes = [wt.HMENU]
    user32.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, ctypes.c_void_p]
    user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.SetCapture.argtypes = [wt.HWND]
    user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.MessageBoxW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                    ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                    ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    WS_POPUP = 0x80000000
    WS_EX_LAYERED, WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TRANSPARENT = 0x80000, 0x8, 0x80, 0x8000000, 0x20
    WM_DESTROY, WM_TIMER, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONUP, WM_MOUSEMOVE, WM_HOTKEY, WM_COMMAND, WM_CLOSE = \
        0x2, 0x113, 0x201, 0x202, 0x205, 0x200, 0x312, 0x111, 0x10
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_WHEEL = 2, 4, 8, 16, 0x800
    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, VK_H = 1, 2, 0x4000, 0x48
    ID_PAUSE, ID_PREVIEW, ID_QUIT, ID_TUTORIAL = 1, 2, 3, 4

    def mouse(flag, data=0):
        user32.mouse_event(flag, 0, 0, ctypes.c_uint32(data & 0xFFFFFFFF).value, 0)

    class Layered:
        """A borderless, per-pixel-alpha window drawn from a PIL RGBA image."""
        _proc_keep = []
        def __init__(self, name, proc=None, click_through=False):
            hinst = kernel32.GetModuleHandleW(None)
            cb = WNDPROC(proc) if proc else WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))
            Layered._proc_keep.append(cb)
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.lpfnWndProc = cb
            wc.hInstance = hinst
            wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
            wc.lpszClassName = name
            user32.RegisterClassExW(ctypes.byref(wc))
            ex = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            if click_through:
                ex |= WS_EX_TRANSPARENT
            self.hwnd = user32.CreateWindowExW(ex, name, APP, WS_POPUP, 0, 0, 1, 1, None, None, hinst, None)
            self.visible = False
            self.pos = (0, 0)

        def update(self, img, x, y):
            w, h = img.size
            # premultiply alpha, then hand GDI a top-down BGRA buffer
            import numpy as np
            arr = np.asarray(img, dtype=np.uint16)
            al = arr[..., 3:4]
            bgra = np.empty((h, w, 4), dtype=np.uint8)
            bgra[..., 0] = (arr[..., 2] * al[..., 0] // 255)
            bgra[..., 1] = (arr[..., 1] * al[..., 0] // 255)
            bgra[..., 2] = (arr[..., 0] * al[..., 0] // 255)
            bgra[..., 3] = arr[..., 3]
            data = bgra.tobytes()
            bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            screen = user32.GetDC(None)
            mem = gdi32.CreateCompatibleDC(screen)
            bits = ctypes.c_void_p()
            hbmp = gdi32.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
            ctypes.memmove(bits, data, len(data))
            old = gdi32.SelectObject(mem, hbmp)
            blend = BLENDFUNCTION(0, 0, 255, 1)
            user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(wt.POINT(int(x), int(y))),
                                       ctypes.byref(wt.SIZE(w, h)), mem, ctypes.byref(wt.POINT(0, 0)), 0,
                                       ctypes.byref(blend), 2)
            gdi32.SelectObject(mem, old)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(None, screen)
            self.pos = (int(x), int(y))
            if not self.visible:
                user32.ShowWindow(self.hwnd, 4)   # SW_SHOWNOACTIVATE
                self.visible = True

        def hide(self):
            if self.visible:
                user32.ShowWindow(self.hwnd, 0)
                self.visible = False

    class App:
        def __init__(self):
            self.S = load_settings()
            self.sw, self.sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            try:
                self.scale = user32.GetDpiForSystem() / 96.0
            except Exception:
                self.scale = 1.0
            self.fonts = Fonts(self.scale)
            self.lock = threading.Lock()
            self.ui = dict(state="starting", label="Opening camera", pinch=0.0, fps=0, ms=0)
            self.target = None
            self.preview, self.lm = None, None
            self.paused = False
            self.expanded = False
            self.running = True
            self.ring_alpha = 0.0
            self.last_pill_key = None
            self.drag_origin = None
            self.tut = None
            self.tut_cache = {}
            self.tut_fonts = None
            self.tut_win = None
            self.tut_origin = (0, 0, 0)
            self.live_pinch = 0.0
            self.pill = Layered("HandMouse2Pill", self.wndproc)
            self.ring = Layered("HandMouse2Ring", click_through=True)
            user32.RegisterHotKey(self.pill.hwnd, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_H)
            user32.SetTimer(self.pill.hwnd, 1, 16, None)
            threading.Thread(target=self.vision_loop, daemon=True).start()
            threading.Thread(target=self.glide_loop, daemon=True).start()
            if not self.S.get("tutorial_done"):
                self.start_tutorial()

        # -- first-run tutorial
        def start_tutorial(self):
            if self.tut_win is None:
                self.tut_win = Layered("HandMouse2Tutorial", self.tut_wndproc)
                self.tut_fonts = TutorialFonts(self.scale)
            self.tut_cache = {}
            with self.lock:
                self.tut = Tutorial(self.sw)
            if self.paused:
                self.toggle_pause()

        def finish_tutorial(self):
            with self.lock:
                self.tut = None
            if self.tut_win:
                self.tut_win.hide()
            self.tut_cache = {}
            self.S["tutorial_done"] = True
            save_settings(self.S)

        def _tut_frames(self, kind):
            """Hand animation frames for one step, rendered once and reused."""
            if kind not in self.tut_cache:
                x, y, w, h = tutorial_stage(self.scale)
                n = 40
                self.tut_cache[kind] = [render_hand(kind, i / n, (int(w), int(h)), self.scale) for i in range(n)]
            return self.tut_cache[kind]

        def redraw_tutorial(self):
            with self.lock:
                tut = self.tut
                live = self.live_pinch
            if tut is None or self.tut_win is None:
                return
            now = time.perf_counter()
            key = ("base", tut.step, tut.done_t is not None)
            if tut.success_t is not None or tut.done_t is not None:
                img, pad = render_tutorial(tut, now, self.scale, self.tut_fonts)
            else:
                if self.tut_cache.get("_key") != key:
                    base, pad = render_tutorial(tut, now, self.scale, self.tut_fonts, art=False)
                    self.tut_cache["_key"], self.tut_cache["_base"], self.tut_cache["_pad"] = key, base, pad
                base, pad = self.tut_cache["_base"], self.tut_cache["_pad"]
                frames = self._tut_frames(tut.kind)
                ph = (now % tutorial_period(tut.kind)) / tutorial_period(tut.kind)
                img = base.copy()
                sx, sy, sw, sh = tutorial_stage(self.scale)
                img.alpha_composite(frames[int(ph * len(frames)) % len(frames)], (int(pad + sx), int(pad + sy)))
                if tut.kind in ("click", "drag", "rclick", "scroll") and live > 0.05:
                    d = ImageDraw.Draw(img)
                    rx, ry = pad + sx + sw - 26 * self.scale, pad + sy + 26 * self.scale
                    _ring(d, rx, ry, 9 * self.scale, max(2, int(2.2 * self.scale)), live, ROSE + (255,))
            x = (self.sw - img.size[0]) // 2
            y = (self.sh - img.size[1]) // 2
            self.tut_origin = (x, y, pad)
            self.tut_win.update(img, x, y)

        def _over_tut_button(self, sx, sy):
            x, y, pad = self.tut_origin
            l, t, r, b = tutorial_skip_rect(self.scale, pad)
            return x + l <= sx <= x + r and y + t <= sy <= y + b

        def tut_wndproc(self, h, msg, wp, lp):
            if msg == WM_LBUTTONUP:
                pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
                if self._over_tut_button(pt.x, pt.y):
                    self.finish_tutorial()
                return 0
            return user32.DefWindowProcW(h, msg, wp, lp)

        # -- pill position: top centre by default, like a status island
        def pill_origin(self, img_w, pad):
            if self.S.get("pill_x") is not None:
                return int(self.S["pill_x"]), int(self.S["pill_y"])
            return (self.sw - img_w) // 2, int(10 * self.scale) - pad

        def redraw_pill(self, force=False):
            with self.lock:
                ui = dict(self.ui)
                prev, lm = self.preview, self.lm
            if self.paused:
                ui.update(state="paused", label="Ctrl+Alt+H to resume", pinch=0.0)
            key = (ui["state"], ui["label"], round(ui.get("pinch", 0), 2), int(ui.get("fps", 0)), self.expanded)
            if not force and key == self.last_pill_key and not self.expanded:
                return
            self.last_pill_key = key
            img, pad = render_pill(ui, self.scale, self.fonts, self.expanded, prev,
                                   (self.S["box_left"], self.S["box_top"], self.S["box_right"], self.S["box_bottom"]), lm)
            x, y = self.pill_origin(img.size[0], pad)
            self.pill.update(img, x, y)

        def redraw_ring(self):
            with self.lock:
                ui = dict(self.ui)
            want = (not self.paused) and ui["state"] in ("tracking", "drag", "scroll") and (ui["pinch"] > 0.08 or ui["state"] != "tracking")
            self.ring_alpha += ((1.0 if want else 0.0) - self.ring_alpha) * 0.25
            if self.ring_alpha < 0.03:
                self.ring.hide()
                return
            pt = wt.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            img = render_cursor_ring(ui["pinch"], ui["state"] in ("drag", "scroll"), self.scale, self.ring_alpha)
            self.ring.update(img, pt.x - img.size[0] // 2, pt.y - img.size[1] // 2)

        def toggle_pause(self):
            self.paused = not self.paused
            if self.paused:
                with self.lock:
                    self.target = None
            self.redraw_pill(True)

        def menu(self):
            m = user32.CreatePopupMenu()
            user32.AppendMenuW(m, 0, ID_PAUSE, "Resume tracking" if self.paused else "Pause tracking\tCtrl+Alt+H")
            user32.AppendMenuW(m, 0x8 if self.expanded else 0, ID_PREVIEW, "Show camera")
            user32.AppendMenuW(m, 0, ID_TUTORIAL, "Show tutorial")
            user32.AppendMenuW(m, 0x800, 0, None)
            user32.AppendMenuW(m, 0, ID_QUIT, "Quit HandMouse")
            pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(self.pill.hwnd)
            cmd = user32.TrackPopupMenu(m, 0x100 | 0x8, pt.x, pt.y, 0, self.pill.hwnd, None)  # RETURNCMD | RIGHTBUTTON
            user32.DestroyMenu(m)
            if cmd == ID_PAUSE:
                self.toggle_pause()
            elif cmd == ID_PREVIEW:
                self.expanded = not self.expanded; self.redraw_pill(True)
            elif cmd == ID_TUTORIAL:
                self.start_tutorial()
            elif cmd == ID_QUIT:
                user32.PostMessageW(self.pill.hwnd, WM_CLOSE, 0, 0)

        def wndproc(self, h, msg, wp, lp):
            try:
                if msg == WM_TIMER:
                    self.redraw_pill(); self.redraw_ring()
                    if getattr(self, "tut_finish_req", False):
                        self.tut_finish_req = False
                        self.finish_tutorial()
                    if self.tut is not None:
                        self.tick = getattr(self, "tick", 0) + 1
                        if self.tick % 2 == 0:
                            self.redraw_tutorial()
                    return 0
                if msg == WM_HOTKEY:
                    self.toggle_pause(); return 0
                if msg == WM_LBUTTONDOWN:
                    pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
                    self.drag_origin = (pt.x, pt.y, self.pill.pos, False)
                    user32.SetCapture(h); return 0
                if msg == WM_MOUSEMOVE and self.drag_origin:
                    pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
                    ox, oy, (px, py), moved = self.drag_origin
                    if moved or abs(pt.x - ox) + abs(pt.y - oy) > 4:
                        self.drag_origin = (ox, oy, (px, py), True)
                        user32.SetWindowPos(h, None, px + pt.x - ox, py + pt.y - oy, 0, 0, 0x1 | 0x4 | 0x10)
                        self.pill.pos = (px + pt.x - ox, py + pt.y - oy)
                    return 0
                if msg == WM_LBUTTONUP and self.drag_origin:
                    user32.ReleaseCapture()
                    moved = self.drag_origin[3]
                    self.drag_origin = None
                    if moved:
                        self.S["pill_x"], self.S["pill_y"] = self.pill.pos
                        save_settings(self.S)
                    else:
                        self.expanded = not self.expanded
                    self.redraw_pill(True); return 0
                if msg == WM_RBUTTONUP:
                    self.menu(); return 0
                if msg == WM_CLOSE:
                    user32.DestroyWindow(h); return 0
                if msg == WM_DESTROY:
                    self.running = False
                    user32.PostQuitMessage(0); return 0
            except Exception:
                pass
            return user32.DefWindowProcW(h, msg, wp, lp)

        # -- 120 Hz cursor glide between camera frames
        def glide_loop(self):
            cur, last = None, None
            tau = max(self.S["glide_ms"], 1) / 1000.0
            prev_t = time.perf_counter()
            while self.running:
                time.sleep(1 / 120)
                now = time.perf_counter(); dt = now - prev_t; prev_t = now
                with self.lock:
                    tgt = self.target
                if tgt is None or self.paused:
                    cur = None; continue
                if cur is None:
                    pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
                    cur = [float(pt.x), float(pt.y)]
                k = 1.0 - math.exp(-dt / tau)
                cur[0] += (tgt[0] - cur[0]) * k
                cur[1] += (tgt[1] - cur[1]) * k
                p = (int(round(cur[0])), int(round(cur[1])))
                if p != last:
                    user32.SetCursorPos(*p); last = p

        # -- camera + hand model, its own thread so the UI never stutters
        def open_camera(self):
            import cv2
            cap = cv2.VideoCapture(self.S["camera_index"], cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(self.S["camera_index"])
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.S["frame_w"])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.S["frame_h"])
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap

        def vision_loop(self):
            import cv2
            _stub_matplotlib()
            import mediapipe as mp
            hands = mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=1, model_complexity=0,
                                             min_detection_confidence=0.6, min_tracking_confidence=0.5)
            eng = GestureEngine(self.S, self.sw, self.sh)
            cap, fps, ms = None, 0.0, 0.0
            last_frame = time.perf_counter()
            down = False
            while self.running:
                if self.paused:
                    if cap is not None:
                        if down:
                            mouse(MOUSEEVENTF_LEFTUP); down = False
                        cap.release(); cap = None; eng.reset()   # camera light goes off while paused
                    time.sleep(0.1); continue
                if cap is None:
                    cap = self.open_camera()
                    if not cap.isOpened():
                        with self.lock:
                            self.ui.update(state="nocam", label="Check your webcam", pinch=0.0)
                        cap.release(); cap = None; time.sleep(2.0); continue
                ok, frame = cap.read()
                if not ok:
                    cap.release(); cap = None; time.sleep(0.5); continue
                t0 = time.perf_counter()
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                res = hands.process(rgb)
                lm = None
                if res.multi_hand_landmarks:
                    lm = [(p.x, p.y) for p in res.multi_hand_landmarks[0].landmark]
                out = eng.update(lm, time.perf_counter())
                events = out["events"]
                with self.lock:
                    tut = self.tut
                    self.live_pinch = out["pinch"]
                if tut is not None:
                    pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
                    if ("click" in events) and self._over_tut_button(pt.x, pt.y):
                        self.tut_finish_req = True
                    elif tut.feed(out, time.perf_counter()):
                        self.tut_finish_req = True
                    if down:
                        mouse(MOUSEEVENTF_LEFTUP); down = False
                    events = []           # practice mode: nothing reaches the desktop
                for e in events:
                    if e == "click":
                        mouse(MOUSEEVENTF_LEFTDOWN); mouse(MOUSEEVENTF_LEFTUP)
                    elif e == "rclick":
                        mouse(MOUSEEVENTF_RIGHTDOWN); mouse(MOUSEEVENTF_RIGHTUP)
                    elif e == "down":
                        mouse(MOUSEEVENTF_LEFTDOWN); down = True
                    elif e == "up":
                        mouse(MOUSEEVENTF_LEFTUP); down = False
                    elif isinstance(e, tuple) and e[0] == "wheel":
                        mouse(MOUSEEVENTF_WHEEL, e[1])
                t1 = time.perf_counter()
                ms = 0.9 * ms + 0.1 * (t1 - t0) * 1000 if ms else (t1 - t0) * 1000
                inst = 1.0 / max(t1 - last_frame, 1e-3); last_frame = t1
                fps = 0.9 * fps + 0.1 * inst if fps else inst
                small = None
                if self.expanded:
                    small = Image.fromarray(cv2.resize(rgb, (220, 165), interpolation=cv2.INTER_AREA))
                with self.lock:
                    self.target = out["pointer"]
                    self.ui = dict(state=out["state"], label=out["label"], pinch=out["pinch"], fps=fps, ms=ms)
                    self.preview, self.lm = small, lm
            if down:
                mouse(MOUSEEVENTF_LEFTUP)
            if cap is not None:
                cap.release()

        def run(self):
            self.redraw_pill(True)
            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            self.running = False
            time.sleep(0.15)

# ----------------------------------------------------------------------------- entry

def selftest(path):
    lines = []
    try:
        import numpy as np, cv2
        _stub_matplotlib()
        import mediapipe as mp
        h = mp.solutions.hands.Hands(static_image_mode=True, max_num_hands=1, model_complexity=0)
        h.process(np.zeros((480, 640, 3), np.uint8))
        lines.append("model ok")
        img, _ = render_pill(dict(state="tracking", label="Pinch to click", pinch=0.4, fps=30, ms=14), 1.0, Fonts(1.0))
        lines.append(f"render ok {img.size}")
        lines.append("PASS")
    except Exception as e:
        import traceback
        lines.append("FAIL " + repr(e)); lines.append(traceback.format_exc())
    with open(path, "w") as f:
        f.write("\n".join(lines))

def main():
    if "--selftest" in sys.argv:
        selftest(sys.argv[sys.argv.index("--selftest") + 1]); return
    if sys.platform != "win32":
        print("HandMouse 2 runs on Windows."); return
    # one instance only
    ctypes.windll.kernel32.CreateMutexW(None, False, "HandMouse2SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:
        return
    try:
        App().run()
    except Exception as e:
        import traceback
        with open(os.path.join(app_dir(), "HandMouse2_error.txt"), "w") as f:
            f.write(traceback.format_exc())
        user32.MessageBoxW(None, f"HandMouse hit an error:\n{e}", APP, 0x10)

if __name__ == "__main__":
    main()
