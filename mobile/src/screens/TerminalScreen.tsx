import React from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { CandlestickChart } from '../components/CandlestickChart';
import { OrderBookLadder } from '../components/OrderBookLadder';
import { useTrading } from '../context/TradingContext';

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];

export const TerminalScreen: React.FC = () => {
  const { telemetry, selectedSymbol, setSelectedSymbol } = useTrading();
  const signal = telemetry.signals[selectedSymbol];
  const book = telemetry.orderbooks[selectedSymbol] || telemetry.orderbooks['BTCUSDT'];
  const candles = telemetry.candles[selectedSymbol] || telemetry.candles['BTCUSDT'] || [];

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {/* Instrument Selector Tabs */}
      <View style={styles.symbolBar}>
        {SYMBOLS.map((sym) => {
          const active = sym === selectedSymbol;
          return (
            <TouchableOpacity
              key={sym}
              style={[styles.symbolTab, active && styles.symbolTabActive]}
              onPress={() => setSelectedSymbol(sym)}
            >
              <Text style={[styles.symbolTabText, active && styles.symbolTabTextActive]}>{sym}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Live Candlestick Chart */}
      <CandlestickChart
        symbol={selectedSymbol}
        candles={candles}
        microPrice={signal?.micro_price}
      />

      {/* TensorRT Alpha Signal & Microstructure Readout */}
      {signal && (
        <View style={styles.signalCard}>
          <View style={styles.signalHeader}>
            <Text style={styles.cardTitle}>TENSORRT FP16 ALPHA & MICROSTRUCTURE</Text>
            <Text style={styles.latencyBadge}>TRT: {signal.trt_inference_us.toFixed(1)} µs</Text>
          </View>

          <View style={styles.signalGrid}>
            <View style={styles.sigBox}>
              <Text style={styles.sigLabel}>TARGET POS</Text>
              <Text
                style={[
                  styles.sigValue,
                  { color: signal.position_target >= 0 ? '#00E676' : '#FF5252' },
                ]}
              >
                {signal.position_target >= 0 ? '+' : ''}
                {signal.position_target.toFixed(2)}
              </Text>
            </View>

            <View style={styles.sigBox}>
              <Text style={styles.sigLabel}>CONFIDENCE</Text>
              <Text style={styles.sigValue}>{(signal.confidence * 100).toFixed(1)}%</Text>
            </View>

            <View style={styles.sigBox}>
              <Text style={styles.sigLabel}>OFI (L1-L5)</Text>
              <Text
                style={[
                  styles.sigValue,
                  { color: signal.ofi >= 0 ? '#00E676' : '#FF5252' },
                ]}
              >
                {signal.ofi.toFixed(2)}
              </Text>
            </View>

            <View style={styles.sigBox}>
              <Text style={styles.sigLabel}>VPIN TOXICITY</Text>
              <Text
                style={[
                  styles.sigValue,
                  { color: signal.vpin > 0.6 ? '#FF5252' : '#38BDF8' },
                ]}
              >
                {signal.vpin.toFixed(3)}
              </Text>
            </View>

            <View style={styles.sigBox}>
              <Text style={styles.sigLabel}>DEPTH SKEW</Text>
              <Text style={styles.sigValue}>{signal.depth_skew.toFixed(3)}</Text>
            </View>

            <View style={styles.sigBox}>
              <Text style={styles.sigLabel}>FINBERT SENTIMENT</Text>
              <Text
                style={[
                  styles.sigValue,
                  { color: signal.sentiment_score >= 0 ? '#00E676' : '#FF5252' },
                ]}
              >
                {signal.sentiment_score >= 0 ? '+' : ''}
                {signal.sentiment_score.toFixed(2)}
              </Text>
            </View>
          </View>
        </View>
      )}

      {/* L2 Order Book Depth Ladder */}
      <OrderBookLadder book={book} />
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
  symbolBar: {
    flexDirection: 'row',
    marginBottom: 12,
    backgroundColor: '#0E141F',
    borderRadius: 10,
    padding: 4,
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  symbolTab: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 7,
  },
  symbolTabActive: {
    backgroundColor: '#1E293B',
  },
  symbolTabText: {
    color: '#64748B',
    fontSize: 12,
    fontWeight: '700',
  },
  symbolTabTextActive: {
    color: '#38BDF8',
  },
  signalCard: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: '#1E293B',
    marginBottom: 14,
  },
  signalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  cardTitle: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '700',
  },
  latencyBadge: {
    color: '#00E676',
    fontSize: 11,
    fontWeight: '700',
    backgroundColor: 'rgba(0, 230, 118, 0.12)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  signalGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  sigBox: {
    width: '31.5%',
    backgroundColor: '#090D16',
    borderRadius: 8,
    padding: 8,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#162032',
  },
  sigLabel: {
    color: '#64748B',
    fontSize: 9,
    fontWeight: '700',
  },
  sigValue: {
    color: '#F8FAFC',
    fontSize: 14,
    fontWeight: '800',
    marginTop: 4,
  },
});
