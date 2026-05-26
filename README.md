# RFID Reader + WS2812 LED Feedback

This folder is the **RFID half** of the project (Raspberry Pi CM4 + CM4 carrier
board + CAEN R3100C-Lepton3 reader + 2 antennas). It scans for **unique** EPC
tags via the CAEN reader, holds an attached WS2812 LED strip on solid **white**
while idle, and **blinks it green for ~1 s on every new unique tag** — so the
operator gets a visual count of containers as they're scanned.

## Files

| File | Purpose |
|------|---------|
| `rfid_reader.c`     | C program that talks to the CAEN reader, performs continuous inventory on both antennas, dedupes via a `seen_tags[]` table until **no tag reads occur for 15 s**, then clears that list so the same EPCs can be reported again; prints each new detection with timestamp and antenna (`Source_0` / `Source_1`). |
| `compile.sh`        | Builds `rfid_reader` from `rfid_reader.c` + the `SRC/` CAEN light library. |
| `rfid_led.py`       | Python bridge: launches the `rfid_reader` binary, parses its stdout, holds the WS2812 strip white while idle, and blinks it green for 1 s on every new unique tag. |
| `system.sh`         | One-shot runner: checks the `SRC/` library, compiles, and launches `rfid_led.py` (with `sudo` so the LED PWM/DMA can be accessed). |
| `SRC/`              | CAEN RFID Light library sources/headers (do not modify). |

## Hardware

- Raspberry Pi CM4 + CM4 carrier board
- CAEN R3100C-Lepton3 25 dBm RFID reader on `/dev/ttyACM0` (USB)
- 2× UHF antennas on `Source_0` and `Source_1`
- WS2812 LED strip on **GPIO12 (PWM0)**, 19 LEDs (configured in `rfid_led.py`)

## Build & Run

```bash
# 1. Make scripts executable (first time only)
chmod +x compile.sh system.sh

# 2. Make sure the Python LED library is installed on the Pi
sudo pip3 install rpi_ws281x

# 3. Run everything
./system.sh
```

`system.sh` will:

1. Verify the `SRC/` CAEN library files are present.
2. Check USB permissions for `/dev/ttyACM0` / `/dev/ttyUSB0`.
3. Compile `rfid_reader`.
4. Launch `rfid_led.py`, which spawns `rfid_reader` and watches its output.

## What you'll see

```
[RFID] TAG DETECTED: E20000172211010418905449 [Source_0] [2026-04-29 14:32:45]
[LED-RFID] Tags scanned: 1
```

LED behaviour:

- **At startup / when idle:** the whole strip is solid **white** (`#FFFFFF`).
- **Each new unique tag:** a brief white off-pulse (~100 ms) → solid **green**
  (`#00FF00`) for **1 s** → back to white.
- **Multiple tags in quick succession:** every new tag cuts the current green
  pulse short and starts a fresh one, so scanning N containers in a row
  produces N distinct green blinks — a visual counter for the operator. The
  running total is also printed in the terminal next to each tag line.

Press **Ctrl+C** to stop. The bridge sends `SIGINT` to the C reader, waits for
it to disconnect cleanly, then turns the LEDs off (`#000000`).

## Tweaks

- LED count / pin / brightness: edit the `LED_*` constants at the top of
  `rfid_led.py`.
- Green blink length: change `GREEN_HOLD_SECONDS` in `rfid_led.py`.
- Gap between back-to-back blinks: change `WHITE_FLASH_SECONDS` in
  `rfid_led.py`.
- RFID output power: edit `POWER_MW` in `rfid_reader.c`, then re-run
  `./compile.sh` (or just `./system.sh`).
- Time between full **two-antenna** poll rounds: edit `SCAN_MS` (milliseconds)
  in `rfid_reader.c`, then recompile.
- How long with **no tag reads** before dedupe clears so repeats count again:
  edit `IDLE_RESET_SEC` in `rfid_reader.c`, then recompile.

## Troubleshooting

- **`Failed to connect`** — check the USB cable, try `sudo chmod 666 /dev/ttyACM0`,
  or add your user to the `dialout` group: `sudo usermod -a -G dialout $USER`
  then log out / log in.
- **`mmap() failed` from rpi_ws281x** — you must run as root (`sudo`),
  which `system.sh` already handles.
- **Reader connects but no tags appear** — bring a tag closer, confirm both
  antennas are connected, or increase `POWER_MW` in `rfid_reader.c` (within
  hardware limits), then recompile.
