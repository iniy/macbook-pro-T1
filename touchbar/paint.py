# SPDX-License-Identifier: MIT
"""Retina-sized control glyphs and consistent rounded, single-row keys."""
import cairo
import math
import io
from functools import lru_cache
from pathlib import Path
import gi
gi.require_foreign('cairo')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo
import icons
from thumbnails import HEIGHT as FILMSTRIP_HEIGHT, tile_bounds, PREVIEW_WIDTH, PREVIEW_HEIGHT, PREVIEW_COLUMNS

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
    if scene.kind == 'volume':
        slots = {'volume:level': (scene.volume['left'], scene.volume['width']),
                 'volume:close': (scene.volume['close_left'], 80)}
        return [box(*slots[b.action], b) for b in scene.buttons]
    if scene.kind == 'video':
        slots = {'video:backward': (194, 112), 'video:toggle': (314, 112),
                 'video:forward': (434, 112), 'video:seek': (574, 998)}
        return [box(*(slots[b.action] if b.action in slots else STOCK[b.action]), b)
                for b in scene.buttons]
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


def seek_fraction(regions, x, y):
    for left, top, width, height, button in regions:
        if button.action == 'video:seek' and button.enabled:
            start, end = left + width * 90/998, left + width * 890/998
            return max(0, min(1, (x - start) / (end - start)))
    return 0


def volume_fraction(regions, x, y):
    for left, top, width, height, button in regions:
        if button.action == 'volume:level' and button.enabled:
            start, end = left + width * 113/502, left + width * 389/502
            return max(0, min(1, (x-start)/(end-start)))
    return 0


def volume_slider(ctx, state, x, y, width, height, enabled, active):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(width/502, height/54)
    ctx.set_source_rgb(*(55/255,) * 3)
    rounded(ctx, 0, 5, 502, 42, 8)
    icons.draw(ctx, 'audio:down', 32, 8, 38, 36, enabled)
    icons.draw(ctx, 'audio:up', 430, 8, 44, 36, enabled)
    ctx.set_source_rgb(*((.42,) * 3 if enabled else (.25,) * 3))
    rounded(ctx, 113, 24, 276, 6, 3)
    if enabled:
        fraction = state['level']
        ctx.set_source_rgb(*((.42,) * 3 if state['muted'] else (57/255, 130/255, 204/255)))
        if fraction:
            rounded(ctx, 113, 24, 276*fraction, 6, 3)
        ctx.set_source_rgb(1, 1, 1)
        rounded(ctx, 113 + 276*fraction - 21, 5, 42, 42, 9)
    ctx.restore()


def volume_close(ctx, x, y, width, height, active):
    ctx.save()
    ctx.translate(x+width/2, y+height/2)
    ctx.scale(height/54, height/54)
    ctx.set_source_rgb(*((.85,) * 3 if active else (.7,) * 3))
    ctx.arc(0, 0, 15, 0, 2*math.pi)
    ctx.fill()
    ctx.set_source_rgb(0, 0, 0)
    ctx.set_line_width(3.5)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.move_to(-5, -5)
    ctx.line_to(5, 5)
    ctx.move_to(5, -5)
    ctx.line_to(-5, 5)
    ctx.stroke()
    ctx.restore()


def time_label(microseconds):
    seconds = max(0, int(microseconds / 1_000_000))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'


@lru_cache(maxsize=4)
def filmstrip_surface(png):
    return cairo.ImageSurface.create_from_png(io.BytesIO(png))


def glass_lens(ctx, filmstrip, fraction, active, lens_frames=None):
    width, height = 74, 52
    left = max(90, min(890-width, 90 + 800*fraction - width/2))
    top = 4
    # A soft shadow lifts the lens above the filmstrip without moving the rail.
    for spread, alpha in ((4, .10), (2, .20), (0, .45)):
        ctx.set_source_rgba(0, 0, 0, alpha)
        rounded(ctx, left-spread, top+2-spread/2, width+spread*2, height+spread, 10+spread)
    ctx.save()
    rounded(ctx, left, top, width, height, 10, fill=False)
    ctx.clip()
    # Dissolve dense preview frames inside the glass, independently of the
    # twelve spaced thumbnails below it. Add weighted premultiplied pixels so
    # the dissolve stays opaque instead of briefly darkening between frames.
    frames = lens_frames or ((filmstrip.frame_at(fraction), 1),)
    ctx.push_group()
    ctx.set_operator(cairo.OPERATOR_ADD)
    for index, weight in frames:
        ctx.save()
        ctx.translate(left, top)
        if filmstrip.positions:
            image = filmstrip_surface(filmstrip.previews)
            ctx.scale(width/PREVIEW_WIDTH, height/PREVIEW_HEIGHT)
            ctx.set_source_surface(image, -(index % PREVIEW_COLUMNS)*PREVIEW_WIDTH,
                                   -(index // PREVIEW_COLUMNS)*PREVIEW_HEIGHT)
        else:
            image = filmstrip_surface(filmstrip.png)
            start, end = tile_bounds(index)
            ctx.scale(width/(end-start), height/FILMSTRIP_HEIGHT)
            ctx.set_source_surface(image, -start, 0)
        ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
        ctx.paint_with_alpha(weight)
        ctx.restore()
    ctx.pop_group_to_source()
    ctx.set_operator(cairo.OPERATOR_OVER)
    ctx.paint()
    glass = cairo.LinearGradient(left, top, left+width*.35, top+height)
    for stop, alpha in ((0, .48), (.34, .18), (.52, .04), (.54, .14), (1, .07)):
        glass.add_color_stop_rgba(stop, .87, .95, 1, alpha)
    ctx.set_source(glass)
    ctx.paint()
    shade = cairo.LinearGradient(0, top, 0, top+height)
    shade.add_color_stop_rgba(0, 0, 0, 0, 0)
    shade.add_color_stop_rgba(.65, 0, 0, 0, 0)
    shade.add_color_stop_rgba(1, 0, .02, .05, .22)
    ctx.set_source(shade)
    ctx.paint()
    ctx.restore()
    rim = cairo.LinearGradient(0, top, 0, top+height)
    rim.add_color_stop_rgba(0, 1, 1, 1, 1)
    rim.add_color_stop_rgba(.45, .78, .9, 1, .85)
    rim.add_color_stop_rgba(1, .92, .97, 1, .95)
    ctx.set_source(rim)
    ctx.set_line_width(2.5 if active else 2)
    rounded(ctx, left+1, top+1, width-2, height-2, 9, fill=False)
    ctx.stroke()
    ctx.set_source_rgba(1, 1, 1, .4)
    ctx.set_line_width(1)
    rounded(ctx, left+3, top+3, width-6, height-6, 7, fill=False)
    ctx.stroke()


def timeline(ctx, video, x, y, width, height, enabled, position, scrub_fraction, lens_frames=None):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(width / 998, height / 60)
    length = video['length']
    position = video['position'] if position is None else position
    if scrub_fraction is not None and length:
        position = int(length * scrub_fraction)
    color = FOREGROUND if enabled else (.43,) * 3
    text(ctx, time_label(position), 6, 0, 78, 60, 20, color, medium=False)
    remaining = '−' + time_label(max(0, length - position)) if length else '—:—'
    text(ctx, remaining, 900, 0, 92, 60, 20, color, medium=False)
    filmstrip = video.get('filmstrip')
    if filmstrip and enabled and length:
        ctx.save()
        rounded(ctx, 90, 9, 800, 42, 5, fill=False)
        ctx.clip()
        image = filmstrip_surface(filmstrip.png)
        ctx.set_source_surface(image, 90, 9)
        ctx.paint()
        ctx.set_source_rgba(0, 0, 0, .15)
        ctx.paint()
        ctx.restore()
        fraction = max(0, min(1, position / length))
        glass_lens(ctx, filmstrip, fraction, scrub_fraction is not None, lens_frames)
        ctx.restore()
        return
    ctx.set_source_rgb(*((.42,) * 3 if enabled else (.25,) * 3))
    rounded(ctx, 90, 27, 800, 6, 3)
    if length > 0:
        fraction = max(0, min(1, position / length))
        ctx.set_source_rgb(*color)
        if fraction:
            rounded(ctx, 90, 27, 800 * fraction, 6, 3)
        if enabled:
            ctx.arc(90 + 800 * fraction, 30, 6 if scrub_fraction is None else 8, 0, 2*math.pi)
            ctx.fill()
    ctx.restore()


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


def rounded(ctx, x, y, width, height, radius, fill=True):
    radius = min(radius, height / 2, width / 2)
    ctx.new_sub_path()
    for cx, cy, start in ((x+width-radius, y+radius, -math.pi/2),
                          (x+width-radius, y+height-radius, 0),
                          (x+radius, y+height-radius, math.pi/2),
                          (x+radius, y+radius, math.pi)):
        ctx.arc(cx, cy, radius, start, start + math.pi/2)
    ctx.close_path()
    if fill:
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


def draw(surface, scene, width, height, pressed=None, frame=4, position=None, scrub_fraction=None, lens_frames=None):
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
        if scene.kind == 'volume':
            if button.action == 'volume:level':
                volume_slider(ctx, scene.volume, x, y, w, h, button.enabled, held)
            else:
                volume_close(ctx, x, y, w, h, held)
            continue
        fill = ((.18, .57, 1) if held else ACCENT) if primary and button.enabled else PRESSED if held else PLATE
        if button.action == 'audio:mute' and scene.volume and scene.volume['muted']:
            fill = (1, .35, .31) if held else (1, .23, .19)
        ctx.set_source_rgb(*fill)
        rounded(ctx, x, y, w, h, 8*sy)
        if button.action == 'video:seek' and scene.playback:
            timeline(ctx, scene.playback, x, y, w, h, button.enabled, position, scrub_fraction, lens_frames)
            continue
        if icons.draw(ctx, button.action, x, y, w, h, button.enabled, button.icon):
            continue
        color = FOREGROUND if button.enabled else (.43,) * 3
        text(ctx, button.label, x+12, y, w-24, h, 26*sy, color)
    if scene.progress >= 0:
        ctx.set_source_rgb(*ACCENT)
        ctx.rectangle(0, height - 3, width * scene.progress / 100, 3)
        ctx.fill()
    surface.flush()
    return boxes
