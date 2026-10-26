# SPDX-License-Identifier: MIT
"""Original T1Bridge control glyphs rendered from licensed alpha masks.

Cupertino/Myna UI artwork and provenance are in assets/; these are not extracted
Apple assets. Local masks keep the face independent of GTK themes.
"""
import base64
from functools import lru_cache
import json
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


def draw(ctx, action, x, y, width, height, enabled=True):
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
