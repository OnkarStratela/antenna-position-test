"""Antenna-position test logger.

Drives the existing `rfid_reader` C binary one throw at a time and records
every throw to a single master Excel workbook (`results.xlsx`) with two
sheets:

- ``Throws``    : one row per throw — setup, throw number, timing, number of
  unique tags, EPC list, antennas hit, plus an embedded thumbnail of the
  antenna-position photo for that setup.
- ``TagReads``  : one row per detected tag — setup, throw, EPC, antenna, ts.

The C reader dedupes EPCs for its entire process lifetime, so this script
spawns a *fresh* `rfid_reader` subprocess for every throw and kills it when
the operator ends the throw. That way the same container can be thrown again
in a later throw and will still be reported.

Operator workflow (no SSH-and-restart between throws)::

    $ python3 antenna_test_logger.py

    Available antenna setups:
      1. antennas_opposite
      2. antennas_vertical
      3. antennas_horizontal
    Select starting setup [1/2/3]: 1

    [Setup: antennas_opposite]  ENTER = start throw  |  's' = switch setup  |  'q' = quit
    > <ENTER>
    [antennas_opposite | Throw #1] scanning... press ENTER to end this throw
        [RFID] TAG DETECTED: ABCDEF1234 [Source_0] [2026-05-26 16:10:00]
    > <ENTER>
    [antennas_opposite | Throw #1] DONE — 1 unique tag(s), 3.2 s
        logged to results.xlsx

This script intentionally does NOT drive the WS2812 LED strip; for LED
feedback during scanning, use the existing `rfid_led.py` instead. They are
mutually exclusive at runtime because both want to own the rfid_reader
subprocess.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

SCRIPT_DIR    = Path(__file__).resolve().parent
RFID_BINARY   = SCRIPT_DIR / "rfid_reader"
IMAGES_DIR    = SCRIPT_DIR / "images"
RESULTS_XLSX  = SCRIPT_DIR / "results.xlsx"
THUMB_DIR     = SCRIPT_DIR / ".thumbs"

SETUPS: List[str] = [
    "antennas_opposite",
    "antennas_vertical",
    "antennas_horizontal",
]

# rfid_reader.c emits each new EPC on a line like:
#   \x1b[0;32m[RFID] TAG DETECTED: ABCDEF12 \x1b[0m [Source_0] [2026-05-26 16:00:00]
# The ANSI colour codes are stripped before matching.
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TAG_LINE_RE = re.compile(
    r"\[RFID\] TAG DETECTED:\s*(?P<epc>[0-9A-Fa-f]+)\s*"
    r"\[(?P<antenna>[^\]]+)\]\s*\[(?P<ts>[^\]]+)\]"
)
# The C reader prints this once it has finished setup and is actively
# polling both antennas. We wait for it before declaring a throw "live".
READER_READY_RE = re.compile(r"\[RFID\] Scanning on")

THROWS_HEADERS = [
    "session_id",
    "setup",
    "throw_num",
    "start_time",
    "end_time",
    "duration_s",
    "n_unique_tags",
    "epcs",
    "antennas_hit",
    "setup_photo",
]

TAGREADS_HEADERS = [
    "session_id",
    "setup",
    "throw_num",
    "epc",
    "antenna",
    "timestamp",
]

# Column widths (in Excel character units) for readability.
THROWS_WIDTHS    = [16, 22, 10, 22, 22, 11, 8, 60, 22, 20]
TAGREADS_WIDTHS  = [16, 22, 10, 28, 12, 22]

# Embedded-thumbnail height in pixels. Excel row height is in points; one
# row is sized to comfortably hold an 80-px-tall image.
THUMB_HEIGHT_PX  = 80
ROW_HEIGHT_PT    = 64


# ─────────────────────────── data types ────────────────────────────


@dataclass
class TagRead:
    epc: str
    antenna: str
    ts: str


@dataclass
class ThrowResult:
    setup: str
    throw_num: int
    start_time: dt.datetime
    end_time: dt.datetime
    reads: List[TagRead] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    @property
    def unique_epcs(self) -> List[str]:
        seen: List[str] = []
        for r in self.reads:
            if r.epc not in seen:
                seen.append(r.epc)
        return seen

    @property
    def antennas_hit(self) -> List[str]:
        return sorted({r.antenna for r in self.reads})


# ─────────────────────────── workbook I/O ───────────────────────────


def ensure_workbook() -> None:
    """Create `results.xlsx` with the two sheets if it doesn't already exist."""
    if RESULTS_XLSX.exists():
        return
    wb = Workbook()
    throws = wb.active
    throws.title = "Throws"
    throws.append(THROWS_HEADERS)
    for col_idx, w in enumerate(THROWS_WIDTHS, start=1):
        throws.column_dimensions[get_column_letter(col_idx)].width = w

    tagreads = wb.create_sheet("TagReads")
    tagreads.append(TAGREADS_HEADERS)
    for col_idx, w in enumerate(TAGREADS_WIDTHS, start=1):
        tagreads.column_dimensions[get_column_letter(col_idx)].width = w

    wb.save(RESULTS_XLSX)


def thumb_for(setup: str) -> Optional[Path]:
    """Return a cached thumbnail path for `setup`, regenerating if the
    source photo has been updated. Returns None if no source image exists."""
    src = IMAGES_DIR / f"{setup}.png"
    if not src.exists():
        return None
    THUMB_DIR.mkdir(exist_ok=True)
    dst = THUMB_DIR / f"{setup}_thumb.png"
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    img = PILImage.open(src)
    # Preserve aspect ratio; cap height.
    img.thumbnail((10_000, THUMB_HEIGHT_PX))
    img.save(dst, "PNG")
    return dst


def append_throw(session_id: str, throw: ThrowResult) -> None:
    """Append `throw` to results.xlsx: one summary row in Throws (with the
    setup-photo thumbnail embedded) and one row per tag read in TagReads."""
    wb = load_workbook(RESULTS_XLSX)
    throws = wb["Throws"]
    tagreads = wb["TagReads"]

    photo_col_letter = get_column_letter(len(THROWS_HEADERS))
    next_row = throws.max_row + 1
    throws.append([
        session_id,
        throw.setup,
        throw.throw_num,
        throw.start_time.strftime("%Y-%m-%d %H:%M:%S"),
        throw.end_time.strftime("%Y-%m-%d %H:%M:%S"),
        round(throw.duration_s, 2),
        len(throw.unique_epcs),
        ", ".join(throw.unique_epcs),
        ", ".join(throw.antennas_hit),
        "",
    ])
    throws.row_dimensions[next_row].height = ROW_HEIGHT_PT

    thumb = thumb_for(throw.setup)
    if thumb is not None:
        img = XLImage(str(thumb))
        img.anchor = f"{photo_col_letter}{next_row}"
        throws.add_image(img)

    for r in throw.reads:
        tagreads.append([
            session_id,
            throw.setup,
            throw.throw_num,
            r.epc,
            r.antenna,
            r.ts,
        ])

    wb.save(RESULTS_XLSX)


# ────────────────────── rfid_reader subprocess ──────────────────────


def run_one_throw(setup: str, throw_num: int) -> ThrowResult:
    """Spawn `rfid_reader`, stream its output, collect every reported tag
    detection until the operator presses ENTER, then kill the subprocess
    and return the collected ThrowResult."""
    print(
        f"\n[{setup} | Throw #{throw_num}] starting reader... "
        f"(press ENTER once you've thrown the containers to end)"
    )

    proc = subprocess.Popen(
        [str(RFID_BINARY)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
    )

    reads: List[TagRead] = []
    reader_ready = threading.Event()
    reader_exited = threading.Event()
    start_time: List[dt.datetime] = []  # mutable slot set by reader thread

    def reader_thread() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write("    " + line)
            sys.stdout.flush()
            clean = ANSI_RE.sub("", line)
            if not reader_ready.is_set() and READER_READY_RE.search(clean):
                start_time.append(dt.datetime.now())
                reader_ready.set()
                print(
                    f"[{setup} | Throw #{throw_num}] LIVE — drop containers, "
                    f"press ENTER to end."
                )
                sys.stdout.flush()
            m = TAG_LINE_RE.search(clean)
            if m:
                reads.append(TagRead(
                    epc=m.group("epc"),
                    antenna=m.group("antenna"),
                    ts=m.group("ts"),
                ))
        reader_exited.set()

    t = threading.Thread(target=reader_thread, daemon=True)
    t.start()

    try:
        input()  # block until operator presses ENTER (or EOF/Ctrl-D)
    except (KeyboardInterrupt, EOFError):
        pass

    end_time = dt.datetime.now()

    # Send SIGINT so rfid_reader's signal handler runs CAENRFID_Disconnect()
    # cleanly. Escalate if it doesn't comply.
    try:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            proc.kill()
    t.join(timeout=2)

    # If reader_ready never fired (e.g. reader couldn't connect), fall back
    # to "now" so we still log the failed throw.
    actual_start = start_time[0] if start_time else end_time

    return ThrowResult(
        setup=setup,
        throw_num=throw_num,
        start_time=actual_start,
        end_time=end_time,
        reads=reads,
    )


# ───────────────────────────── menu loop ─────────────────────────────


def pick_setup() -> int:
    """Prompt the operator for a setup; returns an index into SETUPS."""
    while True:
        print("\nAvailable antenna setups:")
        for i, s in enumerate(SETUPS, 1):
            print(f"  {i}. {s}")
        choice = input("Select setup [1/2/3]: ").strip()
        if choice in {"1", "2", "3"}:
            return int(choice) - 1
        print("  Invalid choice, try again.")


def main() -> int:
    if not RFID_BINARY.is_file() or not os.access(RFID_BINARY, os.X_OK):
        print(f"ERROR: '{RFID_BINARY}' not found or not executable.")
        print("Build it first:  ./compile.sh")
        return 1

    ensure_workbook()
    session_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"=== Antenna-position test session {session_id} ===")
    print(f"Results: {RESULTS_XLSX}")

    setup_idx = pick_setup()
    # Per-setup throw counters so each setup has its own #1, #2, ...
    throw_counters = {s: 0 for s in SETUPS}

    while True:
        setup = SETUPS[setup_idx]
        prompt = (
            f"\n[Setup: {setup}]  ENTER = start throw  |  "
            f"'s' = switch setup  |  'q' = quit\n> "
        )
        try:
            choice = input(prompt).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            return 0

        if choice == "q":
            print("Bye.")
            return 0
        if choice == "s":
            setup_idx = pick_setup()
            continue

        throw_counters[setup] += 1
        result = run_one_throw(setup, throw_counters[setup])
        print(
            f"[{setup} | Throw #{result.throw_num}] DONE — "
            f"{len(result.unique_epcs)} unique tag(s), "
            f"{result.duration_s:.1f} s"
        )
        try:
            append_throw(session_id, result)
            print(f"    logged to {RESULTS_XLSX.name}")
        except Exception as exc:
            print(f"    ERROR writing to {RESULTS_XLSX.name}: {exc}")
            print("    (throw was NOT saved — fix the issue and retry)")


if __name__ == "__main__":
    sys.exit(main())
