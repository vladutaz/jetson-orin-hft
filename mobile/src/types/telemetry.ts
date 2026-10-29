export type EngineMode = 'ACTIVE' | 'CIRCUIT_BREAKER_TRIPPED' | 'HALTED';

export interface JetsonHardwareTelemetry {
  gpu_temp_c: number;
  cpu_load_pct: number;
  mem_used_gb: number;
  mem_total_gb: number;
  power_watts: number;
  network_ping_ms: number;
  power_mode: string;
  ts_ms: number;
}

export interface PositionTelemetry {
  symbol: string;
  quantity: number;
  avg_entry_price: number;
  mark_price: number;
  notional_usd: number;
  unrealized_pnl_usd: number;
  realized_pnl_usd: number;
}

export interface AlphaSignalTelemetry {
  symbol: string;
  position_target: number;
  confidence: number;
  stop_loss_bps: number;
  predicted_vol_bps: number;
  ofi: number;
  vpin: number;
  micro_price: number;
  mid_price: number;
  spread_bps: number;
  depth_skew: number;
  sentiment_score: number;
  trt_inference_us: number;
}

export interface OrderBookSnapshot {
  symbol: string;
  exchange: string;
  sequence_id: number;
  bids: [number, number][];
  asks: [number, number][];
  last_trade_px: number;
  last_trade_qty: number;
  last_trade_side: 'BUY' | 'SELL';
  ts_ms: number;
}

export interface CandleBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ActiveOrderItem {
  client_order_id: string;
  exchange_order_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  order_type: string;
  state: string;
  price: number;
  quantity: number;
  filled_quantity: number;
  latency_us: number;
}

export interface FillRecordItem {
  fill_id: number;
  client_order_id: string;
  exchange_order_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  fill_price: number;
  fill_qty: number;
  fee_usd: number;
  realized_pnl_usd: number;
  slippage_bps: number;
  latency_us: number;
  ts_ns: number;
}

export interface MobileTelemetryState {
  seq: number;
  ts_ms: number;
  engine_state: EngineMode;
  equity_usd: number;
  realized_pnl_usd: number;
  unrealized_pnl_usd: number;
  daily_drawdown_pct: number;
  daily_sharpe: number;
  win_rate_pct: number;
  margin_utilization_pct: number;
  hardware: JetsonHardwareTelemetry;
  positions: Record<string, PositionTelemetry>;
  signals: Record<string, AlphaSignalTelemetry>;
  orderbooks: Record<string, OrderBookSnapshot>;
  candles: Record<string, CandleBar[]>;
  active_orders: ActiveOrderItem[];
  recent_fills: FillRecordItem[];
}
