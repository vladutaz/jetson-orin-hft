import React, { useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useTrading } from '../context/TradingContext';

export const OrdersScreen: React.FC = () => {
  const { telemetry, selectedSymbol, submitManualOrder, cancelOrder } = useTrading();
  const [tab, setTab] = useState<'ACTIVE' | 'FILLS'>('ACTIVE');
  const [qtyInput, setQtyInput] = useState<string>('0.10');
  const [orderType, setOrderType] = useState<'LIMIT_POST_ONLY' | 'MARKET'>('LIMIT_POST_ONLY');

  const handleManualDispatch = (side: 'BUY' | 'SELL') => {
    const parsed = parseFloat(qtyInput);
    if (!isNaN(parsed) && parsed > 0) {
      submitManualOrder(selectedSymbol, side, parsed, orderType);
    }
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {/* Discretionary Manual Order Override Panel */}
      <View style={styles.overrideCard}>
        <Text style={styles.sectionTitle}>DISCRETIONARY MANUAL ORDER OVERRIDE ({selectedSymbol})</Text>

        <View style={styles.formRow}>
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>QUANTITY</Text>
            <TextInput
              style={styles.textInput}
              value={qtyInput}
              onChangeText={setQtyInput}
              keyboardType="decimal-pad"
              placeholderTextColor="#475569"
            />
          </View>

          <View style={styles.typeGroup}>
            <Text style={styles.inputLabel}>EXECUTION MODE</Text>
            <View style={styles.typeButtons}>
              <TouchableOpacity
                style={[
                  styles.typeBtn,
                  orderType === 'LIMIT_POST_ONLY' && styles.typeBtnSelected,
                ]}
                onPress={() => setOrderType('LIMIT_POST_ONLY')}
              >
                <Text style={styles.typeBtnText}>SOR POST-ONLY</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.typeBtn, orderType === 'MARKET' && styles.typeBtnSelected]}
                onPress={() => setOrderType('MARKET')}
              >
                <Text style={styles.typeBtnText}>MARKET</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>

        <View style={styles.actionRow}>
          <TouchableOpacity
            style={[styles.orderBtn, styles.buyBtn]}
            onPress={() => handleManualDispatch('BUY')}
          >
            <Text style={styles.orderBtnText}>MANUAL BUY {selectedSymbol}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.orderBtn, styles.sellBtn]}
            onPress={() => handleManualDispatch('SELL')}
          >
            <Text style={styles.orderBtnText}>MANUAL SELL {selectedSymbol}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Tab Switcher: Active Orders vs Recent Fills & Latency Log */}
      <View style={styles.tabHeader}>
        <TouchableOpacity
          style={[styles.tabButton, tab === 'ACTIVE' && styles.tabButtonActive]}
          onPress={() => setTab('ACTIVE')}
        >
          <Text style={[styles.tabText, tab === 'ACTIVE' && styles.tabTextActive]}>
            ACTIVE ORDERS ({telemetry.active_orders.length})
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tabButton, tab === 'FILLS' && styles.tabButtonActive]}
          onPress={() => setTab('FILLS')}
        >
          <Text style={[styles.tabText, tab === 'FILLS' && styles.tabTextActive]}>
            RECENT FILLS & LATENCY ({telemetry.recent_fills.length})
          </Text>
        </TouchableOpacity>
      </View>

      {tab === 'ACTIVE' ? (
        <View style={styles.listCard}>
          {telemetry.active_orders.length === 0 ? (
            <Text style={styles.emptyText}>No open resting orders on exchange.</Text>
          ) : (
            telemetry.active_orders.map((ord) => (
              <View key={ord.client_order_id} style={styles.orderRow}>
                <View>
                  <Text style={styles.ordTitle}>
                    <Text style={{ color: ord.side === 'BUY' ? '#00E676' : '#FF5252' }}>
                      {ord.side}
                    </Text>{' '}
                    {ord.symbol} · {ord.order_type}
                  </Text>
                  <Text style={styles.ordSub}>
                    Px: ${ord.price.toFixed(2)} · Filled: {ord.filled_quantity}/{ord.quantity} · State: {ord.state}
                  </Text>
                  <Text style={styles.latencyText}>
                    Ed25519 Ack Latency: {ord.latency_us.toFixed(1)} µs · ID: {ord.client_order_id}
                  </Text>
                </View>

                <TouchableOpacity
                  style={styles.cancelBtn}
                  onPress={() => cancelOrder(ord.client_order_id)}
                >
                  <Text style={styles.cancelBtnText}>CANCEL</Text>
                </TouchableOpacity>
              </View>
            ))
          )}
        </View>
      ) : (
        <View style={styles.listCard}>
          {telemetry.recent_fills.map((fill) => (
            <View key={fill.fill_id} style={styles.orderRow}>
              <View>
                <Text style={styles.ordTitle}>
                  <Text style={{ color: fill.side === 'BUY' ? '#00E676' : '#FF5252' }}>
                    {fill.side}
                  </Text>{' '}
                  {fill.symbol} · {fill.fill_qty} @ ${fill.fill_price.toFixed(2)}
                </Text>
                <Text style={styles.ordSub}>
                  Slippage: {fill.slippage_bps.toFixed(2)} bps · Fee: ${fill.fee_usd.toFixed(2)} · Wire: {fill.latency_us.toFixed(1)} µs
                </Text>
              </View>
              <Text
                style={[
                  styles.fillPnl,
                  { color: fill.realized_pnl_usd >= 0 ? '#00E676' : '#FF5252' },
                ]}
              >
                {fill.realized_pnl_usd >= 0 ? '+' : ''}${fill.realized_pnl_usd.toFixed(2)}
              </Text>
            </View>
          ))}
        </View>
      )}
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
  overrideCard: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#1E293B',
    marginBottom: 14,
  },
  sectionTitle: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.7,
    marginBottom: 12,
  },
  formRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  inputGroup: {
    width: '38%',
  },
  typeGroup: {
    width: '58%',
  },
  inputLabel: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '700',
    marginBottom: 6,
  },
  textInput: {
    backgroundColor: '#090D16',
    color: '#F8FAFC',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 14,
    fontWeight: '700',
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  typeButtons: {
    flexDirection: 'row',
    backgroundColor: '#090D16',
    borderRadius: 8,
    padding: 3,
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  typeBtn: {
    flex: 1,
    paddingVertical: 7,
    alignItems: 'center',
    borderRadius: 6,
  },
  typeBtnSelected: {
    backgroundColor: '#1E293B',
  },
  typeBtnText: {
    color: '#CBD5E1',
    fontSize: 10,
    fontWeight: '700',
  },
  actionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  orderBtn: {
    width: '48.5%',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  buyBtn: {
    backgroundColor: '#00C853',
  },
  sellBtn: {
    backgroundColor: '#D50000',
  },
  orderBtnText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '800',
  },
  tabHeader: {
    flexDirection: 'row',
    backgroundColor: '#0E141F',
    borderRadius: 10,
    padding: 4,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  tabButton: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 7,
  },
  tabButtonActive: {
    backgroundColor: '#1E293B',
  },
  tabText: {
    color: '#64748B',
    fontSize: 11,
    fontWeight: '700',
  },
  tabTextActive: {
    color: '#F8FAFC',
  },
  listCard: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  orderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#162032',
  },
  ordTitle: {
    color: '#F8FAFC',
    fontSize: 13,
    fontWeight: '700',
  },
  ordSub: {
    color: '#94A3B8',
    fontSize: 11,
    marginTop: 2,
  },
  latencyText: {
    color: '#38BDF8',
    fontSize: 10,
    marginTop: 2,
  },
  cancelBtn: {
    backgroundColor: 'rgba(255, 82, 82, 0.16)',
    borderWidth: 1,
    borderColor: '#FF5252',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  cancelBtnText: {
    color: '#FF5252',
    fontSize: 10,
    fontWeight: '800',
  },
  fillPnl: {
    fontSize: 13,
    fontWeight: '800',
  },
  emptyText: {
    color: '#64748B',
    fontSize: 12,
    textAlign: 'center',
    paddingVertical: 20,
  },
});
