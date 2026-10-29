import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { JetsonGatewayClient } from '../services/GatewayClient';
import { MobileTelemetryState } from '../types/telemetry';

const INITIAL_TELEMETRY: MobileTelemetryState = {
  seq: 1,
  ts_ms: Date.now(),
  engine_state: 'ACTIVE',
  equity_usd: 254820.45,
  realized_pnl_usd: 4190.20,
  unrealized_pnl_usd: 630.25,
  daily_drawdown_pct: 0.18,
  daily_sharpe: 3.42,
  win_rate_pct: 64.8,
  margin_utilization_pct: 38.4,
  hardware: {
    gpu_temp_c: 51.2,
    cpu_load_pct: 28.5,
    mem_used_gb: 12.8,
    mem_total_gb: 32.0,
    power_watts: 31.4,
    network_ping_ms: 1.9,
    power_mode: 'MAXN (nvpmodel -m 0)',
    ts_ms: Date.now(),
  },
  positions: {
    BTCUSDT: {
      symbol: 'BTCUSDT',
      quantity: 0.85,
      avg_entry_price: 89420.0,
      mark_price: 89980.0,
      notional_usd: 76483.0,
      unrealized_pnl_usd: 476.0,
      realized_pnl_usd: 2840.5,
    },
    ETHUSDT: {
      symbol: 'ETHUSDT',
      quantity: -6.5,
      avg_entry_price: 3125.0,
      mark_price: 3101.27,
      notional_usd: 20158.25,
      unrealized_pnl_usd: 154.25,
      realized_pnl_usd: 910.2,
    },
    SOLUSDT: {
      symbol: 'SOLUSDT',
      quantity: 0.0,
      avg_entry_price: 0.0,
      mark_price: 194.5,
      notional_usd: 0.0,
      unrealized_pnl_usd: 0.0,
      realized_pnl_usd: 439.5,
    },
  },
  signals: {
    BTCUSDT: {
      symbol: 'BTCUSDT',
      position_target: 0.74,
      confidence: 0.86,
      stop_loss_bps: 18.5,
      predicted_vol_bps: 14.2,
      ofi: 14.82,
      vpin: 0.21,
      micro_price: 89981.4,
      mid_price: 89980.0,
      spread_bps: 0.89,
      depth_skew: 0.34,
      sentiment_score: 0.62,
      trt_inference_us: 142.5,
    },
    ETHUSDT: {
      symbol: 'ETHUSDT',
      position_target: -0.48,
      confidence: 0.72,
      stop_loss_bps: 22.0,
      predicted_vol_bps: 19.4,
      ofi: -8.35,
      vpin: 0.29,
      micro_price: 3100.9,
      mid_price: 3101.25,
      spread_bps: 1.12,
      depth_skew: -0.26,
      sentiment_score: -0.18,
      trt_inference_us: 138.0,
    },
    SOLUSDT: {
      symbol: 'SOLUSDT',
      position_target: 0.19,
      confidence: 0.54,
      stop_loss_bps: 28.0,
      predicted_vol_bps: 26.5,
      ofi: 3.1,
      vpin: 0.33,
      micro_price: 194.54,
      mid_price: 194.5,
      spread_bps: 1.54,
      depth_skew: 0.11,
      sentiment_score: 0.31,
      trt_inference_us: 139.2,
    },
  },
  orderbooks: {
    BTCUSDT: {
      symbol: 'BTCUSDT',
      exchange: 'binance_futures',
      sequence_id: 94827105,
      bids: [
        [89979.6, 1.84],
        [89979.2, 3.12],
        [89978.8, 2.45],
        [89978.0, 5.60],
        [89977.5, 4.18],
        [89976.8, 8.92],
        [89976.0, 6.40],
        [89975.2, 11.25],
      ],
      asks: [
        [89980.4, 0.92],
        [89980.9, 1.65],
        [89981.5, 2.80],
        [89982.0, 4.10],
        [89982.8, 3.75],
        [89983.5, 6.20],
        [89984.2, 7.85],
        [89985.0, 9.50],
      ],
      last_trade_px: 89980.4,
      last_trade_qty: 0.42,
      last_trade_side: 'BUY',
      ts_ms: Date.now(),
    },
  },
  candles: {
    BTCUSDT: Array.from({ length: 32 }, (_, idx) => {
      const base = 89650 + idx * 10;
      const open = base + ((idx % 3) - 1) * 18;
      const close = base + ((idx % 2 === 0 ? 1 : -1) * 24);
      const high = Math.max(open, close) + 19;
      const low = Math.min(open, close) - 16;
      return {
        time: Math.floor(Date.now() / 1000) - (32 - idx) * 60,
        open,
        high,
        low,
        close,
        volume: 18.5 + (idx % 7) * 6.2,
      };
    }),
  },
  active_orders: [
    {
      client_order_id: 'jts-btcusdt-89f2a10c4b',
      exchange_order_id: 'ex-49182041',
      symbol: 'BTCUSDT',
      side: 'BUY',
      order_type: 'LIMIT_POST_ONLY',
      state: 'NEW',
      price: 89979.6,
      quantity: 0.25,
      filled_quantity: 0.0,
      latency_us: 310.4,
    },
    {
      client_order_id: 'jts-ethusdt-31c9e04a12',
      exchange_order_id: 'ex-49182088',
      symbol: 'ETHUSDT',
      side: 'SELL',
      order_type: 'LIMIT_POST_ONLY',
      state: 'PARTIALLY_FILLED',
      price: 3101.6,
      quantity: 4.0,
      filled_quantity: 1.5,
      latency_us: 285.1,
    },
  ],
  recent_fills: [
    {
      fill_id: 1042,
      client_order_id: 'jts-btcusdt-77a1c90821',
      exchange_order_id: 'ex-49181900',
      symbol: 'BTCUSDT',
      side: 'BUY',
      fill_price: 89942.5,
      fill_qty: 0.35,
      fee_usd: 4.72,
      realized_pnl_usd: 148.6,
      slippage_bps: -0.45,
      latency_us: 294.2,
      ts_ns: Date.now() * 1_000_000,
    },
    {
      fill_id: 1041,
      client_order_id: 'jts-ethusdt-61b8d21044',
      exchange_order_id: 'ex-49181712',
      symbol: 'ETHUSDT',
      side: 'SELL',
      fill_price: 3108.4,
      fill_qty: 2.5,
      fee_usd: 1.16,
      realized_pnl_usd: 64.2,
      slippage_bps: -0.32,
      latency_us: 278.9,
      ts_ns: (Date.now() - 42000) * 1_000_000,
    },
  ],
};

interface TradingContextValue {
  telemetry: MobileTelemetryState;
  connected: boolean;
  endpoint: string;
  selectedSymbol: string;
  setSelectedSymbol: (sym: string) => void;
  triggerKillSwitch: (biometricVerified: boolean) => void;
  resumeTrading: () => void;
  submitManualOrder: (
    symbol: string,
    side: 'BUY' | 'SELL',
    quantity: number,
    orderType: 'LIMIT_POST_ONLY' | 'MARKET'
  ) => void;
  cancelOrder: (clientOrderId: string) => void;
}

const TradingContext = createContext<TradingContextValue | undefined>(undefined);

export const TradingProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [telemetry, setTelemetry] = useState<MobileTelemetryState>(INITIAL_TELEMETRY);
  const [connected, setConnected] = useState<boolean>(false);
  const [endpoint, setEndpoint] = useState<string>('wss://100.64.0.10:8443 (Tailscale P2P)');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTCUSDT');

  const client = useMemo(
    () =>
      new JetsonGatewayClient([
        'ws://127.0.0.1:8443',
        'wss://100.64.0.10:8443',
        'wss://jetson-orin.local:8443',
      ]),
    []
  );

  useEffect(() => {
    const unsubscribe = client.subscribe((newState, isConn, ep) => {
      setTelemetry(newState);
      setConnected(isConn);
      setEndpoint(ep);
    });
    client.start();
    return () => {
      unsubscribe();
      client.stop();
    };
  }, [client]);

  const value: TradingContextValue = {
    telemetry,
    connected,
    endpoint,
    selectedSymbol,
    setSelectedSymbol,
    triggerKillSwitch: (biometricVerified: boolean) => {
      client.triggerEmergencyKillSwitch(biometricVerified);
      setTelemetry((prev) => ({
        ...prev,
        engine_state: 'HALTED',
        active_orders: [],
        positions: Object.fromEntries(
          Object.entries(prev.positions).map(([k, v]) => [
            k,
            { ...v, quantity: 0, notional_usd: 0, unrealized_pnl_usd: 0 },
          ])
        ),
      }));
    },
    resumeTrading: () => {
      client.resumeTradingEngine();
      setTelemetry((prev) => ({ ...prev, engine_state: 'ACTIVE' }));
    },
    submitManualOrder: (symbol, side, quantity, orderType) => {
      client.submitManualOrder(symbol, side, quantity, orderType);
      const book = telemetry.orderbooks[symbol];
      const refPx =
        book && book.bids.length > 0 && book.asks.length > 0
          ? side === 'BUY'
            ? book.bids[0][0]
            : book.asks[0][0]
          : 89980.0;
      const newOrder = {
        client_order_id: `man-${symbol.toLowerCase()}-${Date.now().toString(16).slice(-6)}`,
        exchange_order_id: `ex-${Math.floor(Math.random() * 900000 + 100000)}`,
        symbol,
        side,
        order_type: orderType,
        state: orderType === 'MARKET' ? 'FILLED' : 'NEW',
        price: refPx,
        quantity,
        filled_quantity: orderType === 'MARKET' ? quantity : 0,
        latency_us: 265.0,
      };
      setTelemetry((prev) => ({
        ...prev,
        active_orders:
          orderType === 'MARKET' ? prev.active_orders : [newOrder, ...prev.active_orders],
      }));
    },
    cancelOrder: (clientOrderId: string) => {
      client.cancelOrder(clientOrderId);
      setTelemetry((prev) => ({
        ...prev,
        active_orders: prev.active_orders.filter((o) => o.client_order_id !== clientOrderId),
      }));
    },
  };

  return <TradingContext.Provider value={value}>{children}</TradingContext.Provider>;
};

export const useTrading = (): TradingContextValue => {
  const ctx = useContext(TradingContext);
  if (!ctx) {
    throw new Error('useTrading must be used inside TradingProvider');
  }
  return ctx;
};
