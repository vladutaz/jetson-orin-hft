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

export interface InvestedStockItem {
  ticker: string;
  company_name: string;
  country_code: string;
  shares: number;
  avg_buy_price: number;
  current_price: number;
  currency: string;
  sector: string;
  status: string;
  sentiment_score: number;
  last_catalyst_headline: string;
  last_catalyst_source: string;
  cost_basis: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  updated_ts_ms: number;
}

export interface CountryMacroItem {
  country_code: string;
  country_name: string;
  currency: string;
  inflation_rate_yoy_pct: number;
  cpi_index_yoy_pct: number;
  cpi_mom_pct: number;
  central_bank_rate_pct: number;
  corporate_tax_rate_pct: number;
  capital_gains_tax_pct: number;
  last_updated_source: string;
  updated_ts_ms: number;
}

export interface PortfolioNotificationItem {
  notification_id: string;
  category: 'STOCK_STATUS' | 'INFLATION_ALERT' | 'CPI_RELEASE' | 'TAX_POLICY_CHANGE' | 'GURU_CATALYST' | string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL' | 'BULLISH_CATALYST' | string;
  ticker: string;
  country_code: string;
  title: string;
  message: string;
  source: string;
  metric_name: string;
  previous_value: number;
  new_value: number;
  affected_tickers: string[];
  ts_ms: number;
  acknowledged: boolean;
}

export interface TrustedNewsItem {
  source: string;
  headline: string;
  symbols: string[];
  sentiment_score: number;
  confidence: number;
  ts_ms: number;
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
  invested_stocks: InvestedStockItem[];
  country_macro: Record<string, CountryMacroItem>;
  notifications: PortfolioNotificationItem[];
  trusted_news_feed: TrustedNewsItem[];
}
