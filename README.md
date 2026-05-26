# Antenna Position Test

Test harness for comparing **three dual-antenna mounting positions** in an
RFID bin. For each test session the operator drops batches of tagged
containers into the bin; the program records every throw — which tags were
detected, on which antenna, how long the throw lasted — and appends it to a
single master Excel workbook with the antenna-position photo embedded next
to the row.

Three antenna positions under test:

| Setup name              | What it means                                  |
|-------------------------|------------------------------------------------|
| `antennas_opposite`     | Two antennas mounted facing each other across the bin (see `images/antennas_opposite.png`). |
| `antennas_vertical`     | Two antennas stacked vertically on the same wall (see `images/antennas_vertical.png`).      |
| `antennas_horizontal`   | Two antennas spaced horizontally on the same wall (see `images/antennas_horizontal.png`).   |

## Files

| File                       | Purpose |
|----------------------------|---------|
| `rfid_reader.c`            | C program that talks to the CAEN reader, continuously inventories both antennas, and prints every **new unique** EPC with timestamp and antenna name. Dedupes for its entire process lifetime — see "How throws are isolated" below. |
| `compile.sh`               | Builds `rfid_reader` from `rfid_reader.c` + the `SRC/` CAEN light library. |
| `antenna_test_logger.py`   | **The test harness.** Wraps `rfid_reader`, presents a per-throw menu, hot-switches between the 3 setups, drives the same WS2812 + GPIO13 LED feedback as `rfid_led.py`, and appends results to `results.xlsx` with embedded setup photos. |
| `rfid_led.py`              | Standalone LED-only bridge — drives the WS2812 strip green on every new tag, no logging. Useful as a quick LED hardware check when you don't need a test session. (Can't run at the same time as the logger — both spawn `rfid_reader`.) |
| `system.sh`                | One-shot runner for the standalone LED-only flow (compiles + launches `rfid_led.py`). |
| `requirements.txt`         | Python deps needed by the logger: `openpyxl`, `Pillow`. |
| `images/`                  | The three reference photos, one per antenna setup. Embedded into the results spreadsheet. |
| `SRC/`                     | CAEN RFID Light library sources/headers (do not modify). |

## Hardware

- Raspberry Pi CM4 + CM4 carrier board
- CAEN R3100C-Lepton3 25 dBm RFID reader on `/dev/ttyACM0` (USB)
- 2× UHF antennas on `Source_0` and `Source_1`
- WS2812 LED strip on GPIO12 (PWM0) + a held-on PWM LED on GPIO13 — visual feedback during throws.

## Setup

```bash
# 1. Make scripts executable (first time only)
chmod +x compile.sh system.sh

# 2. Build the C reader
./compile.sh

# 3. Install Python deps for the logger.
#    On Pi OS Bookworm + later, pip3 is locked down by PEP 668 — use apt:
sudo apt install -y python3-openpyxl python3-pil
#    (or, if those packages aren't available on your distro:
#       pip3 install --break-system-packages -r requirements.txt )

# 4. (Optional) Python deps for LED feedback — same packages rfid_led.py uses.
#    Skip this if you don't need the LED strip / GPIO13 LED while testing.
sudo apt install -y python3-gpiozero
#    rpi_ws281x isn't in apt; install via pip with the PEP 668 override:
sudo pip3 install --break-system-packages rpi_ws281x
```

## Run a test session

The WS2812 LED strip needs root for PWM/DMA access, so launch with sudo:

```bash
sudo python3 antenna_test_logger.py
```

(If you run without sudo it still works — you just won't get LED feedback;
the spreadsheet is recorded exactly the same.)

You'll be asked which of the three setups is currently mounted, then dropped
into a per-throw menu. Sample session:

```
=== Antenna-position test session 20260526-161205 ===
Results: /home/stratela/antenna-position-test/results.xlsx

Available antenna setups:
  1. antennas_opposite
  2. antennas_vertical
  3. antennas_horizontal
Select setup [1/2/3]: 2

[Setup: antennas_vertical]  ENTER = start throw  |  's' = switch setup  |  'q' = quit
> <ENTER>

[antennas_vertical | Throw #1] starting reader... (press ENTER once you've thrown the containers to end)
    [RFID] Connecting to CAEN reader on /dev/ttyACM0 at 921600 baud...
    [RFID] Power set to 316 mW
    [RFID] Scanning on Source_0 and Source_1 every 10 ms — press Ctrl+C to stop
[antennas_vertical | Throw #1] LIVE — drop containers, press ENTER to end.
    [RFID] TAG DETECTED: E280699500004003D9D7C8B0 [Source_0] [2026-05-26 16:12:14]
    [RFID] TAG DETECTED: E2806995000040034A1E7BB2 [Source_1] [2026-05-26 16:12:15]
<ENTER>
[antennas_vertical | Throw #1] DONE — 2 unique tag(s), 4.3 s
    logged to results.xlsx
```

Number of throws per session, number of containers per throw, and which
setup is mounted are all free — pick `'s'` from the menu any time to switch
to a different antenna position and keep going.

Press `'q'` (or Ctrl-C) at the menu to end the session cleanly.

## How throws are isolated

`rfid_reader` only ever prints each EPC once per process lifetime — so if
the same tag is thrown twice, only the first throw would see it. To make
every throw a clean slate, the logger **spawns a fresh `rfid_reader`
subprocess for every throw** and kills it cleanly (SIGINT → graceful
disconnect) when you press ENTER. The cost is ~1–2 s of reader startup at
the beginning of each throw; the logger displays `LIVE — drop containers,
press ENTER to end.` once the reader is actually scanning, so you know
when it's safe to throw.

## What gets recorded

A single file `results.xlsx` at the repo root, appended to across every
session.

### Sheet `Throws` — one row per throw

| Column         | Description |
|----------------|-------------|
| session_id     | Timestamp of the test session, e.g. `20260526-161205`. |
| setup          | `antennas_opposite` / `antennas_vertical` / `antennas_horizontal`. |
| throw_num      | 1-based throw counter, **independent per setup** (each setup has its own #1, #2, ...). |
| start_time     | When the reader went LIVE for this throw. |
| end_time       | When the operator pressed ENTER. |
| duration_s     | end − start, in seconds. |
| n_unique_tags  | Number of distinct EPCs detected during this throw. |
| epcs           | Comma-separated list of those EPCs. |
| antennas_hit   | Which sources reported anything (`Source_0`, `Source_1`, or both). |
| setup_photo    | Embedded thumbnail of the corresponding `images/<setup>.png`. |

### Sheet `TagReads` — one row per first detection

| Column     | Description |
|------------|-------------|
| session_id | Same as on the Throws sheet. |
| setup      | Same. |
| throw_num  | Same. |
| epc        | The detected tag EPC (hex). |
| antenna    | `Source_0` or `Source_1`. |
| timestamp  | Timestamp reported by the C reader. |

`results.xlsx` is git-ignored — it's the *raw test data* and lives only on
the Pi. Copy it off when you want to analyse a campaign.

## LED behaviour

`antenna_test_logger.py` mirrors the LED feedback from `rfid_led.py` for
the entire session:

- Idle (menu, between throws): WS2812 strip is solid **white**.
- During a throw: a brief white off-pulse → solid **green** for 1 s → back
  to white on **every new unique tag** the C reader reports. Multiple new
  tags in quick succession produce that many distinct green blinks.
- GPIO13 PWM LED is held on at 50% duty for the whole session.
- On exit (`q`, Ctrl-C, or SIGTERM): strip OFF, GPIO13 forced LOW.

If `rpi_ws281x` / `gpiozero` aren't installed, or the script isn't run as
root, the LED layer is silently skipped and the logger keeps working —
spreadsheet output is identical.

### Standalone LED-only mode (no logging)

If you just want to verify the LED hardware without doing a test session:

```bash
./system.sh                # builds + launches rfid_led.py
```

Don't run `rfid_led.py` and `antenna_test_logger.py` at the same time —
they both spawn `rfid_reader` and only one can hold the USB serial port.

## Tweaks

- RFID output power: edit `POWER_MW` in `rfid_reader.c`, then `./compile.sh`.
- Two-antenna poll interval: edit `SCAN_MS` (ms) in `rfid_reader.c`, then recompile.
- Embedded thumbnail size: `THUMB_HEIGHT_PX` / `ROW_HEIGHT_PT` in `antenna_test_logger.py`.
- Add a fourth setup: append it to `SETUPS` in `antenna_test_logger.py`, drop a matching `images/<name>.png`, done.

## Troubleshooting

- **`Failed to connect`** — check the USB cable, try `sudo chmod 666 /dev/ttyACM0`, or add your user to the `dialout` group: `sudo usermod -a -G dialout $USER`, then log out / log in.
- **`rfid_reader' not found or not executable`** — run `./compile.sh` first.
- **`ModuleNotFoundError: openpyxl`** — `sudo apt install -y python3-openpyxl python3-pil` (or, if not available on your OS, `pip3 install --break-system-packages -r requirements.txt`).
- **`error: externally-managed-environment`** when running plain `pip3 install` — that's Pi OS Bookworm's PEP 668 lock. Same fix as above: prefer apt, or pass `--break-system-packages` to pip.
- **`[LED] WARN: could not init WS2812 strip ... mmap() failed`** — you ran the logger without `sudo`. WS2812 PWM/DMA access needs root. Run with `sudo python3 antenna_test_logger.py`. The logger continues without LEDs in this case.
- **Throw shows 0 tags even with containers present** — make sure you waited for the `LIVE` message before throwing; the C reader takes ~1–2 s to initialise.
- **`results.xlsx` is open in Excel on another machine while the logger tries to save** — Excel locks the file. Close it on the other end, then start a fresh throw (or copy the file off the Pi before opening).
