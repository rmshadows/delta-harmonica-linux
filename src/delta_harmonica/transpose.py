"""Pitch-range checks and transpose for the in-game harmonica UI.

Playable banks (relative to natural ``1`` = 0 semitones):

- natural ``1..7 1'`` → 0,2,4,5,7,9,11,12
- sharp (+12) / flat (−12); ``##1`` = sharp+``1'`` → 24
- semitone on natural-row buttons → those values +1
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from delta_harmonica.models import (
    Modifier,
    PitchKey,
    PlayNote,
    Score,
    ScoreEvent,
    SetModifier,
)

# Scale-degree → semitones above natural 1 (major).
_DEGREE_ST: dict[PitchKey, int] = {
    PitchKey.N1: 0,
    PitchKey.N2: 2,
    PitchKey.N3: 4,
    PitchKey.N4: 5,
    PitchKey.N5: 7,
    PitchKey.N6: 9,
    PitchKey.N7: 11,
    PitchKey.N1P: 12,
}

_ST_TO_PITCH: dict[int, PitchKey] = {v: k for k, v in _DEGREE_ST.items()}

KEY_NAMES: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

# Natural keys only (左右键循环): C D E F G A B
DIATONIC_SEMITONES: tuple[int, ...] = (0, 2, 4, 5, 7, 9, 11)
DIATONIC_NAMES: tuple[str, ...] = ("C", "D", "E", "F", "G", "A", "B")


def nudge_diatonic_key(transpose: int, delta: int) -> int:
    """Move along C–D–E–F–G–A–B, wrapping octaves."""
    o, k = divmod(int(transpose), 12)
    if k in DIATONIC_SEMITONES:
        i = DIATONIC_SEMITONES.index(k)
    else:
        i = min(
            range(len(DIATONIC_SEMITONES)),
            key=lambda j: abs(DIATONIC_SEMITONES[j] - k),
        )
    total = o * 7 + i + int(delta)
    o2, i2 = divmod(total, 7)
    return o2 * 12 + DIATONIC_SEMITONES[i2]


def diatonic_key_label(transpose: int) -> str:
    """e.g. ``D`` / ``↑1八度 D`` / ``↓1八度 G``."""
    o, k = divmod(int(transpose), 12)
    if k in DIATONIC_SEMITONES:
        name = DIATONIC_NAMES[DIATONIC_SEMITONES.index(k)]
    else:
        name = KEY_NAMES[k]
    if o == 0:
        return name
    return f"{'↑' if o > 0 else '↓'}{abs(o)}八度 {name}"



def note_semitones(note: PlayNote) -> int:
    """Absolute semitone offset relative to natural ``1``."""
    base = _DEGREE_ST[note.pitch]
    if note.modifier == Modifier.SEMITONE:
        return base + 1 + 12 * note.octaves
    return base + 12 * note.octaves


def _playable_semitones() -> frozenset[int]:
    natural = [0, 2, 4, 5, 7, 9, 11, 12]
    out: set[int] = set()
    for o in (-2, -1, 0, 1, 2):
        for st in natural:
            out.add(st + 12 * o)
    for st in natural:
        out.add(st + 1)  # 半音 bank on natural row
    return frozenset(out)


PLAYABLE: frozenset[int] = _playable_semitones()


@dataclass(frozen=True)
class RangeReport:
    semitones: tuple[int, ...]
    out_of_range: tuple[int, ...]
    lo: int
    hi: int

    @property
    def ok(self) -> bool:
        return not self.out_of_range


def analyze_range(score: Score) -> RangeReport:
    sts = tuple(
        note_semitones(ev) for ev in score.events if isinstance(ev, PlayNote)
    )
    if not sts:
        return RangeReport((), (), 0, 0)
    bad = tuple(st for st in sts if st not in PLAYABLE)
    return RangeReport(sts, bad, min(sts), max(sts))


def _token_for_semitone(st: int) -> tuple[Modifier, PitchKey, int] | None:
    """Map semitone → (modifier, pitch, octaves) for score / player."""
    # Exact diatonic banks first (natural / ±octave / ±2 octave).
    for octaves in (0, 1, -1, 2, -2):
        rel = st - 12 * octaves
        pitch = _ST_TO_PITCH.get(rel)
        if pitch is None:
            continue
        # Prefer physical 1' over #1 for +12
        if octaves == 1 and pitch == PitchKey.N1:
            return Modifier.NATURAL, PitchKey.N1P, 0
        if octaves == 0 and pitch == PitchKey.N1P:
            return Modifier.NATURAL, PitchKey.N1P, 0
        if octaves == 2 and pitch == PitchKey.N1:
            # ##1 → player: sharp + 1'
            return Modifier.SHARP, PitchKey.N1, 2
        if octaves == -2 and pitch == PitchKey.N1P:
            return Modifier.FLAT, PitchKey.N1P, -2
        if octaves > 0:
            return Modifier.SHARP, pitch, octaves
        if octaves < 0:
            return Modifier.FLAT, pitch, octaves
        return Modifier.NATURAL, pitch, 0

    # Semitone on natural row (s1..s7, s1')
    rel = st - 1
    pitch = _ST_TO_PITCH.get(rel)
    if pitch is not None:
        return Modifier.SEMITONE, pitch, 0
    return None


def transpose_note(note: PlayNote, semitones: int) -> PlayNote | None:
    if semitones == 0:
        return note
    mapped = _token_for_semitone(note_semitones(note) + semitones)
    if mapped is None:
        return None
    mod, pitch, octaves = mapped
    return PlayNote(
        pitch=pitch,
        duration_ms=note.duration_ms,
        modifier=mod,
        octaves=octaves,
    )


def transpose_score(score: Score, semitones: int) -> Score | None:
    """Shift every note by ``semitones``; None if any note cannot be mapped."""
    if semitones == 0:
        return score
    events: list[ScoreEvent] = []
    for ev in score.events:
        if isinstance(ev, PlayNote):
            n = transpose_note(ev, semitones)
            if n is None:
                return None
            events.append(SetModifier(n.modifier))
            events.append(n)
        elif isinstance(ev, SetModifier):
            continue
        else:
            events.append(ev)
    return replace(score, events=events)


def fits(score: Score, semitones: int = 0) -> bool:
    s = score if semitones == 0 else transpose_score(score, semitones)
    if s is None:
        return False
    return analyze_range(s).ok


@dataclass(frozen=True)
class TransposePlan:
    semitones: int
    label: str


def plan_label(semitones: int) -> str:
    if semitones == 0:
        return "原调"
    o, k = divmod(semitones, 12)
    # normalize remainder to -6..5 for readability
    if k > 6:
        o += 1
        k -= 12
    elif k < -6:
        o -= 1
        k += 12
    parts: list[str] = []
    if o:
        parts.append(f"{'升' if o > 0 else '降'}{abs(o)}八度")
    if k:
        name = KEY_NAMES[k % 12]
        parts.append(f"C→{name} ({k:+d})")
    return " ".join(parts) if parts else "原调"


def suggest_transpose(score: Score) -> TransposePlan:
    """Choose a shift that fits the UI range; prefer smaller |semitones|."""
    if fits(score, 0):
        return TransposePlan(0, plan_label(0))

    candidates: list[int] = []
    for oct_shift in (0, -1, 1, -2, 2):
        for key in range(12):
            candidates.append(oct_shift * 12 + key)
            if key:
                candidates.append(oct_shift * 12 - key)
    seen: set[int] = set()
    ordered: list[int] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    ordered.sort(key=lambda s: (abs(s), s))

    for shift in ordered:
        if fits(score, shift):
            return TransposePlan(shift, plan_label(shift))

    best_shift = 0
    best_ok = -1
    for shift in ordered[:80]:
        s = transpose_score(score, shift)
        if s is None:
            continue
        rep = analyze_range(s)
        ok_n = len(rep.semitones) - len(rep.out_of_range)
        if ok_n > best_ok:
            best_ok = ok_n
            best_shift = shift
    return TransposePlan(best_shift, plan_label(best_shift) + "（仍有超音域音）")
