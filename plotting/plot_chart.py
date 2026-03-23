import json
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch

# ---------------------------------------------------------------------------
# Load data starting from line 19427 (~3.69hr mark, voltage bottom)
# ---------------------------------------------------------------------------
voltages = []
currents = []
hours_elapsed = []

start_line = 19427
max_hours = 100
origin_time = None

with open('20260316_130956_voltage_log.jsonl') as f:
    for i, line in enumerate(f, 1):
        if i < start_line:
            continue
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            v = float(d['voltage'])
            c = float(d['current'])
            ts = datetime.fromisoformat(d['timestamp'])
        except:
            continue

        if origin_time is None:
            origin_time = ts

        elapsed = (ts - origin_time).total_seconds() / 3600.0
        if elapsed > max_hours:
            break

        voltages.append(v)
        currents.append(c)
        hours_elapsed.append(elapsed)

print(f"Loaded {len(voltages)} data points over {hours_elapsed[-1]:.1f} hours")

# ---------------------------------------------------------------------------
# Downsample & smooth
# ---------------------------------------------------------------------------
h = np.array(hours_elapsed)
v = np.array(voltages)
c = np.array(currents)

step = max(1, len(h) // 5000)
h = h[::step]
v = v[::step]
c = c[::step]

window = 50

def sma(arr, w):
    kernel = np.ones(w) / w
    smoothed = np.convolve(arr, kernel, mode='same')
    for i in range(w // 2):
        smoothed[i] = np.mean(arr[:i + w // 2 + 1])
        smoothed[-(i + 1)] = np.mean(arr[-(i + w // 2 + 1):])
    return smoothed

v_smooth = sma(v, window)
c_smooth = sma(c, window)

print(f"Plotting {len(h)} points with SMA window={window}")

# ---------------------------------------------------------------------------
# Colors matched to reference image
# ---------------------------------------------------------------------------
COLOR_CURRENT  = '#1B7A8A'  # teal blue (matches reference)
COLOR_VOLTAGE  = '#D4772C'  # burnt orange (matches reference)
COLOR_TEXT     = '#000000'
COLOR_BORDER   = '#000000'

# ---------------------------------------------------------------------------
# Figure setup
# ---------------------------------------------------------------------------
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.weight': 'bold',
    'axes.titleweight': 'bold',
    'axes.labelweight': 'bold',
    'mathtext.default': 'regular',
})

fig, ax1 = plt.subplots(figsize=(10, 5.25))
fig.patch.set_facecolor('#FFFFFF')
ax1.set_facecolor('#FFFFFF')

# ---------------------------------------------------------------------------
# Current (left y-axis) — teal, plotted first so it layers behind voltage
# ---------------------------------------------------------------------------
ax1.plot(h, c_smooth, color=COLOR_CURRENT, linewidth=1.8, alpha=0.9,
         label='Current vs. Time', zorder=3)
ax1.fill_between(h, c_smooth, alpha=0.08, color=COLOR_CURRENT, zorder=2)

ax1.set_xlabel('Time Elapsed, t (hours)', fontsize=18, fontweight='bold',
               labelpad=12, color=COLOR_TEXT)
ax1.set_ylabel('Current, I (A)', fontsize=18, fontweight='bold',
               labelpad=12, color=COLOR_TEXT)
ax1.tick_params(axis='y', labelcolor=COLOR_TEXT, labelsize=16, width=1.2, length=5,
                direction='out')
ax1.tick_params(axis='x', labelcolor=COLOR_TEXT, labelsize=16, width=1.2, length=5,
                direction='out')
for label in ax1.get_yticklabels() + ax1.get_xticklabels():
    label.set_fontweight('bold')
ax1.set_xlim(0, 100)
ax1.set_ylim(0, max(c_smooth) * 1.12)
ax1.xaxis.set_major_locator(mticker.MultipleLocator(20))
ax1.yaxis.set_major_locator(mticker.MaxNLocator(nbins=7))
ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

# No gridlines (matches reference)
ax1.grid(False)

# Bold black spines (matches reference thick border)
for spine in ax1.spines.values():
    spine.set_color(COLOR_BORDER)
    spine.set_linewidth(2.0)

# ---------------------------------------------------------------------------
# Voltage (right y-axis) — orange
# ---------------------------------------------------------------------------
ax2 = ax1.twinx()
ax2.plot(h, v_smooth, color=COLOR_VOLTAGE, linewidth=1.8, alpha=0.9,
         label='Potential vs. Time', zorder=3)
ax2.fill_between(h, v_smooth, alpha=0.06, color=COLOR_VOLTAGE, zorder=2)

ax2.set_ylabel('Cell Potential, E (V)', fontsize=18, fontweight='bold',
               labelpad=12, color=COLOR_TEXT)
ax2.tick_params(axis='y', labelcolor=COLOR_TEXT, labelsize=16, width=1.2, length=5,
                direction='out')
for label in ax2.get_yticklabels():
    label.set_fontweight('bold')
ax2.set_ylim(0, max(v_smooth) * 1.12)
ax2.yaxis.set_major_locator(mticker.MaxNLocator(nbins=7))
ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

for spine in ax2.spines.values():
    spine.set_color(COLOR_BORDER)
    spine.set_linewidth(2.0)

# ---------------------------------------------------------------------------
# Title — multi-line, matching reference
# ---------------------------------------------------------------------------
ax1.set_title('Current, I (A) & Cell Potential, E (V)\nvs. Time Elapsed, t (hours)',
              fontsize=20, fontweight='bold', color=COLOR_TEXT, pad=16)

# ---------------------------------------------------------------------------
# Legend — inside the plot, lower-left, matching reference
# ---------------------------------------------------------------------------
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
legend = ax1.legend(
    lines1 + lines2, labels1 + labels2,
    loc='lower left',
    bbox_to_anchor=(0.03, 0.03),
    ncol=1,
    fontsize=16,
    frameon=True,
    framealpha=1.0,
    edgecolor=COLOR_BORDER,
    fancybox=False,
    shadow=False,
    borderpad=0.8,
    handlelength=2.0,
    handletextpad=0.6,
    labelspacing=0.5,
)
legend.get_frame().set_linewidth(1.5)
legend.get_frame().set_facecolor('#FFFFFF')

# ---------------------------------------------------------------------------
# Outer border — thick black rectangle around entire figure (matches reference)
# ---------------------------------------------------------------------------
fig.patches.append(FancyBboxPatch(
    (0.005, 0.005), 0.99, 0.99,
    boxstyle='square,pad=0',
    linewidth=3.5,
    edgecolor=COLOR_BORDER,
    facecolor='none',
    transform=fig.transFigure,
    clip_on=False,
    zorder=10,
))

# ---------------------------------------------------------------------------
# Layout & save
# ---------------------------------------------------------------------------
fig.tight_layout()
fig.subplots_adjust(top=0.84, bottom=0.16, left=0.13, right=0.87)

fig.savefig('voltage_current_chart.png', dpi=200,
            facecolor='#FFFFFF', pad_inches=0.35)
fig.savefig('voltage_current_chart.jpg', dpi=200,
            format='jpeg', facecolor='#FFFFFF', pad_inches=0.35,
            pil_kwargs={'quality': 95})
print("Saved voltage_current_chart.png and .jpg")
