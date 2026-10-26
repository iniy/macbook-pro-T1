# SPDX-License-Identifier: MIT
"""Retina-sized control glyphs and consistent rounded, single-row keys."""
import cairo
import math
from pathlib import Path
import gi
gi.require_foreign('cairo')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo
import icons

# App-local fonts: neither desktop preferences nor system font files change.
FONT_MAP = PangoCairo.FontMap.new()
FONT_MAP.set_resolution(96)
for filename in ('Inter-Regular.otf', 'Inter-Medium.otf'):
    if not FONT_MAP.add_font_file(str(Path(__file__).parent / 'assets' / filename)):
        raise RuntimeError('Could not load bundled Touch Bar font')

PLATE = (53/255,) * 3
PRESSED = (76/255,) * 3
ACCENT = (0, 122/255, 1)
FOREGROUND = (242/255,) * 3

# Native geometry from the original T1Bridge face. Esc and audio retain their
# familiar positions when application actions occupy the middle section.
STOCK = {
    'key:1': (0, 162),
    'light:down': (194, 182), 'light:up': (384, 182),
    'backlight:down': (602, 182), 'backlight:up': (792, 182),
    'media:previous': (1010, 182), 'media:play-pause': (1200, 182),
    'media:next': (1390, 182),
    'audio:mute': (1608, 182), 'audio:down': (1798, 182), 'audio:up': (1988, 182),
}


def regions(scene, width, height):
    if not scene.buttons:
        return []
    sx = width / 2170
    def box(x, w, button):
        return (round(x*sx), 0, round((x+w)*sx)-round(x*sx), height, button)
    if scene.kind in ('shell-dialog', 'app-dialog'):
        gap = 16
        widths = [200, 280] if len(scene.buttons) == 2 else [280] * len(scene.buttons)
        start = (2170 - sum(widths) - gap * (len(widths) - 1)) / 2
        result = []
        for button_width, button in zip(widths, scene.buttons):
            result.append(box(start, button_width, button))
            start += button_width + gap
        return result
    if scene.kind == 'fingerprint':
        return [box(0, 182, scene.buttons[0])]
    if scene.kind == 'function':
        step = 2170 / len(scene.buttons)
        return [box(i*step + (5 if i else 0), step - (10 if i else 5), button)
                for i, button in enumerate(scene.buttons)]
    contextual = [b for b in scene.buttons if b.action not in STOCK]
    if not contextual:
        return [box(*STOCK[b.action], b) for b in scene.buttons]
    step = min(280, (1572 - 194 + 8) / len(contextual))
    start = 194 + (1572 - 194 - (len(contextual)*step - 8)) / 2
    slots = {b.action: (start + i*step, step - 8) for i, b in enumerate(contextual)}
    return [box(*(STOCK[b.action] if b.action in STOCK else slots[b.action]), b) for b in scene.buttons]


def hit_test(regions, x, y):
    return next((button.action for left, top, width, height, button in regions
                 if button.enabled and left <= x < left+width and top <= y < top+height), None)


def text(ctx, label, x, y, width, height, size, color, alignment=Pango.Alignment.CENTER, medium=True):
    context = FONT_MAP.create_context()
    PangoCairo.update_context(ctx, context)
    PangoCairo.context_set_resolution(context, 96)
    options = cairo.FontOptions()
    options.set_antialias(cairo.ANTIALIAS_GRAY)
    options.set_hint_style(cairo.HINT_STYLE_SLIGHT)
    options.set_hint_metrics(cairo.HINT_METRICS_ON)
    PangoCairo.context_set_font_options(context, options)
    layout = Pango.Layout.new(context)
    layout.set_text(label, -1)
    font = Pango.FontDescription()
    font.set_family('Inter')
    font.set_weight(Pango.Weight.MEDIUM if medium else Pango.Weight.NORMAL)
    # Panel pixels, independent of the user's desktop DPI/font scaling.
    font.set_absolute_size(size * Pango.SCALE)
    layout.set_font_description(font)
    layout.set_width(max(1, int(width)) * Pango.SCALE)
    layout.set_ellipsize(Pango.EllipsizeMode.END)
    layout.set_single_paragraph_mode(True)
    layout.set_alignment(alignment)
    _, logical = layout.get_pixel_extents()
    ctx.set_source_rgb(*color)
    ctx.move_to(x, y + (height - logical.height) / 2 - logical.y)
    PangoCairo.show_layout(ctx, layout)


def rounded(ctx, x, y, width, height, radius):
    radius = min(radius, height / 2, width / 2)
    ctx.new_sub_path()
    for cx, cy, start in ((x+width-radius, y+radius, -math.pi/2),
                          (x+width-radius, y+height-radius, 0),
                          (x+radius, y+height-radius, math.pi/2),
                          (x+radius, y+radius, math.pi)):
        ctx.arc(cx, cy, radius, start, start + math.pi/2)
    ctx.close_path()
    ctx.fill()


def animation_frame(scene, elapsed):
    # Cosmetic frames must not change the scene signature or reset a held tap.
    # Match the original 150 ms overlay fade using the existing 40 ms poll.
    if scene.kind == 'fingerprint' and scene.buttons:
        return min(int(max(0, elapsed) * 25), 4)
    return None


def fingerprint_guidance(ctx, scene, width, height, frame):
    if not scene.buttons:
        # Keep the existing completed-verification presentation unchanged.
        text(ctx, scene.title, 16, 0, width - 230*width/2170, height,
             26*height/60, FOREGROUND, Pango.Alignment.LEFT, False)
        return
    ctx.save()
    ctx.scale(width / 2170, height / 60)
    ctx.push_group()
    # Keep the label beside the physical sensor. Reserve the far-left Cancel
    # target and the original T1Bridge right margin, arrow width and label gap.
    text(ctx, scene.title, 220, 0, 1877, 60, 26, FOREGROUND,
         Pango.Alignment.RIGHT, False)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_width(2.2)
    ctx.set_source_rgb(*FOREGROUND)
    ctx.move_to(2114, 30)
    ctx.line_to(2152, 30)
    ctx.move_to(2144, 22)
    ctx.line_to(2152, 30)
    ctx.line_to(2144, 38)
    ctx.stroke()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(min(1, frame * .04 / .15))
    ctx.restore()


def draw(surface, scene, width, height, pressed=None, frame=4):
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(0, 0, 0)
    ctx.paint()
    if scene.kind == 'blank':
        surface.flush()
        return []
    boxes = regions(scene, width, height)
    sy = height / 60
    if scene.kind == 'fingerprint':
        fingerprint_guidance(ctx, scene, width, height, frame)
    for i, (x, y, w, h, button) in enumerate(boxes):
        primary = button.suggested or (scene.kind == 'shell-dialog' and len(boxes) == 2 and i == 1)
        held = button.action == pressed and button.enabled
        fill = ((.18, .57, 1) if held else ACCENT) if primary and button.enabled else PRESSED if held else PLATE
        ctx.set_source_rgb(*fill)
        rounded(ctx, x, y, w, h, 8*sy)
        if icons.draw(ctx, button.action, x, y, w, h, button.enabled):
            continue
        color = FOREGROUND if button.enabled else (.43,) * 3
        text(ctx, button.label, x+12, y, w-24, h, 26*sy, color)
    if scene.progress >= 0:
        ctx.set_source_rgb(*ACCENT)
        ctx.rectangle(0, height - 3, width * scene.progress / 100, 3)
        ctx.fill()
    surface.flush()
    return boxes
