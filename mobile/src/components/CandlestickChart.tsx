import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Line, Rect } from 'react-native-svg';
import { CandleBar } from '../types/telemetry';

interface Props {
  symbol: string;
  candles: CandleBar[];
  microPrice?: number;
}

/**
 * High-FPS Vector Candlestick & Micro-Price Chart compatible with TradingView OHLCV series.
 */
export const CandlestickChart: React.FC<Props> = ({ symbol, candles, microPrice }) => {
  const visible = candles.slice(-28);
  if (visible.length === 0) {
    return (
      <View style={styles.container}>
        <Text style={styles.emptyText}>Awaiting L2 candlestick aggregation for {symbol}...</Text>
      </View>
    );
  }

  const minLow = Math.min(...visible.map((c) => c.low));
  const maxHigh = Math.max(...visible.map((c) => c.high));
  const range = Math.max(1e-6, maxHigh - minLow);
  const width = 340;
  const height = 165;
  const stepX = width / visible.length;
  const candleWidth = Math.max(4, stepX * 0.62);

  const priceToY = (px: number): number => {
    return height - 12 - ((px - minLow) / range) * (height - 24);
  };

  const lastBar = visible[visible.length - 1];
  const isBull = lastBar.close >= lastBar.open;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View>
          <Text style={styles.symbolTitle}>{symbol} PERP · 1M OHLCV</Text>
          <Text style={styles.subTitle}>
            O: {lastBar.open.toFixed(2)}  H: {lastBar.high.toFixed(2)}  L: {lastBar.low.toFixed(2)}  C:{' '}
            {lastBar.close.toFixed(2)}
          </Text>
        </View>
        {microPrice !== undefined && (
          <View style={styles.microPriceBadge}>
            <Text style={styles.microPriceLabel}>MICRO-PRICE</Text>
            <Text style={[styles.microPriceValue, { color: isBull ? '#00E676' : '#FF5252' }]}>
              ${microPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </Text>
          </View>
        )}
      </View>

      <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
        {/* Horizontal reference grid lines */}
        {[0.2, 0.5, 0.8].map((ratio, idx) => (
          <Line
            key={idx}
            x1={0}
            y1={height * ratio}
            x2={width}
            y2={height * ratio}
            stroke="#1E293B"
            strokeDasharray="3,3"
            strokeWidth={1}
          />
        ))}

        {visible.map((bar, i) => {
          const cx = i * stepX + stepX / 2;
          const yHigh = priceToY(bar.high);
          const yLow = priceToY(bar.low);
          const yOpen = priceToY(bar.open);
          const yClose = priceToY(bar.close);
          const top = Math.min(yOpen, yClose);
          const bodyHeight = Math.max(2, Math.abs(yClose - yOpen));
          const color = bar.close >= bar.open ? '#00E676' : '#FF5252';

          return (
            <React.Fragment key={bar.time + '-' + i}>
              <Line x1={cx} y1={yHigh} x2={cx} y2={yLow} stroke={color} strokeWidth={1.3} />
              <Rect
                x={cx - candleWidth / 2}
                y={top}
                width={candleWidth}
                height={bodyHeight}
                fill={color}
                rx={1}
              />
            </React.Fragment>
          );
        })}
      </Svg>
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  symbolTitle: {
    color: '#F8FAFC',
    fontSize: 13,
    fontWeight: '700',
  },
  subTitle: {
    color: '#94A3B8',
    fontSize: 10,
    marginTop: 2,
  },
  microPriceBadge: {
    alignItems: 'flex-end',
  },
  microPriceLabel: {
    color: '#64748B',
    fontSize: 9,
    fontWeight: '700',
  },
  microPriceValue: {
    fontSize: 15,
    fontWeight: '800',
  },
  emptyText: {
    color: '#64748B',
    fontSize: 12,
    textAlign: 'center',
    paddingVertical: 30,
  },
});
