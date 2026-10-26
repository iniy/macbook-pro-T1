# SPDX-License-Identifier: MIT
"""On-demand output spectrum: native DSP, no microphone or saved audio."""
import math
import re
import subprocess
import threading
import time

BANDS = 64
EDGES = (0, 1, 2, 3, 4, 5, 6, 8, 10, 13, 17, 22, 28, 35, 44, 54, 64)
SILENT = (0,) * 16


def magnitudes(structure):
    # python3-gst supplies GstValueList overrides, but is optional on desktops
    # with PyGObject alone. Gst's own serialization works on both installations.
    if structure.get_name() != 'spectrum':
        return None
    match = re.search(r'magnitude=\(float\)\{([^}]*)\}', structure.to_string())
    if not match:
        return None
    try:
        values = tuple(float(v) for v in match[1].split(','))
    except ValueError:
        return None
    return values if len(values) == BANDS and all(math.isfinite(v) for v in values) else None


class Envelope:
    def __init__(self):
        self.levels = [0.] * 16

    def update(self, values):
        # Group the native linear FFT bins into progressively wider bands.
        # Fast attack, gentle release; quantization avoids subpixel redraws.
        for i, (left, right) in enumerate(zip(EDGES, EDGES[1:])):
            target = max(0., min(1., (max(values[left:right])+60)/48))
            previous = self.levels[i]
            self.levels[i] += (target-previous) * (.72 if target > previous else .24)
        return tuple(round(v*40) for v in self.levels)


def default_monitor():
    result = subprocess.run(['/usr/bin/pactl', 'get-default-sink'],
                            capture_output=True, text=True, timeout=.5, check=True)
    sink = result.stdout.strip()
    if not sink or len(sink) > 512 or any(c.isspace() for c in sink):
        raise ValueError('Output unavailable')
    return sink + '.monitor'


class NativeSpectrum:
    def __init__(self, monitor):
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)
        self.Gst = Gst
        self.pipeline = Gst.parse_launch(
            'pulsesrc name=output client-name="Touch Bar spectrum" '
            'buffer-time=120000 latency-time=40000 ! '
            'audio/x-raw,format=F32LE,rate=16000,channels=1 ! '
            'spectrum bands=64 interval=40000000 threshold=-60 '
            'message-phase=false ! fakesink sync=false enable-last-sample=false')
        try:
            source = self.pipeline.get_by_name('output')
            # An explicit sink monitor is mandatory. Never fall back to the
            # default recording source (which may be a microphone).
            source.set_property('device', monitor)
            source.set_property('stream-properties', Gst.Structure.new_from_string(
                'props, stream.capture.sink=(boolean)true, stream.monitor=(boolean)true, '
                'node.dont-fallback=(boolean)true'))
            self.bus = self.pipeline.get_bus()
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError('Output monitor unavailable')
        except Exception:
            self.close()
            raise

    def sample(self):
        Gst = self.Gst
        message = self.bus.timed_pop_filtered(80*Gst.MSECOND,
            Gst.MessageType.ELEMENT | Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if message is None:
            return None
        if message.type != Gst.MessageType.ELEMENT:
            raise RuntimeError('Output monitor ended')
        return magnitudes(message.get_structure())

    def close(self):
        self.pipeline.set_state(self.Gst.State.NULL)


class SpectrumWorker:
    def __init__(self, factory=NativeSpectrum, monitor=default_monitor):
        self.factory, self.monitor = factory, monitor
        self.condition = threading.Condition()
        self.context = None
        self.generation = self.route = 0
        self.levels, self.sampled_at = SILENT, 0
        self.stopped = False
        self.thread = None

    def read(self, context):
        with self.condition:
            if context != self.context:
                self.context = context
                self.generation += 1
                self.levels = SILENT
                self.condition.notify_all()
            if context and not self.stopped and self.thread is None:
                self.thread = threading.Thread(target=self.run, daemon=True,
                                               name='touchbar-spectrum')
                self.thread.start()
            # Stalled/disconnected audio must not freeze the last loud frame.
            return self.levels if context and time.monotonic()-self.sampled_at < .25 else SILENT

    def output_changed(self):
        # Reuse the existing mixer's event subscription, with no extra polling.
        with self.condition:
            self.route += 1
            self.condition.notify_all()

    def close(self):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()
        if self.thread:
            self.thread.join(timeout=2)

    def run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.stopped or self.context is not None)
                if self.stopped:
                    return
                generation, route = self.generation, self.route
            stream = None
            failed = False
            try:
                monitor = self.monitor()
                with self.condition:
                    if self.stopped or generation != self.generation:
                        continue
                stream = self.factory(monitor)
                envelope = Envelope()
                while True:
                    with self.condition:
                        if self.stopped or generation != self.generation:
                            break
                        next_route = self.route
                    if route != next_route:
                        route = next_route
                        if self.monitor() != monitor:
                            break  # Restart on the new output, including headphones.
                    values = stream.sample()
                    if values is not None:
                        levels = envelope.update(values)
                        with self.condition:
                            if generation == self.generation:
                                self.levels, self.sampled_at = levels, time.monotonic()
            except Exception:
                # Missing optional plugins/audio service must never affect
                # playback controls. Retry only with a bounded backoff.
                failed = True
            finally:
                if stream:
                    stream.close()
                with self.condition:
                    self.levels = SILENT
                    if failed:
                        self.condition.wait_for(lambda: self.stopped or generation != self.generation
                                                or route != self.route, timeout=10)
