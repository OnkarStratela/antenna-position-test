// Simple dual-antenna RFID reader (Source_0 + Source_1).
// Continuously scans both antennas; prints every NEW unique EPC in green
// with the antenna that reported it.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <unistd.h>
#include <signal.h>

#include "CAENRFIDLib_Light.h"
#include "host.h"

#define MAX_ID_LENGTH 64
#define MAX_TAGS      1024

#define GREEN "\033[0;32m"
#define RESET "\033[0m"

#define ANTENNA_COUNT 2
#define POWER_MW       316
#define SCAN_MS        10

volatile int running = 0;

static void printHex(uint8_t* vect, uint16_t length, char* result) {
    for (int i = 0; i < length; i++) {
        sprintf(result + (i * 2), "%02X", vect[i]);
    }
    result[length * 2] = '\0';
}

static void handle_sigint(int sig) {
    (void)sig;
    printf("\n[RFID] Stopping...\n");
    running = 0;
}

int main(void) {
    CAENRFIDErrorCodes ec;
    CAENRFIDReader reader = {
        .connect       = _connect,
        .disconnect    = _disconnect,
        .tx            = _tx,
        .rx            = _rx,
        .clear_rx_data = _clear_rx_data,
        .enable_irqs   = _enable_irqs,
        .disable_irqs  = _disable_irqs
    };

    RS232_params port_params = {
        .com         = "/dev/ttyACM0",
        .baudrate    = 921600,
        .dataBits    = 8,
        .stopBits    = 1,
        .parity      = 0,
        .flowControl = 0,
    };

    signal(SIGINT, handle_sigint);

    printf("[RFID] Connecting to CAEN reader on %s at %d baud...\n",
           port_params.com, port_params.baudrate);
    ec = CAENRFID_Connect(&reader, CAENRFID_RS232, &port_params);
    if (ec != CAENRFID_StatusOK) {
        printf("[RFID] Failed to connect (code: %d).\n", ec);
        printf("  - Is reader connected to %s?\n", port_params.com);
        printf("  - Try: sudo chmod 666 %s\n", port_params.com);
        return -1;
    }

    char model[64], serial[64];
    if (CAENRFID_GetReaderInfo(&reader, model, serial) == CAENRFID_StatusOK) {
        printf("[RFID] Reader: %s, Serial: %s\n", model, serial);
    }

    const char *sources[ANTENNA_COUNT] = {"Source_0", "Source_1"};

    CAENRFID_SetPower(&reader, POWER_MW);
    printf("[RFID] Power set to %d mW\n", POWER_MW);
    printf("[RFID] Scanning on %s and %s every %d ms — press Ctrl+C to stop\n\n",
           sources[0], sources[1], SCAN_MS);

    char seen_tags[MAX_TAGS][2 * MAX_ID_LENGTH + 1];
    int  tag_count = 0;

    running = 1;
    while (running) {
        for (int a = 0; a < ANTENNA_COUNT && running; a++) {
            CAENRFIDTagList *tags = NULL, *aux;
            uint16_t numTags = 0;

            ec = CAENRFID_InventoryTag(&reader, (char *)sources[a], 0, 0, 0,
                                       NULL, 0, 0, &tags, &numTags);

            if (ec == CAENRFID_StatusOK && numTags > 0) {
                aux = tags;
                while (aux != NULL) {
                    char epcStr[2 * MAX_ID_LENGTH + 1];
                    printHex(aux->Tag.ID, aux->Tag.Length, epcStr);

                    bool is_new = true;
                    for (int i = 0; i < tag_count; i++) {
                        if (strcmp(seen_tags[i], epcStr) == 0) {
                            is_new = false;
                            break;
                        }
                    }

                    if (is_new) {
                        time_t rawtime;
                        struct tm *timeinfo;
                        char time_buffer[80];
                        time(&rawtime);
                        timeinfo = localtime(&rawtime);
                        strftime(time_buffer, sizeof(time_buffer),
                                 "%Y-%m-%d %H:%M:%S", timeinfo);

                        printf("%s[RFID] TAG DETECTED: %s%s [%s] [%s]\n",
                               GREEN, epcStr, RESET, sources[a], time_buffer);
                        fflush(stdout);

                        if (tag_count < MAX_TAGS) {
                            strcpy(seen_tags[tag_count++], epcStr);
                        }
                    }

                    CAENRFIDTagList *next = aux->Next;
                    free(aux);
                    aux = next;
                }
            }
        }

        usleep(SCAN_MS * 1000);
    }

    CAENRFID_Disconnect(&reader);
    printf("[RFID] Disconnected. Total unique tags detected: %d\n", tag_count);
    return 0;
}
