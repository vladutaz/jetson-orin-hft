import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { JetsonHardwareTelemetry } from '../types/telemetry';

interface Props {
  hardware: JetsonHardwareTelemetry;
  connected: boolean;
  endpoint: string;
}

export const HardwareHud: React.FC<Props> = ({ hardware, connected, endpoint }) => {
  const memPct =
    hardware.mem_total_gb > 0
      ? Math.min(100, (hardware.mem_used_gb / hardware.mem_total_gb) * 100)
      : 0;
  const tempWarn = hardware.gpu_temp_c >= 75.0;

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <View style={styles.titleGroup}>
          <View style={[styles.statusDot, { backgroundColor: connected ? '#00E676' : '#FFB300' }]} />
          <Text style={styles.title}>NVIDIA JETSON ORIN AGX TELEMETRY HUD</Text>
        </View>
        <Text style={styles.modeBadge}>{hardware.power_mode}</Text>
      </View>

      <Text style={styles.endpointText} numberOfLines={1}>
        P2P Link: {endpoint}
      </Text>

      <View style={styles.metricsGrid}>
        <View style={styles.metricCell}>
          <Text style={styles.metricLabel}>GPU TEMP</Text>
          <Text style={[styles.metricValue, tempWarn && styles.warnText]}>
            {hardware.gpu_temp_c.toFixed(1)}°C
          </Text>
          <View style={styles.barTrack}>
            <View
              style={[
                styles.barFill,
                {
                  width: `${Math.min(100, hardware.gpu_temp_c)}%`,
                  backgroundColor: tempWarn ? '#FF5252' : '#00E676',
                },
              ]}
            />
          </View>
        </View>

        <View style={styles.metricCell}>
          <Text style={styles.metricLabel}>CPU LOAD (12C)</Text>
          <Text style={styles.metricValue}>{hardware.cpu_load_pct.toFixed(1)}%</Text>
          <View style={styles.barTrack}>
            <View
              style={[
                styles.barFill,
                { width: `${Math.min(100, hardware.cpu_load_pct)}%`, backgroundColor: '#29B6F6' },
              ]}
            />
          </View>
        </View>

        <View style={styles.metricCell}>
          <Text style={styles.metricLabel}>UNIFIED RAM</Text>
          <Text style={styles.metricValue}>
            {hardware.mem_used_gb.toFixed(1)}/{hardware.mem_total_gb.toFixed(0)} GB
          </Text>
          <View style={styles.barTrack}>
            <View style={[styles.barFill, { width: `${memPct}%`, backgroundColor: '#AB47BC' }]} />
          </View>
        </View>

        <View style={styles.metricCell}>
          <Text style={styles.metricLabel}>POWER DRAW</Text>
          <Text style={styles.metricValue}>{hardware.power_watts.toFixed(1)} W</Text>
          <Text style={styles.subMetric}>PING: {hardware.network_ping_ms.toFixed(1)} ms</Text>
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#1E293B',
    marginBottom: 14,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  titleGroup: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  title: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  modeBadge: {
    color: '#38BDF8',
    fontSize: 10,
    fontWeight: '700',
    backgroundColor: '#0C2D48',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  endpointText: {
    color: '#64748B',
    fontSize: 10,
    marginBottom: 10,
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  metricCell: {
    width: '48%',
    backgroundColor: '#090D16',
    padding: 10,
    borderRadius: 8,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#162032',
  },
  metricLabel: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '600',
    marginBottom: 4,
  },
  metricValue: {
    color: '#F8FAFC',
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 6,
  },
  warnText: {
    color: '#FF5252',
  },
  subMetric: {
    color: '#00E676',
    fontSize: 11,
    fontWeight: '600',
  },
  barTrack: {
    height: 4,
    backgroundColor: '#1E293B',
    borderRadius: 2,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 2,
  },
});
