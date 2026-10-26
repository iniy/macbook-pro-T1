# SPDX-License-Identifier: MIT
"""Original T1Bridge control glyphs rendered from licensed alpha masks.

Cupertino/Myna UI artwork and provenance are in assets/; these are not extracted
Apple assets. Local masks keep the face independent of GTK themes.
"""
import base64
from functools import lru_cache
import json
import math
from pathlib import Path
import zlib
import cairo

MASKS = json.loads((Path(__file__).parent / 'assets/controls.json').read_text())
ICONS = {
    'light:down': 'DISPLAY_DOWN', 'light:up': 'DISPLAY_UP',
    'backlight:down': 'KEYBOARD_DOWN', 'backlight:up': 'KEYBOARD_UP',
    'media:previous': 'PREVIOUS', 'media:play-pause': 'PLAY_PAUSE', 'media:next': 'NEXT',
    'audio:mute': 'MUTE', 'audio:down': 'VOLUME_DOWN', 'audio:up': 'VOLUME_UP',
}


@lru_cache(maxsize=10)
def surface(name):
    mask = MASKS[name]
    width, height = mask['width'], mask['height']
    raw = zlib.decompress(base64.b64decode(mask['alpha']))
    if len(raw) != width * height:
        raise ValueError('Invalid control glyph')
    stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_A8, width)
    pixels = bytearray(stride * height)
    for row in range(height):
        pixels[row*stride:row*stride+width] = raw[row*width:(row+1)*width]
    return cairo.ImageSurface.create_for_data(pixels, cairo.FORMAT_A8, width, height, stride)


def draw_profile(ctx, name, x, y, width, height, enabled):
    if name not in ('back', 'forward', 'reload', 'new-tab', 'search', 'address', 'new-folder', 'more'):
        return False
    # Original vector artwork in the same monochrome style and panel pixel
    # scale as the existing control masks. Never depend on theme icons/fonts.
    scale = min(height / 60, (width - 12) / 32)
    ctx.save()
    ctx.translate(x + (width - 32*scale)/2, y + (height - 32*scale)/2)
    ctx.scale(scale, scale)
    ctx.set_source_rgb(*((242/255,) * 3 if enabled else (.43,) * 3))
    ctx.set_line_width(2.2)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    if name in ('back', 'forward'):
        outer, inner = (21, 10) if name == 'back' else (11, 22)
        ctx.move_to(outer, 5)
        ctx.line_to(inner, 16)
        ctx.line_to(outer, 27)
    elif name == 'reload':
        ctx.arc(16, 16, 10, math.pi/6, 2*math.pi - math.pi/6)
        ctx.move_to(25, 4)
        ctx.line_to(25, 12)
        ctx.line_to(17, 12)
    elif name == 'new-tab':
        ctx.move_to(16, 5)
        ctx.line_to(16, 27)
        ctx.move_to(5, 16)
        ctx.line_to(27, 16)
    elif name == 'search':
        ctx.arc(13, 13, 9, 0, 2*math.pi)
        ctx.move_to(19.5, 19.5)
        ctx.line_to(28, 28)
    elif name == 'address':
        ctx.arc(16, 16, 12, 0, 2*math.pi)
        ctx.move_to(4, 16)
        ctx.line_to(28, 16)
        ctx.save()
        ctx.translate(16, 16)
        ctx.scale(.5, 1)
        ctx.new_sub_path()
        ctx.arc(0, 0, 12, 0, 2*math.pi)
        ctx.restore()
    elif name == 'new-folder':
        ctx.move_to(3, 9)
        ctx.line_to(12, 9)
        ctx.line_to(15, 12)
        ctx.line_to(29, 12)
        ctx.line_to(29, 27)
        ctx.line_to(3, 27)
        ctx.close_path()
        ctx.move_to(16, 19.5)
        ctx.line_to(24, 19.5)
        ctx.move_to(20, 15.5)
        ctx.line_to(20, 23.5)
    else:
        for center in (6, 16, 26):
            ctx.new_sub_path()
            ctx.arc(center, 16, 1.8, 0, 2*math.pi)
        ctx.fill()
    ctx.stroke()
    ctx.restore()
    return True


def draw(ctx, action, x, y, width, height, enabled=True, icon=''):
    if icon and draw_profile(ctx, icon, x, y, width, height, enabled):
        return True
    name = ICONS.get(action)
    if name is None:
        return False
    mask = surface(name)
    scale = min(height / 60, (width - 12) / mask.get_width())
    ctx.save()
    ctx.translate(x + (width - mask.get_width()*scale)/2,
                  y + (height - mask.get_height()*scale)/2)
    ctx.scale(scale, scale)
    ctx.set_source_rgb(*((242/255,) * 3 if enabled else (.43,) * 3))
    ctx.mask_surface(mask, 0, 0)
    ctx.restore()
    return True
