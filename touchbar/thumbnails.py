# SPDX-License-Identifier: MIT
"""Bounded, cookie-free YouTube storyboards; thumbnail work never blocks input."""
from dataclasses import dataclass
from bisect import bisect_left
import hashlib
import io
import json
import re
import threading
import time
import urllib.parse
import urllib.request

WIDTH, HEIGHT, CELLS, GAP = 800, 42, 12, 8
PREVIEW_WIDTH, PREVIEW_HEIGHT, PREVIEW_COLUMNS, MAX_PREVIEWS = 74, 52, 20, 240


def tile_bounds(index):
    return round(index*WIDTH/CELLS) + GAP//2, round((index+1)*WIDTH/CELLS) - GAP//2


def youtube_id(url):
    if not isinstance(url, str) or len(url) > 8192:
        return None
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https'):
        return None
    if parsed.hostname == 'youtu.be':
        ident = parsed.path.strip('/').split('/')[0]
    elif parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
        if parsed.path == '/watch':
            ident = urllib.parse.parse_qs(parsed.query).get('v', [''])[0]
        elif re.match(r'^/(shorts|embed|live)/', parsed.path):
            ident = parsed.path.split('/')[2]
        else:
            return None
    else:
        return None
    return ident if re.fullmatch(r'[A-Za-z0-9_-]{11}', ident) else None


def allowed_url(url):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname in ('www.youtube.com', 'i.ytimg.com')
            and parsed.port in (None, 443) and not parsed.username and not parsed.password)


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise ValueError('Unsupported storyboard redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, limit=5_000_000):
    if not allowed_url(url):
        raise ValueError('Unsupported storyboard host')
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                                  'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.build_opener(PublicRedirect()).open(request, timeout=5) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Storyboard response exceeds limit')
    return data


@dataclass(frozen=True)
class Storyboard:
    template: str
    width: int
    height: int
    count: int
    columns: int
    rows: int
    interval: int
    duration: int

    def index(self, fraction):
        index = int(fraction * self.duration * 1000 / self.interval) if self.interval else int(fraction*self.count)
        return max(0, min(self.count - 1, index))


@dataclass(frozen=True)
class Filmstrip:
    source: str
    duration: int
    revision: str
    png: bytes
    previews: bytes = b''
    positions: tuple = ()

    def frame_at(self, fraction):
        if not self.positions:
            return min(CELLS-1, int(fraction*CELLS))
        right = min(len(self.positions)-1, bisect_left(self.positions, fraction))
        left = max(0, right-1)
        return left if fraction-self.positions[left] < self.positions[right]-fraction else right


def parse_storyboard(page, source):
    # Parse only a data object; never evaluate scripts from a video page.
    match = re.search(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*', page)
    if not match:
        raise ValueError('No public player data')
    player = json.JSONDecoder().raw_decode(page[match.end():])[0]
    details = player.get('videoDetails', {})
    if details.get('videoId') != source or details.get('isLiveContent'):
        raise ValueError('Storyboard does not match this video')
    duration = int(details.get('lengthSeconds', 0))
    if not 0 < duration <= 86400:
        raise ValueError('Unsupported storyboard duration')
    spec = player.get('storyboards', {}).get('playerStoryboardSpecRenderer', {}).get('spec', '')
    if not isinstance(spec, str) or len(spec) > 32768:
        raise ValueError('Invalid storyboard data')
    template, *levels = spec.split('|')
    if template.startswith('//'):
        template = 'https:' + template
    if not allowed_url(template) or not urllib.parse.urlsplit(template).path.startswith(f'/sb/{source}/'):
        raise ValueError('Unsupported storyboard template')
    choices = []
    for level, fields in enumerate(levels):
        try:
            width, height, count, columns, rows, interval, name, signature = fields.split('#')
            width, height, count, columns, rows, interval = map(int, (width, height, count, columns, rows, interval))
            if (not 1 <= width <= 640 or not 1 <= height <= 360 or not 1 <= count <= 100000
                    or not 1 <= columns <= 20 or not 1 <= rows <= 20 or not 0 <= interval <= 3600000
                    or width*height*columns*rows > 4_194_304):
                continue
            url = template.replace('$L', str(level)).replace('$N', name)
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode({'sigh': signature})
            candidate = Storyboard(url, width, height, count, columns, rows, interval, duration)
            sheets = {candidate.index((i+.5)/CELLS) // (columns*rows) for i in range(CELLS)}
            if len(sheets) <= 8:
                choices.append((abs(height - 45), len(sheets), candidate))
        except (ValueError, TypeError):
            continue
    if not choices:
        raise ValueError('No bounded storyboard format')
    return min(choices, key=lambda item: item[:2])[2]


def load_filmstrip(source, fetch=download, cancelled=lambda: False):
    from PIL import Image, ImageOps
    if not isinstance(source, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', source):
        raise ValueError('Invalid video ID')
    deadline = time.monotonic() + 20
    page = fetch('https://www.youtube.com/watch?v=' + source + '&hl=en').decode('utf-8', 'replace')
    board = parse_storyboard(page, source)
    strip = Image.new('RGB', (WIDTH, HEIGHT), (53, 53, 53))
    sheets = {}
    for cell in range(CELLS):
        if cancelled() or time.monotonic() > deadline:
            raise TimeoutError('Storyboard request superseded or expired')
        index = board.index((cell+.5)/CELLS)
        sheet_index, offset = divmod(index, board.columns*board.rows)
        if sheet_index not in sheets:
            raw = fetch(board.template.replace('$M', str(sheet_index)))
            with Image.open(io.BytesIO(raw)) as image:
                if (image.format not in ('JPEG', 'PNG', 'WEBP') or image.width*image.height > 4_194_304
                        or image.width < board.width or image.height < board.height):
                    raise ValueError('Invalid storyboard image')
                sheets[sheet_index] = image.convert('RGB')
        x, y = offset % board.columns * board.width, offset // board.columns * board.height
        if x + board.width > sheets[sheet_index].width or y + board.height > sheets[sheet_index].height:
            raise ValueError('Storyboard tile is outside the supplied image')
        frame = sheets[sheet_index].crop((x, y, x+board.width, y+board.height))
        left, right = tile_bounds(cell)
        frame = ImageOps.fit(frame, (right-left, HEIGHT), method=Image.Resampling.LANCZOS)
        strip.paste(frame, (left, 0))
    output = io.BytesIO()
    strip.save(output, format='PNG')
    data = output.getvalue()
    # Reuse the sprite sheets already fetched for the twelve visible tiles.
    # The lens gets a denser set of frames without extra network requests or
    # reducing the approved spacing on the rail. Bound its decoded memory.
    last = board.index(1)
    count = min(last+1, MAX_PREVIEWS)
    indices = sorted({round(i*last/max(1, count-1)) for i in range(count)})
    previews, positions = [], []
    for index in indices:
        if cancelled() or time.monotonic() > deadline:
            raise TimeoutError('Storyboard request superseded or expired')
        sheet_index, offset = divmod(index, board.columns*board.rows)
        sheet = sheets.get(sheet_index)
        if sheet is None:
            continue
        x, y = offset % board.columns * board.width, offset // board.columns * board.height
        if x+board.width > sheet.width or y+board.height > sheet.height:
            continue
        frame = sheet.crop((x, y, x+board.width, y+board.height))
        previews.append(ImageOps.fit(frame, (PREVIEW_WIDTH, PREVIEW_HEIGHT), method=Image.Resampling.LANCZOS))
        positions.append(min(1, index*board.interval/(board.duration*1000)) if board.interval else index/board.count)
    atlas = Image.new('RGB', (PREVIEW_COLUMNS*PREVIEW_WIDTH,
                              max(1, (len(previews)+PREVIEW_COLUMNS-1)//PREVIEW_COLUMNS)*PREVIEW_HEIGHT))
    for index, preview in enumerate(previews):
        atlas.paste(preview, (index % PREVIEW_COLUMNS*PREVIEW_WIDTH, index // PREVIEW_COLUMNS*PREVIEW_HEIGHT))
    output = io.BytesIO()
    atlas.save(output, format='PNG')
    preview_data = output.getvalue()
    revision = hashlib.sha256(data+preview_data).hexdigest()[:16]
    return Filmstrip(source, board.duration, revision, data, preview_data, tuple(positions))


class ThumbnailWorker:
    def __init__(self, loader=load_filmstrip):
        self.loader = loader
        self.condition = threading.Condition()
        self.cache, self.failed = {}, {}
        self.wanted = self.pending = self.inflight = None
        self.stopped = False
        self.thread = threading.Thread(target=self.run, name='touchbar-storyboards', daemon=True)
        self.thread.start()

    def read(self, video):
        source = video.get('thumbnail_source') if video['length'] > 0 and video['can_seek'] else None
        with self.condition:
            self.wanted = source
            if not source:
                self.pending = None
                return None
            result = self.cache.get(source)
            if result:
                # Ads and different media sessions must not use a filmstrip
                # with a different duration just because the page URL matches.
                if abs(result.duration*1_000_000 - video['length']) <= max(2_000_000, video['length']*.02):
                    return result
                return None
            if source not in (self.inflight, self.pending) and time.monotonic() - self.failed.get(source, -100) > 60:
                self.pending = source
                self.condition.notify()
        return None

    def close(self):
        with self.condition:
            self.stopped = True
            self.condition.notify()

    def run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.stopped or self.pending is not None)
                if self.stopped:
                    return
                source, self.pending = self.pending, None
                self.inflight = source
            try:
                result = self.loader(source, cancelled=lambda: self.stopped or self.wanted != source)
                with self.condition:
                    self.cache[source] = result
                    while len(self.cache) > 2:
                        del self.cache[next(iter(self.cache))]
            except Exception:
                # A private/unavailable video gets the existing time scrubber.
                # Never log page URLs, IDs, titles, signed image URLs or pixels.
                with self.condition:
                    if self.wanted == source:
                        self.failed[source] = time.monotonic()
                        while len(self.failed) > 8:
                            del self.failed[next(iter(self.failed))]
            finally:
                with self.condition:
                    self.inflight = None
