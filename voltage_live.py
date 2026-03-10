import serial
import json
import time
import threading
import tkinter as tk
from datetime import datetime

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ── Config ──
COMPORT = "COM9"
BAUD_RATE = 115200
SAMPLE_INTERVAL = 1 / 3  # ~3 samples per second
DISPLAY_INTERVAL = 10  # print to console every 10 seconds
DURATION_SECONDS = 200 * 3600  # 200 hours
OUTPUT_FILE = "voltage_log.jsonl"

# ── Shared state ──
timestamps = []
voltages = []
currents = []
powers = []
data_lock = threading.Lock()
serial_lock = threading.Lock()
tracker_status = {"count": 0, "total": 0, "running": True}
ser = None  # global serial connection


# ── Serial helpers ──
def send_command(cmd):
    with serial_lock:
        ser.write((cmd + "\n").encode())
        time.sleep(0.1)
        return ser.readline().decode().strip()


# ── Serial tracker (background thread) ──
def tracker_thread():
    total = int(DURATION_SECONDS / SAMPLE_INTERVAL)
    tracker_status["total"] = total
    print(f"Sampling {1/SAMPLE_INTERVAL:.0f}x/s, displaying every {DISPLAY_INTERVAL}s, for {DURATION_SECONDS}s ({total} readings)")
    print(f"Output: {OUTPUT_FILE}\n")

    count = 0
    last_display = 0
    try:
        with open(OUTPUT_FILE, "a") as f:
            while count < total and tracker_status["running"]:
                ts = datetime.now()
                timestamp = ts.isoformat()
                try:
                    voltage = send_command("measure:voltage?")
                    current = send_command("measure:current?")
                except Exception as e:
                    print(f"[{timestamp}] Read error: {e}")
                    time.sleep(SAMPLE_INTERVAL)
                    continue

                try:
                    v = float(voltage)
                    c = float(current)
                    power = round(v * c, 4)
                except ValueError:
                    v, c, power = 0.0, 0.0, None

                entry = {
                    "timestamp": timestamp,
                    "voltage": voltage,
                    "current": current,
                    "power": power,
                    "reading": count + 1,
                }
                f.write(json.dumps(entry) + "\n")
                f.flush()

                with data_lock:
                    timestamps.append(ts)
                    voltages.append(v)
                    currents.append(c)
                    powers.append(power if power is not None else 0.0)

                count += 1
                tracker_status["count"] = count

                now = time.monotonic()
                if now - last_display >= DISPLAY_INTERVAL:
                    print(f"[{timestamp}] V={voltage} A={current} W={power} ({count}/{total})")
                    last_display = now

                time.sleep(SAMPLE_INTERVAL)
    finally:
        print(f"Done. {count} readings saved to {OUTPUT_FILE}")


# ── Tkinter control panel (background thread) ──
def control_panel_thread():
    root = tk.Tk()
    root.title("DC310Pro Control")
    root.resizable(False, False)

    status_var = tk.StringVar(value="Status: --")

    def set_value(cmd_prefix, entry):
        val = entry.get().strip()
        if not val:
            return
        try:
            float(val)
        except ValueError:
            status_var.set("Status: Invalid number")
            return
        resp = send_command(f"{cmd_prefix} {val}")
        status_var.set(f"Status: {cmd_prefix} {val} → {resp if resp else 'OK'}")

    def set_output(state):
        resp = send_command(f"output {state}")
        status_var.set(f"Status: output {state} → {resp if resp else 'OK'}")

    def refresh_status():
        try:
            v = send_command("voltage?")
            c = send_command("current?")
            out = send_command("output?")
            status_var.set(f"Set: V={v}  A={c}  Output={out}")
        except Exception as e:
            status_var.set(f"Status: Error - {e}")

    # ── Layout ──
    pad = {"padx": 8, "pady": 4}

    row = 0
    for label_text, cmd in [
        ("Voltage (V):", "voltage"),
        ("Current (A):", "current"),
        ("Volt Limit:", "voltage:limit"),
        ("Curr Limit:", "current:limit"),
    ]:
        tk.Label(root, text=label_text, anchor="e", width=12).grid(row=row, column=0, **pad)
        entry = tk.Entry(root, width=10)
        entry.grid(row=row, column=1, **pad)
        btn = tk.Button(root, text="Set", width=5,
                        command=lambda c=cmd, e=entry: set_value(c, e))
        btn.grid(row=row, column=2, **pad)
        row += 1

    # Output on/off
    tk.Label(root, text="Output:", anchor="e", width=12).grid(row=row, column=0, **pad)
    btn_frame = tk.Frame(root)
    btn_frame.grid(row=row, column=1, columnspan=2, **pad, sticky="w")
    tk.Button(btn_frame, text="ON", width=6, bg="#4CAF50", fg="white",
              command=lambda: set_output(1)).pack(side="left", padx=2)
    tk.Button(btn_frame, text="OFF", width=6, bg="#f44336", fg="white",
              command=lambda: set_output(0)).pack(side="left", padx=2)
    row += 1

    # Refresh button
    tk.Button(root, text="Refresh Status", command=refresh_status).grid(
        row=row, column=0, columnspan=3, padx=8, pady=(8, 2))
    row += 1

    # Status label
    tk.Label(root, textvariable=status_var, anchor="w", fg="#555").grid(
        row=row, column=0, columnspan=3, **pad, sticky="w")

    refresh_status()

    def on_close():
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


# ── Chart (main thread) ──
def update(frame):
    with data_lock:
        if not timestamps:
            return
        ts = list(timestamps)
        vs = list(voltages)
        cs = list(currents)
        ps = list(powers)

    # Thin to every 10th second (every 30th sample at 3 samples/s)
    step = int(DISPLAY_INTERVAL * (1 / SAMPLE_INTERVAL))  # 10 * 3 = 30
    ts = ts[::step]
    vs = vs[::step]
    cs = cs[::step]
    ps = ps[::step]

    # Convert timestamps to elapsed minutes or hours
    t0 = ts[0]
    elapsed_total = (ts[-1] - t0).total_seconds() / 3600
    if elapsed_total < 5:
        elapsed_vals = [(t - t0).total_seconds() / 60 for t in ts]
        x_label = "Elapsed (minutes)"
    else:
        elapsed_vals = [(t - t0).total_seconds() / 3600 for t in ts]
        x_label = "Elapsed (hours)"

    for ax, data, label, color in [
        (ax1, vs, "Voltage (V)", "#2196F3"),
        (ax2, cs, "Current (A)", "#FF9800"),
        (ax3, ps, "Power (W)", "#4CAF50"),
    ]:
        ax.clear()
        ax.plot(elapsed_vals, data, color=color, linewidth=1, marker="o", markersize=3)
        ax.set_ylabel(label, fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.text(
            0.98, 0.95, f"{data[-1]:.3f}",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=14, fontweight="bold", color=color,
        )

    ax3.set_xlabel(x_label)

    hours, remainder = divmod(int((ts[-1] - t0).total_seconds()), 3600)
    minutes = remainder // 60
    count = tracker_status["count"]
    total = tracker_status["total"]
    fig.suptitle(
        f"DC310Pro Live Monitor — {count}/{total} readings, elapsed {hours}h {minutes}m",
        fontsize=12,
    )


# ── Start ──
ser = serial.Serial(COMPORT, BAUD_RATE, timeout=2)
time.sleep(1)

idn = send_command("*idn?")
print(f"Device: {idn}")

# Launch tracker thread
tracker = threading.Thread(target=tracker_thread, daemon=True)
tracker.start()

# Launch control panel thread
control = threading.Thread(target=control_panel_thread, daemon=True)
control.start()

# Chart in main thread
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
fig.subplots_adjust(hspace=0.15, top=0.92)

ani = FuncAnimation(fig, update, interval=DISPLAY_INTERVAL * 1000, cache_frame_data=False)

try:
    plt.show()
except KeyboardInterrupt:
    pass
finally:
    tracker_status["running"] = False
    tracker.join(timeout=10)
    ser.close()
