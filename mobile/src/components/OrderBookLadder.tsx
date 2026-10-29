import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { OrderBookSnapshot } from '../types/telemetry';

interface Props {
  book?: OrderBookSnapshot;
}

export const OrderBookLadder: React.FC<Props> = ({ book }) => {
  if (!book) {
    return (
      <View style={styles.container}>
        <Text style={styles.emptyText}>Synchronizing L2 Order Book Snapshot...</Text>
      </View>
    );
  }

  const bids = book.bids.slice(0, 8);
  const asks = book.asks.slice(0, 8);
  const maxQty = Math.max(
    1e-6,
    ...bids.map((b) => b[1]),
    ...asks.map((a) => a[1])
  );

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.headerTitle}>L2 ORDER BOOK DEPTH LADDER (SEQ #{book.sequence_id})</Text>
        <Text
          style={[
            styles.lastTradeText,
            { color: book.last_trade_side === 'BUY' ? '#00E676' : '#FF5252' },
          ]}
        >
          LAST: {book.last_trade_px.toFixed(2)} ({book.last_trade_qty.toFixed(3)} {book.last_trade_side})
        </Text>
      </View>

      <View style={styles.columnHeaders}>
        <Text style={styles.colLabel}>BID QTY</Text>
        <Text style={styles.colLabel}>BID PX</Text>
        <Text style={styles.colLabel}>ASK PX</Text>
        <Text style={styles.colLabel}>ASK QTY</Text>
      </View>

      {Array.from({ length: Math.max(bids.length, asks.length) }, (_, idx) => {
        const bid = bids[idx];
        const ask = asks[idx];
        const bidWidthPct = bid ? Math.min(100, (bid[1] / maxQty) * 100) : 0;
        const askWidthPct = ask ? Math.min(100, (ask[1] / maxQty) * 100) : 0;

        return (
          <View key={idx} style={styles.levelRow}>
            {/* Bid Side */}
            <View style={styles.sideCell}>
              <View style={[styles.bidDepthBar, { width: `${bidWidthPct}%` }]} />
              <Text style={styles.qtyText}>{bid ? bid[1].toFixed(3) : '-'}</Text>
              <Text style={styles.bidPriceText}>{bid ? bid[0].toFixed(2) : '-'}</Text>
            </View>

            {/* Ask Side */}
            <View style={styles.sideCell}>
              <View style={[styles.askDepthBar, { width: `${askWidthPct}%` }]} />
              <Text style={styles.askPriceText}>{ask ? ask[0].toFixed(2) : '-'}</Text>
              <Text style={styles.qtyText}>{ask ? ask[1].toFixed(3) : '-'}</Text>
            </View>
          </View>
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: '#1E293B',
    marginBottom: 14,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  headerTitle: {
    color: '#94A3B8',
    fontSize: 10,
    fontWeight: '700',
  },
  lastTradeText: {
    fontSize: 11,
    fontWeight: '700',
  },
  columnHeaders: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingBottom: 6,
    borderBottomWidth: 1,
    borderBottomColor: '#1E293B',
    marginBottom: 4,
  },
  colLabel: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '600',
  },
  levelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    height: 22,
    alignItems: 'center',
    marginVertical: 1,
  },
  sideCell: {
    width: '49%',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 6,
    height: '100%',
    position: 'relative',
    overflow: 'hidden',
  },
  bidDepthBar: {
    position: 'absolute',
    right: 0,
    top: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 230, 118, 0.14)',
  },
  askDepthBar: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    backgroundColor: 'rgba(255, 82, 82, 0.14)',
  },
  bidPriceText: {
    color: '#00E676',
    fontSize: 12,
    fontWeight: '700',
  },
  askPriceText: {
    color: '#FF5252',
    fontSize: 12,
    fontWeight: '700',
  },
  qtyText: {
    color: '#CBD5E1',
    fontSize: 11,
  },
  emptyText: {
    color: '#64748B',
    fontSize: 12,
    textAlign: 'center',
    paddingVertical: 20,
  },
});
