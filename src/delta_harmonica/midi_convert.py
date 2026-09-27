from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mido

_NATURAL_OFFSETS = [0, 2, 4, 5, 7, 9, 11, 12]  # 1..7, 1'
_LABELS = ["1", "2", "3", "4", "5", "6", "7", "1'"]


@dataclass
class MidiNote:
    midi: int
    start_tick: int
    duration_tick: int


@dataclass
class ConvertResult:
    text: str
    warnings: list[str]


def _collect_notes(mid: mido.MidiFile) -> list[MidiNote]:
    messages = mido.merge_tracks(mid.tracks)
    abs_tick = 0
    active: dict[int, int] = {}
    notes: list[MidiNote] = []
    for msg in messages:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            active[msg.note] = abs_tick
        elif msg.type == "note_off" or (
            msg.type == "note_on" and msg.velocity == 0
        ):
            start = active.pop(msg.note, None)
            if start is None:
                continue
            notes.append(
                MidiNote(
                    midi=msg.note,
                    start_tick=start,
                    duration_tick=max(1, abs_tick - start),
                )
            )
    notes.sort(key=lambda n: (n.start_tick, n.midi))
    return notes


def _ticks_to_ms(ticks: int, tempo: int, ticks_per_beat: int) -> float:
    return (ticks * tempo) / (ticks_per_beat * 1000.0)


def _quantize_dur_token(beats: float, grid: float = 0.25) -> str:
    candidates = {"1": 4.0, "2": 2.0, "4": 1.0, "8": 0.5, "16": 0.25}
    snapped = round(beats / grid) * grid
    if snapped <= 0:
        snapped = grid
    best = min(candidates.items(), key=lambda kv: abs(kv[1] - snapped))
    return best[0]


def _build_candidates(midi_root: int) -> list[tuple[int, str]]:
    """List of (midi_pitch, token).

    Single natural bank at midi_root; octaves via game modifiers:
      s = 半音 (+1), # = 升调 (+octave), b = 降调 (-octave)
    """
    out: list[tuple[int, str]] = []
    base = midi_root
    for label, off in zip(_LABELS, _NATURAL_OFFSETS, strict=True):
        natural = base + off
        out.append((natural, label))
        out.append((natural + 1, f"s{label}"))
        out.append((natural + 12, f"#{label}"))
        out.append((natural - 12, f"b{label}"))
        # ±2 octaves via stacked modifiers
        out.append((natural + 24, f"##{label}"))
        out.append((natural - 24, f"bb{label}"))
    return out


def _token_cost(tok: str) -> int:
    """Prefer natural, then 半音, then octave modifiers."""
    if tok.startswith("s"):
        return 1
    if tok.startswith("#") or tok.startswith("b"):
        return 2
    return 0


def midi_to_token(
    midi_note: int,
    *,
    midi_root: int = 60,
) -> tuple[str, list[str]] | None:
    """Map MIDI note → (pitch_token, warnings) or None if out of range."""
    warnings: list[str] = []
    candidates = _build_candidates(midi_root)
    exact = [tok for pitch, tok in candidates if pitch == midi_note]
    if exact:
        exact.sort(key=_token_cost)
        return exact[0], warnings

    nearest = min(candidates, key=lambda c: abs(c[0] - midi_note))
    if abs(nearest[0] - midi_note) > 1:
        warnings.append(f"skip MIDI {midi_note}: outside harmonica range")
        return None
    warnings.append(f"MIDI {midi_note} approx as {nearest[1]}")
    return nearest[1], warnings


def convert_midi(
    path: Path,
    *,
    bpm: float | None = None,
    midi_root: int = 60,
    title: str | None = None,
    grid: float = 0.25,
) -> ConvertResult:
    mid = mido.MidiFile(str(path))
    notes = _collect_notes(mid)
    warnings: list[str] = []

    tempo = 500000
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                tempo = msg.tempo
                break
        else:
            continue
        break

    file_bpm = mido.tempo2bpm(tempo)
    use_bpm = float(bpm) if bpm is not None else float(file_bpm)
    ms_beat = 60000.0 / use_bpm
    tpb = mid.ticks_per_beat

    tokens_out: list[str] = []
    last_end_ms = 0.0

    for n in notes:
        start_ms = _ticks_to_ms(n.start_tick, tempo, tpb)
        dur_ms = _ticks_to_ms(n.duration_tick, tempo, tpb)

        gap = start_ms - last_end_ms
        if gap > ms_beat * 0.2:
            gap_beats = gap / ms_beat
            dur_tok = _quantize_dur_token(gap_beats, grid=grid)
            tokens_out.append(f"0/{dur_tok}")

        mapped = midi_to_token(n.midi, midi_root=midi_root)
        if mapped is None:
            warnings.append(f"skip MIDI {n.midi} at {start_ms:.0f}ms")
            last_end_ms = max(last_end_ms, start_ms + dur_ms)
            continue
        pitch_tok, w = mapped
        warnings.extend(w)

        beats = dur_ms / ms_beat
        dur_tok = _quantize_dur_token(beats, grid=grid)
        tokens_out.append(f"{pitch_tok}/{dur_tok}")
        last_end_ms = start_ms + dur_ms

    body_lines: list[str] = []
    line: list[str] = []
    for tok in tokens_out:
        line.append(tok)
        if len(line) >= 8:
            body_lines.append(" ".join(line))
            line = []
    if line:
        body_lines.append(" ".join(line))

    song_title = title or path.stem

    header = [
        "# 三角洲口琴简谱 v1 (from MIDI — please review)",
        f"title: {song_title}",
        f"bpm: {use_bpm:.2f}",
        f"# midi_root: {midi_root}  source: {path.name}",
        "",
    ]
    text = "\n".join(header + body_lines) + "\n"
    return ConvertResult(text=text, warnings=warnings)
