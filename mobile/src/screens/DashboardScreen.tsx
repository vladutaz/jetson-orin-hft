import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { HardwareHud } from '../components/HardwareHud';
import { useTrading } from '../context/TradingContext';

export const DashboardScreen: React.FC = () => {
  const { telemetry, connected, endpoint } = useTrading();
  const totalPnl = telemetry.realized_pnl_usd + telemetry.unrealized_pnl_usd;
  const isPositive = totalPnl >= 0;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {/* Executive Net Equity & State Banner */}
      <View style={styles.heroCard}>
        <View style={styles.heroTopRow}>
          <Text style={styles.heroLabel}>LIVE NET ACCOUNT EQUITY</Text>
          <View
            style={[
              styles.stateBadge,
              telemetry.engine_state === 'ACTIVE'
                ? styles.badgeActive
                : styles.badgeHalted,
            ]}
          >
            <Text style={styles.stateBadgeText}>{telemetry.engine_state}</Text>
          </View>
        </View>

        <Text style={styles.equityValue}>
          ${telemetry.equity_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </Text>

        <View style={styles.pnlRow}>
          <View style={styles.pnlBlock}>
            <Text style={styles.subLabel}>REALIZED PNL</Text>
            <Text
              style={[
                styles.pnlValue,
                { color: telemetry.realized_pnl_usd >= 0 ? '#00E676' : '#FF5252' },
              ]}
            >
              {telemetry.realized_pnl_usd >= 0 ? '+' : ''}${telemetry.realized_pnl_usd.toFixed(2)}
            </Text>
          </View>

          <View style={styles.pnlBlock}>
            <Text style={styles.subLabel}>UNREALIZED PNL</Text>
            <Text
              style={[
                styles.pnlValue,
                { color: telemetry.unrealized_pnl_usd >= 0 ? '#00E676' : '#FF5252' },
              ]}
            >
              {telemetry.unrealized_pnl_usd >= 0 ? '+' : ''}${telemetry.unrealized_pnl_usd.toFixed(2)}
            </Text>
          </View>

          <View style={styles.pnlBlock}>
            <Text style={styles.subLabel}>NET SESSION</Text>
            <Text style={[styles.pnlValue, { color: isPositive ? '#00E676' : '#FF5252' }]}>
              {isPositive ? '+' : ''}${totalPnl.toFixed(2)}
            </Text>
          </View>
        </View>
      </View>

      {/* Institutional Risk & Performance KPI Grid */}
      <View style={styles.kpiGrid}>
        <View style={styles.kpiCard}>
          <Text style={styles.kpiLabel}>DAILY SHARPE</Text>
          <Text style={styles.kpiVal}>{telemetry.daily_sharpe.toFixed(2)}</Text>
        </View>
        <View style={styles.kpiCard}>
          <Text style={styles.kpiLabel}>WIN RATE</Text>
          <Text style={styles.kpiVal}>{telemetry.win_rate_pct.toFixed(1)}%</Text>
        </View>
        <View style={styles.kpiCard}>
          <Text style={styles.kpiLabel}>MARGIN UTIL</Text>
          <Text style={styles.kpiVal}>{telemetry.margin_utilization_pct.toFixed(1)}%</Text>
        </View>
        <View style={styles.kpiCard}>
          <Text style={styles.kpiLabel}>DRAWDOWN (MAX 3%)</Text>
          <Text
            style={[
              styles.kpiVal,
              telemetry.daily_drawdown_pct >= 2.0 ? { color: '#FF5252' } : { color: '#00E676' },
            ]}
          >
            {telemetry.daily_drawdown_pct.toFixed(2)}%
          </Text>
        </View>
      </View>

      {/* Jetson Hardware Telemetry HUD */}
      <HardwareHud hardware={telemetry.hardware} connected={connected} endpoint={endpoint} />

      {/* Open Portfolio Positions */}
      <View style={styles.sectionCard}>
        <Text style={styles.sectionTitle}>ACTIVE PERPETUAL POSITIONS</Text>
        {Object.values(telemetry.positions).map((pos) => {
          const isLong = pos.quantity > 0;
          const isFlat = Math.abs(pos.quantity) < 1e-8;
          return (
            <View key={pos.symbol} style={styles.posRow}>
              <View>
                <Text style={styles.posSymbol}>{pos.symbol}</Text>
                <Text style={styles.posMeta}>
                  {isFlat ? 'FLAT' : isLong ? 'LONG' : 'SHORT'} · Qty: {pos.quantity} @ ${pos.avg_entry_price.toFixed(2)}
                </Text>
              </View>
              <View style={styles.posRight}>
                <Text style={styles.posNotional}>${pos.notional_usd.toLocaleString()}</Text>
                <Text
                  style={[
                    styles.posPnl,
                    { color: pos.unrealized_pnl_usd >= 0 ? '#00E676' : '#FF5252' },
                  ]}
                >
                  {pos.unrealized_pnl_usd >= 0 ? '+' : ''}${pos.unrealized_pnl_usd.toFixed(2)}
                </Text>
              </View>
            </View>
          );
        })}
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#070A0F',
  },
  content: {
    padding: 14,
    paddingBottom: 32,
  },
  heroCard: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#1E293B',
    marginBottom: 12,
  },
  heroTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  heroLabel: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  stateBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  badgeActive: {
    backgroundColor: 'rgba(0, 230, 118, 0.16)',
  },
  badgeHalted: {
    backgroundColor: 'rgba(255, 82, 82, 0.24)',
  },
  stateBadgeText: {
    color: '#F8FAFC',
    fontSize: 10,
    fontWeight: '800',
  },
  equityValue: {
    color: '#F8FAFC',
    fontSize: 32,
    fontWeight: '800',
    marginVertical: 10,
  },
  pnlRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: '#1E293B',
    paddingTop: 10,
  },
  pnlBlock: {
    flex: 1,
  },
  subLabel: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '600',
  },
  pnlValue: {
    fontSize: 14,
    fontWeight: '700',
    marginTop: 2,
  },
  kpiGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  kpiCard: {
    width: '48.5%',
    backgroundColor: '#0E141F',
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  kpiLabel: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '700',
  },
  kpiVal: {
    color: '#F8FAFC',
    fontSize: 18,
    fontWeight: '800',
    marginTop: 4,
  },
  sectionCard: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  sectionTitle: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.8,
    marginBottom: 10,
  },
  posRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: '#162032',
  },
  posSymbol: {
    color: '#F8FAFC',
    fontSize: 14,
    fontWeight: '700',
  },
  posMeta: {
    color: '#64748B',
    fontSize: 11,
    marginTop: 2,
  },
  posRight: {
    alignItems: 'flex-end',
  },
  posNotional: {
    color: '#E2E8F0',
    fontSize: 13,
    fontWeight: '700',
  },
  posPnl: {
    fontSize: 12,
    fontWeight: '700',
    marginTop: 2,
  },
});
