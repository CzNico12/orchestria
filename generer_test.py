import numpy as np
import subprocess
import os

SR = 44100
DUR = 30
N = SR * DUR
t = np.arange(N) / SR
rng = np.random.default_rng(42)

mix = np.zeros((N, 2))


def add(x, where_l, where_r):
    mix[:, 0] += x * where_l
    mix[:, 1] += x * where_r


def piano_note(freq, start, dur, vel=0.5):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    env = np.exp(-tt * 2.2) * np.minimum(1, tt * 40)
    partials = sum(
        vel / (i + 1) ** 1.4 * np.sin(2 * np.pi * freq * (i + 1) * tt)
        for i in range(5)
    )
    return env * partials


melody = [
    (261.63, 0.0), (329.63, 0.4), (392.00, 0.8), (523.25, 1.2),
    (392.00, 1.6), (329.63, 2.0), (261.63, 2.4), (392.00, 2.8),
    (329.63, 3.2), (523.25, 3.6), (659.25, 4.0), (523.25, 4.4),
    (392.00, 4.8), (329.63, 5.2), (261.63, 5.6), (329.63, 6.0),
    (261.63, 6.4), (392.00, 7.0), (329.63, 7.6), (523.25, 8.2),
    (659.25, 8.8), (783.99, 9.4), (659.25, 10.0), (523.25, 10.6),
]

chord_prog = [
    [261.63, 329.63, 392.00, 523.25],
    [220.00, 261.63, 329.63, 440.00],
    [174.61, 220.00, 261.63, 349.23],
    [196.00, 246.94, 293.66, 392.00],
]

piano_buf = np.zeros(N)
for f, s in melody:
    val = piano_note(f, s, 1.1)
    i0 = int(s * SR)
    i1 = min(N, i0 + len(val))
    piano_buf[i0:i1] += val[: i1 - i0]

for bar in range(8):
    for f in chord_prog[bar % 4]:
        val = piano_note(f, bar * 3.75, 3.3, 0.32)
        i0 = int(bar * 3.75 * SR)
        i1 = min(N, i0 + len(val))
        piano_buf[i0:i1] += val[: i1 - i0]

add(piano_buf, 0.9, 0.85)


def note_name(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


bass_line = [36, 36, 43, 36, 41, 36, 43, 48]
bass_buf = np.zeros(N)
for beat in range(34):
    midi = bass_line[beat % len(bass_line)]
    f = note_name(midi)
    start = beat * 0.875
    dur = 0.82
    n = int(dur * SR)
    tt = np.arange(n) / SR
    if beat % 2 == 0:
        glide = f * (1.0 - 0.25 * np.minimum(1, tt * 6))
        env = np.exp(-tt * 0.7)
        wave = np.sin(2 * np.pi * glide * tt) + 0.3 * np.sin(2 * np.pi * glide * 2 * tt)
    else:
        env = np.exp(-tt * 2.5)
        wave = np.sin(2 * np.pi * f * tt)
    val = env * wave
    i0 = int(start * SR)
    i1 = min(N, i0 + n)
    bass_buf[i0:i1] += val[: i1 - i0]

add(bass_buf, 0.8, 0.78)


def kick(start):
    n = int(0.32 * SR)
    tt = np.arange(n) / SR
    f = 110 * np.exp(-tt * 14) + 45
    phase = 2 * np.pi * np.cumsum(f) / SR
    env = np.exp(-tt * 9)
    return env * np.sin(phase)


def hat(start, open_=False):
    n = int((0.18 if open_ else 0.07) * SR)
    noise = rng.normal(0, 1, n)
    tt = np.arange(n) / SR
    env = np.exp(-tt * (18 if open_ else 90))
    padded = np.concatenate([noise, [0, 0]])
    hp = np.diff(np.convolve(padded, [1, -2, 1], mode="same"))[:n]
    return env * hp / 3


def snare(start):
    n = int(0.16 * SR)
    tt = np.arange(n) / SR
    noise = rng.normal(0, 1, n) * np.exp(-tt * 25)
    tone = np.sin(2 * np.pi * 190 * tt) * np.exp(-tt * 30)
    return (noise + 0.5 * tone) / 2


drum_buf = np.zeros(N)
for beat in range(32):
    sec = beat * 0.875
    i = int(sec * SR)
    if beat % 4 == 0:
        v = kick(sec)
        drum_buf[i : i + len(v)] += v
    if beat % 4 == 2:
        v = snare(sec)
        drum_buf[i : i + len(v)] += v
    v = hat(sec, beat % 2 == 1)
    drum_buf[i : i + len(v)] += v * 0.45
    v = hat(sec + 0.4375, False)
    drum_buf[i + int(0.4375 * SR) : i + int(0.4375 * SR) + len(v)] += v * 0.3

add(drum_buf, 0.65, 0.62)

peak = np.max(np.abs(mix))
mix = mix / peak * 0.92

os.makedirs("data/test", exist_ok=True)
mix = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
subprocess.run(
    ["tools/ffmpeg", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
     "-codec:a", "libmp3lame", "-b:a", "192k", "data/test/morceau-test.mp3"],
    input=mix.tobytes(),
    check=True,
)
print("MP3 de test généré :", os.path.getsize("data/test/morceau-test.mp3"), "octets")