#!/usr/bin/env bash
# ==============================================================================
# Automated Process, Shared Memory & Network Recovery Supervisor for Jetson Orin
# Run via systemd timer or cron every 10 seconds to guarantee 99.999% uptime
# ==============================================================================
set -euo pipefail

SERVICES=("jetson-ingest.service" "jetson-engine.service" "jetson-bridge.service")
IPC_SOCKETS=("/tmp/jetson_market.ipc" "/tmp/jetson_signals.ipc" "/tmp/jetson_execution.ipc" "/tmp/jetson_telemetry.ipc")

log_msg() {
    echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [jetson-recovery] $1"
}

# 1. Verify and restart any crashed or inactive systemd daemons
for svc in "${SERVICES[@]}"; do
    if ! systemctl is-active --quiet "$svc"; then
        log_msg "CRITICAL: Service $svc is not active. Triggering immediate restart..."
        systemctl restart "$svc"
    fi
done

# 2. Verify ZeroMQ IPC Unix domain sockets exist when services are running
for sock in "${IPC_SOCKETS[@]}"; do
    if [ ! -S "$sock" ]; then
        log_msg "WARNING: Missing IPC socket $sock. Restarting pipeline..."
        systemctl restart jetson-ingest.service jetson-engine.service jetson-bridge.service
        break
    fi
done

# 3. Verify POSIX Shared Memory ring buffer (/dev/shm/jetson_l2_ring) freshness
if [ -f "/dev/shm/jetson_l2_ring" ]; then
    SHM_AGE=$(( $(date +%s) - $(stat -c %Y "/dev/shm/jetson_l2_ring" 2>/dev/null || echo "$(date +%s)") ))
    if [ "$SHM_AGE" -gt 30 ]; then
        log_msg "WARNING: Shared memory /dev/shm/jetson_l2_ring stale (${SHM_AGE}s). Restarting jetson-ingest..."
        systemctl restart jetson-ingest.service
    fi
fi

# 4. Verify network connectivity & WireGuard/Tailscale tunnel health
if ! ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1; then
    log_msg "WARNING: Upstream WAN connectivity degraded; cycling network interface..."
    nmcli networking off && sleep 1 && nmcli networking on || true
fi

if command -v tailscale >/dev/null 2>&1; then
    if ! tailscale status >/dev/null 2>&1; then
        log_msg "Reconnecting Tailscale P2P mesh daemon..."
        systemctl restart tailscaled.service || true
    fi
fi
