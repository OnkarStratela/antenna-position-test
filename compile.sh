#!/bin/bash

echo "[Build] Starting RFID reader compilation..."

# Check if SRC directory exists
if [ ! -d "SRC" ]; then
    echo "[Build] ERROR: SRC directory not found!"
    echo "[Build] Please ensure CAEN library files are in the SRC folder"
    exit 1
fi

# Check for critical files
if [ ! -f "SRC/CAENRFIDLib_Light.c" ] || [ ! -f "SRC/host.c" ] || [ ! -f "SRC/IO_Light.c" ]; then
    echo "[Build] ERROR: Missing CAEN library source files in SRC folder!"
    echo "[Build] Required files:"
    echo "  - SRC/CAENRFIDLib_Light.c"
    echo "  - SRC/host.c"
    echo "  - SRC/IO_Light.c"
    exit 1
fi

if [ ! -f "rfid_reader.c" ]; then
    echo "[Build] ERROR: rfid_reader.c not found!"
    exit 1
fi

echo "[Build] Found all required files, compiling..."

# Build against CAEN Light sources in SRC (Linux)
gcc \
  rfid_reader.c \
  SRC/host.c SRC/CAENRFIDLib_Light.c SRC/IO_Light.c \
  -ISRC \
  -o rfid_reader \
  -lpthread -lm \
  -Wall

if [ $? -eq 0 ]; then
    echo "[Build] Success! Created rfid_reader executable"
    
    # Make executable
    chmod +x rfid_reader
    
    echo "[Build] Ready to run!"
    echo ""
    echo "To run RFID reader: ./rfid_reader"
    echo "Or use:            ./run_system.sh"
else
    echo "[Build] Compilation failed!"
    echo "[Build] Check that you have gcc installed: sudo apt-get install build-essential"
    exit 1
fi