import serial
import json
import time
import threading
import tkinter as tk
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ── Config ──
COMPORT = "COM9"
BAUD_RATE = 115200
SAMPLE_INTERVAL = 0.5  # 2 samples per second
DISPLAY_INTERVAL = 10  # print to console every 10 seconds
DURATION_SECONDS = 200 * 3600  # 200 hours
THIN_STEP = 20  # plot 1 out of every 20 samples on compressed chart (= every 10s)
LIVE_WINDOW = timedelta(hours=2)

START_TIME = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_FILE = f"{START_TIME}_voltage_log.jsonl"

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


# ── Helper: elapsed x-axis values ──
def elapsed_values(ts_list):
    """Return (elapsed_vals, x_label) with auto minutes/hours scaling."""
    t0 = ts_list[0]
    total_hours = (ts_list[-1] - t0).total_seconds() / 3600
    if total_hours < 5:
        vals = [(t - t0).total_seconds() / 60 for t in ts_list]
        return vals, "Elapsed (minutes)"
    else:
        vals = [(t - t0).total_seconds() / 3600 for t in ts_list]
        return vals, "Elapsed (hours)"


def suptitle_text(ts_list, count, total):
    if len(ts_list) >= 2:
        elapsed = ts_list[-1] - ts_list[0]
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes = remainder // 60
    else:
        hours, minutes = 0, 0
    return f"DC310Pro — {count}/{total} readings, elapsed {hours}h {minutes}m"


# ── Compressed chart update (every 20th sample = every 10s) ──
def update_compressed(frame):
    with data_lock:
        if not timestamps:
            return
        ts = list(timestamps)
        vs = list(voltages)
        cs = list(currents)
        ps = list(powers)

    # Thin: keep every THIN_STEP-th sample
    ts = ts[::THIN_STEP]
    vs = vs[::THIN_STEP]
    cs = cs[::THIN_STEP]
    ps = ps[::THIN_STEP]

    if not ts:
        return

    elapsed_vals, x_label = elapsed_values(ts) if len(ts) >= 2 else ([0.0] * len(ts), "Elapsed (minutes)")

    for ax, data, label, color in [
        (c_ax1, vs, "Voltage (V)", "#2196F3"),
        (c_ax2, cs, "Current (A)", "#FF9800"),
        (c_ax3, ps, "Power (W)", "#4CAF50"),
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

    c_ax3.set_xlabel(x_label)
    fig_compressed.suptitle(
        "Compressed — " + suptitle_text(ts, tracker_status["count"], tracker_status["total"]),
        fontsize=12,
    )


# ── Live chart update (all points, 2-hour sliding window) ──
def update_live(frame):
    with data_lock:
        if not timestamps:
            return
        ts = list(timestamps)
        vs = list(voltages)
        cs = list(currents)
        ps = list(powers)

    if not ts:
        return

    # Determine the window boundaries
    t0_all = ts[0]
    t_last = ts[-1]
    window_elapsed = LIVE_WINDOW.total_seconds()
    total_elapsed = (t_last - t0_all).total_seconds()

    if total_elapsed > window_elapsed:
        # Sliding window — trim to last 2 hours
        cutoff = t_last - LIVE_WINDOW
        idx = 0
        for i, t in enumerate(ts):
            if t >= cutoff:
                idx = i
                break
        ts = ts[idx:]
        vs = vs[idx:]
        cs = cs[idx:]
        ps = ps[idx:]

    # X-axis fits tightly to the data, growing rightward
    x_origin = ts[0]
    elapsed_vals = [(t - x_origin).total_seconds() / 60 for t in ts]
    x_min = 0.0
    x_max = elapsed_vals[-1] if len(elapsed_vals) > 1 else 1.0

    for ax, data, label, color in [
        (l_ax1, vs, "Voltage (V)", "#2196F3"),
        (l_ax2, cs, "Current (A)", "#FF9800"),
        (l_ax3, ps, "Power (W)", "#4CAF50"),
    ]:
        ax.clear()
        ax.plot(elapsed_vals, data, color=color, linewidth=1)
        ax.plot(elapsed_vals[-1], data[-1], color=color, marker="o", markersize=5)
        ax.set_ylabel(label, fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(x_min, x_max)
        ax.text(
            0.98, 0.95, f"{data[-1]:.3f}",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=14, fontweight="bold", color=color,
        )

    l_ax3.set_xlabel("Elapsed (minutes)")
    fig_live.suptitle(
        "Live (2h window) — " + suptitle_text(ts, tracker_status["count"], tracker_status["total"]),
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

# ── Create two figure windows ──
# Compressed: full experiment, thinned to every 10s
fig_compressed, (c_ax1, c_ax2, c_ax3) = plt.subplots(3, 1, figsize=(10, 7), sharex=True, num="Compressed View")
fig_compressed.subplots_adjust(hspace=0.15, top=0.92)

# Live: every data point, 2-hour sliding window
fig_live, (l_ax1, l_ax2, l_ax3) = plt.subplots(3, 1, figsize=(10, 7), sharex=True, num="Live View (2h)")
fig_live.subplots_adjust(hspace=0.15, top=0.92)

# Compressed updates every 10s, live updates every 500ms
ani_compressed = FuncAnimation(fig_compressed, update_compressed, interval=10000, cache_frame_data=False)
ani_live = FuncAnimation(fig_live, update_live, interval=500, cache_frame_data=False)

try:
    plt.show()
except KeyboardInterrupt:
    pass
finally:
    tracker_status["running"] = False
    tracker.join(timeout=10)
    ser.close()
