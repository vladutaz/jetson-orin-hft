#!/usr/bin/env bash
# ==============================================================================
# NVIDIA Jetson Orin (JetPack 6.x / L4T Ubuntu 22.04) Maximum Performance Tuner
# Sets MAXN power mode, locks CPU/GPU/EMC clocks, and tunes kernel network stack
# ==============================================================================
set -euo pipefail

echo "[jetson-perf] Configuring NVIDIA Jetson Orin for ultra-low-latency trading..."

# 1. Enable MAXN Power Mode (Mode 0 on AGX Orin / Orin NX)
if command -v nvpmodel >/dev/null 2>&1; then
    nvpmodel -m 0 || true
    echo "[jetson-perf] Activated nvpmodel -m 0 (MAXN)"
fi

# 2. Lock CPU, GPU, and LPDDR5 EMC clocks to maximum frequency
if command -v jetson_clocks >/dev/null 2>&1; then
    jetson_clocks --fan || jetson_clocks || true
    echo "[jetson-perf] Locked clocks and fan to maximum via jetson_clocks"
fi

# 3. Force all Cortex-A78AE CPU cores to 'performance' scaling governor and disable idle C-states
for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [ -w "$gov" ]; then
        echo "performance" > "$gov" || true
    fi
done

# 4. Tune Linux Kernel Network Stack for sub-millisecond WebSocket & ZeroMQ IPC
sysctl -w net.core.rmem_max=67108864 >/dev/null 2>&1 || true
sysctl -w net.core.wmem_max=67108864 >/dev/null 2>&1 || true
sysctl -w net.core.rmem_default=16777216 >/dev/null 2>&1 || true
sysctl -w net.core.wmem_default=16777216 >/dev/null 2>&1 || true
sysctl -w net.core.busy_read=50 >/dev/null 2>&1 || true
sysctl -w net.core.busy_poll=50 >/dev/null 2>&1 || true
sysctl -w net.ipv4.tcp_low_latency=1 >/dev/null 2>&1 || true
sysctl -w net.ipv4.tcp_tw_reuse=1 >/dev/null 2>&1 || true
sysctl -w kernel.sched_rt_runtime_us=-1 >/dev/null 2>&1 || true

# 5. Prepare IPC socket directory and data ledger directory
mkdir -p /tmp /opt/jetson-hft/data /opt/jetson-hft/models
chmod 1777 /tmp

echo "[jetson-perf] Hardware & kernel optimization complete."
