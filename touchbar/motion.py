# SPDX-License-Identifier: MIT
"""Presentation-only animation; release targets remain the raw touch position."""
import math

from media import position_at


class TimelineMotion:
    def __init__(self):
        self.context = self.position = self.updated = None
        self.dragging = False
        self.pending = None

    def released(self, fraction, video, now):
        # Keep the preview under the finger until the asynchronous browser seek
        # arrives. Do not flash the old playback position between release/ack.
        self.pending = (fraction * video['length'], now)

    def update(self, context, video, fraction, now):
        target = position_at(video, now)
        playing = video['status'] == 'Playing'
        speed = video['rate'] * 1_000_000 if playing else 0
        if self.context != context:
            self.context, self.position, self.updated = context, target, now
            self.dragging, self.pending = False, None
        dt = max(0, now - self.updated)
        if fraction is not None:
            target = fraction * video['length']
            self.pending = None
            if not self.dragging:
                self.position = target
        elif self.pending:
            requested, started = self.pending
            expected = requested + (now-started) * speed
            if (video['sampled_at'] > started and abs(target-expected) < 400_000) or now-started > 1:
                self.pending = None
            else:
                target = expected
        ease = 1 - math.exp(-dt / .035)
        if fraction is not None or self.dragging:
            self.position += (target-self.position) * ease
        else:
            predicted = self.position + dt * speed
            error = target - predicted
            if playing and abs(error) < 1_000_000:
                # Coarsely sampled MPRIS clocks must not make the marker step
                # backwards every poll. Gently correct its running clock.
                correction = max(-speed*dt*.5, min(speed*dt*.5, error*dt/.75))
                self.position = predicted + correction
            else:
                self.position = predicted + error * ease
        self.position = max(0, min(self.position, video['length'])) if video['length'] else max(0, self.position)
        if abs(self.position-target) < 100:
            self.position = target
        self.updated, self.dragging = now, fraction is not None
        return int(self.position)


class FrameBlend:
    def __init__(self):
        self.key = self.target = None
        self.weights, self.started = {}, 0

    def update(self, key, target, now):
        if key != self.key:
            self.key, self.target, self.weights = key, target, {target: 1.0}
            self.started = now - .1
        amount = max(0, min(1, (now-self.started) / .1))
        amount = amount * amount * (3 - 2*amount)
        current = {index: weight*(1-amount) for index, weight in self.weights.items()}
        current[self.target] = current.get(self.target, 0) + amount
        # A fast drag can pass several storyboard frames during one dissolve.
        # Start each transition from the current mixture, avoiding hard cuts.
        if target != self.target:
            current = dict(sorted(current.items(), key=lambda item: item[1], reverse=True)[:4])
            current = {index: weight for index, weight in current.items() if weight > .0001}
            total = sum(current.values())
            current = {index: weight/total for index, weight in current.items()}
            self.weights, self.target, self.started = current, target, now
        return tuple((index, round(weight, 4)) for index, weight in current.items() if weight > .0001)
