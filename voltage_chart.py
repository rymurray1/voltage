import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.animation import FuncAnimation
from datetime import datetime

LOG_FILE = "voltage_log.jsonl"
POLL_INTERVAL_MS = 2000

timestamps = []
voltages = []
currents = []
powers = []
file_pos = 0


def load_new_data():
    global file_pos
    new_lines = 0
    try:
        with open(LOG_FILE, "r") as f:
            f.seek(file_pos)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                timestamps.append(datetime.fromisoformat(entry["timestamp"]))
                voltages.append(float(entry["voltage"]))
                currents.append(float(entry["current"]))
                p = entry.get("power")
                powers.append(float(p) if p is not None else 0.0)
                new_lines += 1
            file_pos = f.tell()
    except FileNotFoundError:
        pass
    return new_lines


def update(frame):
    load_new_data()
    if not timestamps:
        return

    for ax, data, label, color in [
        (ax1, voltages, "Voltage (V)", "#2196F3"),
        (ax2, currents, "Current (A)", "#FF9800"),
        (ax3, powers, "Power (W)", "#4CAF50"),
    ]:
        ax.clear()
        ax.plot(timestamps, data, color=color, linewidth=1)
        ax.set_ylabel(label, fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.text(
            0.98, 0.95, f"{data[-1]:.3f}",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=14, fontweight="bold", color=color,
        )

    ax3.set_xlabel("Time")
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    elapsed = timestamps[-1] - timestamps[0]
    hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
    minutes = remainder // 60
    fig.suptitle(
        f"DC310Pro Live Monitor — {len(timestamps)} readings, elapsed {hours}h {minutes}m",
        fontsize=12,
    )


# Load initial data
load_new_data()

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
fig.subplots_adjust(hspace=0.15, top=0.92)

ani = FuncAnimation(fig, update, interval=POLL_INTERVAL_MS, cache_frame_data=False)
plt.show()
