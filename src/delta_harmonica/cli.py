from __future__ import annotations

import json
import shutil
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Optional

import typer

from delta_harmonica import __version__
from delta_harmonica.adb_util import (
    AdbError,
    get_display_size,
    get_wm_size,
    list_devices,
    pick_serial,
    ready_devices,
    which_adb,
    which_scrcpy,
)
from delta_harmonica.calibrate import CalibrateError, run_calibrate, run_calibrate_test
from delta_harmonica.midi_convert import convert_midi
from delta_harmonica.paths import (
    profiles_dir,
    project_root,
    resolve_profile_path,
    resolve_score_path,
    scores_dir,
)
from delta_harmonica.player import Player, format_timeline
from delta_harmonica.preview_server import make_handler
from delta_harmonica.profile_io import load_profile
from delta_harmonica.score_parser import ScoreParseError, parse_score_file
from delta_harmonica.touch import TouchController
from delta_harmonica.window import WindowError, find_scrcpy_window_id, get_window_rect, parse_geometry_string

app = typer.Typer(
    name="dharm",
    help="三角洲口琴练习辅助（乐谱解析 / 标定 / 练习）",
    no_args_is_help=True,
    add_completion=True,
)


def _die(msg: str, code: int = 1) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def _complete_scores(incomplete: str) -> list[str]:
    d = scores_dir()
    if not d.is_dir():
        return []
    names: list[str] = []
    for f in sorted(d.glob("*.txt")):
        for cand in (f.stem, f.name, str(f)):
            if cand.startswith(incomplete) and cand not in names:
                names.append(cand)
    return names


def _complete_profiles(incomplete: str) -> list[str]:
    d = profiles_dir()
    if not d.is_dir():
        return []
    names: list[str] = []
    for f in sorted(d.glob("*.json")):
        for cand in (f.stem, f.name):
            if cand.startswith(incomplete) and cand not in names:
                names.append(cand)
    return names


def _complete_serials(incomplete: str) -> list[str]:
    try:
        return [
            d.serial
            for d in list_devices()
            if d.state == "device" and d.serial.startswith(incomplete)
        ]
    except Exception:  # noqa: BLE001
        return []


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version and exit."
    ),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command("doctor")
def doctor_cmd(
    serial: Optional[str] = typer.Option(
        None,
        "--serial",
        "-s",
        help="adb serial",
        autocompletion=_complete_serials,
    ),
) -> None:
    """Check adb, scrcpy, and connected device."""
    ok = True

    adb = which_adb()
    if adb:
        typer.echo(f"adb: {adb}")
    else:
        typer.secho("adb: NOT FOUND", fg=typer.colors.RED)
        ok = False

    sc = which_scrcpy()
    if sc:
        typer.echo(f"scrcpy: {sc}")
    else:
        typer.secho("scrcpy: NOT FOUND (needed for screen mirror / calibrate)", fg=typer.colors.YELLOW)

    if shutil.which("xdotool"):
        typer.echo(f"xdotool: {shutil.which('xdotool')}")
        try:
            wid = find_scrcpy_window_id()
            rect = get_window_rect(wid)
            typer.echo(
                f"scrcpy window: id={wid} "
                f"{rect.width}x{rect.height}+{rect.x}+{rect.y}"
            )
        except WindowError as exc:
            typer.secho(f"scrcpy window: {exc}", fg=typer.colors.YELLOW)
    else:
        typer.secho("xdotool: NOT FOUND (calibrate window auto-detect disabled)", fg=typer.colors.YELLOW)

    if adb:
        devices = list_devices()
        if not devices:
            typer.secho("devices: none", fg=typer.colors.RED)
            ok = False
        else:
            for d in devices:
                color = typer.colors.GREEN if d.state == "device" else typer.colors.YELLOW
                typer.secho(f"device: {d.serial}\t{d.state}", fg=color)
        try:
            ser = pick_serial(serial) if ready_devices() else None
            if ser:
                pw, ph = get_wm_size(ser)
                dw, dh = get_display_size(ser)
                typer.echo(f"wm size (physical/override): {pw}x{ph}")
                typer.echo(f"display size (touch coords): {dw}x{dh}")
                if (pw, ph) != (dw, dh):
                    typer.secho(
                        "note: display rotated vs wm size — calibrate uses display size",
                        fg=typer.colors.YELLOW,
                    )
                touch = TouchController(serial=ser, dry_run=False)
                typer.echo(f"touch backend: {touch.backend.value}")
        except AdbError as exc:
            typer.secho(f"adb error: {exc}", fg=typer.colors.RED)
            ok = False

    typer.echo(f"scores dir: {scores_dir()}")
    typer.echo(f"profiles dir: {profiles_dir()}")
    if ok:
        typer.secho("doctor: OK", fg=typer.colors.GREEN)
    else:
        typer.secho("doctor: issues found", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command("calibrate")
def calibrate_cmd(
    profile: str = typer.Option(
        ...,
        "--profile",
        "-p",
        help="Profile name to write/load",
        autocompletion=_complete_profiles,
    ),
    test: bool = typer.Option(False, "--test", help="Tap each calibrated key to verify"),
    serial: Optional[str] = typer.Option(
        None, "--serial", "-s", autocompletion=_complete_serials
    ),
    window_id: Optional[str] = typer.Option(None, "--window-id", help="scrcpy X window id"),
    geometry: Optional[str] = typer.Option(
        None,
        "--geometry",
        help="Manual window geometry: WIDTHxHEIGHT+X+Y or X,Y,W,H",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="With --test: print only"),
) -> None:
    """Calibrate UI key positions via clicks on the scrcpy window."""
    if test:
        try:
            path = resolve_profile_path(profile)
            prof = load_profile(path)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            _die(str(exc))
        try:
            run_calibrate_test(prof, serial=serial, dry_run=dry_run)
        except (AdbError, CalibrateError) as exc:
            _die(str(exc))
        return

    rect = None
    if geometry:
        try:
            rect = parse_geometry_string(geometry)
        except WindowError as exc:
            _die(str(exc))
    try:
        path = run_calibrate(
            profile,
            serial=serial,
            window_id=window_id,
            window_rect=rect,
        )
    except (AdbError, CalibrateError, WindowError) as exc:
        _die(str(exc))
    typer.secho(f"profile saved: {path}", fg=typer.colors.GREEN)


@app.command("list")
def list_cmd() -> None:
    """List scores in the default scores/ folder."""
    d = scores_dir()
    if not d.is_dir():
        typer.echo(f"(no scores dir at {d})")
        return
    files = sorted(d.glob("*.txt"))
    if not files:
        typer.echo("(no .txt scores)")
        return
    for f in files:
        typer.echo(f.name)


@app.command("play")
def play_cmd(
    score: str = typer.Argument(
        ..., help="Score name or path", autocompletion=_complete_scores
    ),
    profile: str = typer.Option(
        ...,
        "--profile",
        "-p",
        help="Calibration profile name",
        autocompletion=_complete_profiles,
    ),
    serial: Optional[str] = typer.Option(
        None, "--serial", "-s", autocompletion=_complete_serials
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print timeline / no touch"),
    countdown: int = typer.Option(3, "--countdown", "-c", help="Seconds before start"),
    hold_extra: int = typer.Option(
        0,
        "--hold-extra",
        "-H",
        help="Extra ms added to every note press (game needs a moment to sound)",
        min=0,
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Practice-assist play: follow a score using a calibrated profile."""
    try:
        score_path = resolve_score_path(score)
        parsed = parse_score_file(score_path)
    except (FileNotFoundError, ScoreParseError) as exc:
        _die(str(exc))

    try:
        prof_path = resolve_profile_path(profile)
        prof = load_profile(prof_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        _die(str(exc))

    if dry_run:
        typer.echo(format_timeline(parsed))
        if hold_extra:
            typer.echo(f"# hold_extra={hold_extra}ms (applied on real play)")
        return

    try:
        ser = pick_serial(serial)
        dw, dh = get_display_size(ser)
    except AdbError as exc:
        _die(str(exc))

    if (dw, dh) != (prof.device_width, prof.device_height):
        typer.secho(
            f"display now {dw}x{dh}, profile was {prof.device_width}x{prof.device_height} "
            "— scaling key positions proportionally",
            fg=typer.colors.YELLOW,
        )

    if not yes:
        extra = f"\nhold_extra: {hold_extra}ms" if hold_extra else ""
        typer.echo(
            f"Score: {parsed.title} ({score_path.name})\n"
            f"Profile: {prof.name} "
            f"(calibrated {prof.device_width}x{prof.device_height}, "
            f"play {dw}x{dh}){extra}\n"
            "Make sure the harmonica UI is open (自然音). 八度用升调/降调。"
        )
        if not typer.confirm("Continue?"):
            raise typer.Exit(0)

    try:
        touch = TouchController(serial=ser, dry_run=False)
        player = Player(
            prof,
            touch,
            display_width=dw,
            display_height=dh,
            hold_extra_ms=hold_extra,
        )
        player.play(parsed, countdown=countdown, verbose=True)
    except AdbError as exc:
        _die(str(exc))


@app.command("midi2txt")
def midi2txt_cmd(
    midi: Path = typer.Argument(..., exists=True, readable=True, help="Input .mid file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output .txt path"),
    bpm: Optional[float] = typer.Option(None, "--bpm", help="Override BPM"),
    midi_root: int = typer.Option(
        60, "--midi-root", help="MIDI note for register1 degree 1 (default C4=60)"
    ),
    title: Optional[str] = typer.Option(None, "--title"),
) -> None:
    """Convert MIDI to a draft numbered score (.txt)."""
    try:
        result = convert_midi(
            midi, bpm=bpm, midi_root=midi_root, title=title
        )
    except Exception as exc:  # noqa: BLE001
        _die(f"midi convert failed: {exc}")

    out = output
    if out is None:
        scores_dir().mkdir(parents=True, exist_ok=True)
        out = scores_dir() / f"{midi.stem}.txt"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.text, encoding="utf-8")
    typer.echo(f"wrote {out}")
    for w in result.warnings:
        typer.secho(f"warning: {w}", fg=typer.colors.YELLOW)


@app.command("preview")
def preview_cmd(
    port: int = typer.Option(8765, "--port", "-P", help="Local HTTP port"),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open browser"),
) -> None:
    """Open PC HTML score preview (listen with Web Audio, no phone needed)."""
    root = project_root()
    index = root / "preview" / "index.html"
    if not index.is_file():
        _die(f"preview page missing: {index}")

    handler = make_handler(root)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        _die(f"cannot bind 127.0.0.1:{port}: {exc}")

    url = f"http://127.0.0.1:{port}/preview/index.html"
    typer.echo(f"preview: {url}")
    typer.echo("wheel = tempo · save BPM writes scores/*.txt")
    typer.echo("Ctrl+C to stop")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if not no_open:
        # tiny delay so the server accepts the first request
        time.sleep(0.15)
        webbrowser.open(url)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        typer.echo("\nstopping preview server")
    finally:
        server.shutdown()


def run() -> None:
    app()


# Allow `python -m delta_harmonica` and entry point `dharm = ...:app`
# Typer's Typer instance is a click MultiCommand and works as entry point.
if __name__ == "__main__":
    app()
