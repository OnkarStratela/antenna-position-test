#!/bin/bash
# One-shot runner for the antenna-position test logger.
#
# Same prep as system.sh (CAEN library check, USB permissions check,
# compile, auto-sudo for WS2812 PWM/DMA access) but launches
# antenna_test_logger.py instead of rfid_led.py.

echo "===== Antenna Position Test Logger ====="
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Checking for CAEN library files in SRC folder...${NC}"

if [ ! -d "SRC" ]; then
    echo -e "${RED}SRC folder not found!${NC}"
    echo "Please create SRC folder and copy CAEN library files there."
    exit 1
fi

REQUIRED_FILES=(
    "SRC/CAENRFIDLib_Light.c"
    "SRC/CAENRFIDLib_Light.h"
    "SRC/CAENRFIDTypes_Light.h"
    "SRC/IO_Light.c"
    "SRC/IO_Light.h"
    "SRC/Protocol_Light.h"
    "SRC/host.c"
    "SRC/host.h"
)

MISSING_FILES=()
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -ne 0 ]; then
    echo -e "${RED}Missing required CAEN library files:${NC}"
    for file in "${MISSING_FILES[@]}"; do
        echo "  - $file"
    done
    echo ""
    echo "Please copy all CAEN library files to the SRC directory."
    exit 1
fi

echo -e "${GREEN}All required CAEN files found in SRC folder!${NC}"

echo -e "${YELLOW}Checking USB device access...${NC}"
if [ -e /dev/ttyACM0 ] || [ -e /dev/ttyUSB0 ]; then
    if [ ! -r /dev/ttyACM0 ] && [ ! -r /dev/ttyUSB0 ]; then
        echo -e "${YELLOW}USB device found but no read permission.${NC}"
        echo "Adding user to dialout group..."
        sudo usermod -a -G dialout "$USER"
        echo -e "${GREEN}User added to dialout group. Please logout and login again.${NC}"
    else
        echo -e "${GREEN}USB device access OK${NC}"
    fi
else
    echo -e "${YELLOW}No CAEN RFID reader detected on USB${NC}"
    echo "Please connect the CAEN RFID reader to USB port"
fi

echo -e "${YELLOW}Setting permissions...${NC}"
chmod +x compile.sh 2>/dev/null

echo -e "${YELLOW}Compiling RFID reader...${NC}"
./compile.sh

if [ $? -ne 0 ]; then
    echo -e "${RED}Compilation failed. Please check error messages.${NC}"
    exit 1
fi

echo -e "${GREEN}Compilation successful!${NC}"
echo ""
echo -e "${GREEN}Launching antenna test logger with LED feedback...${NC}"
echo -e "${YELLOW}(LEDs blink GREEN on every new unique tag during a throw)${NC}"
echo ""

# rpi_ws281x needs root for WS2812 PWM/DMA access. Self-elevate if needed.
if [ "$EUID" -ne 0 ]; then
    sudo python3 antenna_test_logger.py
else
    python3 antenna_test_logger.py
fi
