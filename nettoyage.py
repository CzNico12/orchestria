import pretty_midi

DRUM_MAP = {
    36: 36, 38: 38, 40: 38, 37: 38, 39: 38,
    42: 42, 44: 42, 46: 46, 41: 41, 43: 43,
    45: 45, 47: 47, 48: 48, 49: 49, 50: 50, 51: 51,
}


def band_map(pitch):
    if pitch < 40:
        return 36
    if pitch < 50:
        return 38
    if pitch < 60:
        return 45
    if pitch < 70:
        return 48
    return 46


def nettoyer(path, kind):
    pm = pretty_midi.PrettyMIDI(path)
    inst = pm.instruments[0]
    notes = sorted(inst.notes, key=lambda n: (n.pitch, n.start))

    merged = []
    for n in notes:
        if merged and merged[-1].pitch == n.pitch and n.start <= merged[-1].end + 0.02:
            prev = merged[-1]
            prev.end = max(prev.end, n.end)
            prev.velocity = max(prev.velocity, n.velocity)
        else:
            merged.append(n)

    minlen = 0.03 if kind == "drums" else 0.06
    merged = [n for n in merged if n.end - n.start >= minlen]

    if kind == "drums":
        for n in merged:
            n.pitch = DRUM_MAP.get(n.pitch, band_map(n.pitch))
        inst.is_drum = True

    inst.notes = merged
    pm.write(path)