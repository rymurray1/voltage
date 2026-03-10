import serial
import json
import time
from datetime import datetime

COMPORT = "COM9"
BAUD_RATE = 115200
INTERVAL_SECONDS = 5
DURATION_SECONDS = 200 * 3600  # 200 hours
OUTPUT_FILE = "voltage_log.jsonl"


def send_command(ser, cmd):
    ser.write((cmd + "\n").encode())
    time.sleep(0.1)
    response = ser.readline().decode().strip()
    return response


ser = serial.Serial(COMPORT, BAUD_RATE, timeout=2)
time.sleep(1)  # wait for connection to stabilize

idn = send_command(ser, "*idn?")
print(f"Device: {idn}")

total_readings = int(DURATION_SECONDS / INTERVAL_SECONDS)
print(f"Logging every {INTERVAL_SECONDS}s for {DURATION_SECONDS}s ({total_readings} readings)")
print(f"Output: {OUTPUT_FILE}")
print("Press Ctrl+C to stop early.\n")

count = 0
try:
    with open(OUTPUT_FILE, "a") as f:
        while count < total_readings:
            timestamp = datetime.now().isoformat()
            try:
                voltage = send_command(ser, "measure:voltage?")
                current = send_command(ser, "measure:current?")
            except Exception as e:
                print(f"[{timestamp}] Read error: {e}")
                time.sleep(INTERVAL_SECONDS)
                continue

            try:
                power = round(float(voltage) * float(current), 4)
            except ValueError:
                power = None

            entry = {
                "timestamp": timestamp,
                "voltage": voltage,
                "current": current,
                "power": power,
                "reading": count + 1,
            }
            f.write(json.dumps(entry) + "\n")
            f.flush()

            count += 1
            print(f"[{timestamp}] V={voltage} A={current} W={power} ({count}/{total_readings})")

            time.sleep(INTERVAL_SECONDS)

except KeyboardInterrupt:
    print(f"\nStopped early after {count} readings.")
finally:
    ser.close()
    print(f"Done. {count} readings saved to {OUTPUT_FILE}")
