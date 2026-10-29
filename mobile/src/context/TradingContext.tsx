import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { JetsonGatewayClient } from '../services/GatewayClient';
import { MobileTelemetryState } from '../types/telemetry';

const INITIAL_TELEMETRY: MobileTelemetryState = {
  seq: 1,
  ts_ms: Date.now(),
  engine_state: 'ACTIVE',
  equity_usd: 254820.45,
  realized_pnl_usd: 4190.2,
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
        [89978.0, 5.6],
        [89977.5, 4.18],
        [89976.8, 8.92],
        [89976.0, 6.4],
        [89975.2, 11.25],
      ],
      asks: [
        [89980.4, 0.92],
        [89980.9, 1.65],
        [89981.5, 2.8],
        [89982.0, 4.1],
        [89982.8, 3.75],
        [89983.5, 6.2],
        [89984.2, 7.85],
        [89985.0, 9.5],
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
      const close = base + (idx % 2 === 0 ? 1 : -1) * 24;
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
  invested_stocks: [
    {
      ticker: 'NVDA',
      company_name: 'NVIDIA Corporation',
      country_code: 'US',
      shares: 45,
      avg_buy_price: 118.5,
      current_price: 138.6,
      currency: 'USD',
      sector: 'Semiconductors & AI',
      status: 'OUTPERFORMING',
      sentiment_score: 0.78,
      last_catalyst_headline: 'Seeking Alpha: NVIDIA Blackwell datacenter demand surges ahead of Q4 guidance',
      last_catalyst_source: 'Seeking Alpha Market Currents',
      cost_basis: 5332.5,
      market_value: 6237.0,
      unrealized_pnl: 904.5,
      unrealized_pnl_pct: 16.96,
      updated_ts_ms: Date.now(),
    },
    {
      ticker: 'AAPL',
      company_name: 'Apple Inc.',
      country_code: 'US',
      shares: 60,
      avg_buy_price: 212.0,
      current_price: 231.4,
      currency: 'USD',
      sector: 'Consumer Technology',
      status: 'OUTPERFORMING',
      sentiment_score: 0.52,
      last_catalyst_headline: 'GuruFocus / Trading Guru: Institutional buyback pace and services margin expansion',
      last_catalyst_source: 'GuruFocus / Trading Guru',
      cost_basis: 12720.0,
      market_value: 13884.0,
      unrealized_pnl: 1164.0,
      unrealized_pnl_pct: 9.15,
      updated_ts_ms: Date.now(),
    },
    {
      ticker: 'ASML',
      company_name: 'ASML Holding N.V.',
      country_code: 'EU',
      shares: 12,
      avg_buy_price: 720.0,
      current_price: 695.5,
      currency: 'EUR',
      sector: 'Semiconductor Lithography',
      status: 'WATCH',
      sentiment_score: 0.14,
      last_catalyst_headline: 'Eurostat CPI cools to 2.0% YoY supporting European tech valuation multiples',
      last_catalyst_source: 'Eurostat Eurozone CPI & Macro',
      cost_basis: 8640.0,
      market_value: 8346.0,
      unrealized_pnl: -294.0,
      unrealized_pnl_pct: -3.4,
      updated_ts_ms: Date.now(),
    },
  ],
  country_macro: {
    US: {
      country_code: 'US',
      country_name: 'United States',
      currency: 'USD',
      inflation_rate_yoy_pct: 2.6,
      cpi_index_yoy_pct: 2.6,
      cpi_mom_pct: 0.2,
      central_bank_rate_pct: 4.75,
      corporate_tax_rate_pct: 21.0,
      capital_gains_tax_pct: 20.0,
      last_updated_source: 'US Bureau of Labor Statistics (BLS) / Federal Reserve',
      updated_ts_ms: Date.now(),
    },
    EU: {
      country_code: 'EU',
      country_name: 'Eurozone (ECB)',
      currency: 'EUR',
      inflation_rate_yoy_pct: 2.0,
      cpi_index_yoy_pct: 2.0,
      cpi_mom_pct: 0.1,
      central_bank_rate_pct: 3.25,
      corporate_tax_rate_pct: 25.0,
      capital_gains_tax_pct: 26.0,
      last_updated_source: 'Eurostat / European Central Bank',
      updated_ts_ms: Date.now(),
    },
    UK: {
      country_code: 'UK',
      country_name: 'United Kingdom',
      currency: 'GBP',
      inflation_rate_yoy_pct: 2.3,
      cpi_index_yoy_pct: 2.3,
      cpi_mom_pct: 0.3,
      central_bank_rate_pct: 4.75,
      corporate_tax_rate_pct: 25.0,
      capital_gains_tax_pct: 24.0,
      last_updated_source: 'UK Office for National Statistics (ONS)',
      updated_ts_ms: Date.now(),
    },
    RO: {
      country_code: 'RO',
      country_name: 'Romania',
      currency: 'RON',
      inflation_rate_yoy_pct: 4.7,
      cpi_index_yoy_pct: 4.7,
      cpi_mom_pct: 0.4,
      central_bank_rate_pct: 6.5,
      corporate_tax_rate_pct: 16.0,
      capital_gains_tax_pct: 10.0,
      last_updated_source: 'INSSE / National Bank of Romania (BNR)',
      updated_ts_ms: Date.now(),
    },
  },
  notifications: [
    {
      notification_id: 'ntf-cpi-us-01',
      category: 'CPI_RELEASE',
      severity: 'BULLISH_CATALYST',
      ticker: 'NVDA,AAPL',
      country_code: 'US',
      title: '[US] CPI Index (YoY) decreased from 2.90% to 2.60%',
      message:
        'United States (US) CPI Index (YoY) decreased by -0.30% (from 2.90% to 2.60%) via US Bureau of Labor Statistics (BLS). Affected invested stocks in your portfolio: [NVDA, AAPL].',
      source: 'US Bureau of Labor Statistics (CPI/Inflation)',
      metric_name: 'CPI_INDEX_YOY_PCT',
      previous_value: 2.9,
      new_value: 2.6,
      affected_tickers: ['NVDA', 'AAPL'],
      ts_ms: Date.now() - 120000,
      acknowledged: false,
    },
    {
      notification_id: 'ntf-guru-nvda-02',
      category: 'GURU_CATALYST',
      severity: 'BULLISH_CATALYST',
      ticker: 'NVDA',
      country_code: 'US',
      title: 'NVDA Status Update: OUTPERFORMING (+16.96%)',
      message:
        'NVIDIA Corporation (NVDA) is now at 138.60 USD (PnL: +904.50 USD / +16.96%). Catalyst [Seeking Alpha Market Currents]: NVIDIA Blackwell datacenter demand surges ahead of Q4 guidance.',
      source: 'Seeking Alpha Market Currents',
      metric_name: 'UNREALIZED_PNL_PCT',
      previous_value: 12.4,
      new_value: 16.96,
      affected_tickers: ['NVDA'],
      ts_ms: Date.now() - 300000,
      acknowledged: false,
    },
  ],
  trusted_news_feed: [
    {
      source: 'Seeking Alpha Market Currents',
      headline: 'NVIDIA Blackwell datacenter demand surges ahead of Q4 institutional guidance; hyperscaler CapEx raised',
      symbols: ['NVDA', 'BTCUSDT'],
      sentiment_score: 0.82,
      confidence: 0.91,
      ts_ms: Date.now() - 45000,
    },
    {
      source: 'GuruFocus / Trading Guru',
      headline: 'Top quantitative gurus increase allocation to semiconductor & AI infrastructure leaders',
      symbols: ['NVDA', 'AAPL', 'ASML'],
      sentiment_score: 0.68,
      confidence: 0.85,
      ts_ms: Date.now() - 95000,
    },
    {
      source: 'US Bureau of Labor Statistics (CPI/Inflation)',
      headline: 'US Consumer Price Index (CPI) cools to 2.6% YoY; Core inflation steady at 0.2% MoM',
      symbols: ['BTCUSDT', 'ETHUSDT', 'NVDA', 'AAPL'],
      sentiment_score: 0.64,
      confidence: 0.94,
      ts_ms: Date.now() - 180000,
    },
    {
      source: 'SEC EDGAR Regulatory Filings',
      headline: 'Form 13F-HR Institutional Holdings Update: Spot Bitcoin ETF & AI equity inflows reach quarterly high',
      symbols: ['BTCUSDT', 'NVDA'],
      sentiment_score: 0.75,
      confidence: 0.89,
      ts_ms: Date.now() - 240000,
    },
  ],
};

interface SaveStockInput {
  ticker: string;
  company_name: string;
  country_code: string;
  shares: number;
  avg_buy_price: number;
  current_price?: number;
  currency?: string;
  sector?: string;
}

interface UpdateCountryMacroInput {
  country_code: string;
  inflation_rate_yoy_pct?: number;
  cpi_index_yoy_pct?: number;
  cpi_mom_pct?: number;
  central_bank_rate_pct?: number;
  corporate_tax_rate_pct?: number;
  capital_gains_tax_pct?: number;
  source?: string;
  headline?: string;
}

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
  saveInvestedStock: (input: SaveStockInput) => void;
  removeInvestedStock: (ticker: string) => void;
  updateCountryMacro: (input: UpdateCountryMacroInput) => void;
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
    saveInvestedStock: (input: SaveStockInput) => {
      client.saveInvestedStock(input);
      const ticker = input.ticker.trim().toUpperCase();
      const countryCode = input.country_code.trim().toUpperCase() || 'US';
      const curPx = input.current_price ?? input.avg_buy_price;
      const costBasis = input.shares * input.avg_buy_price;
      const mktVal = input.shares * curPx;
      const pnl = mktVal - costBasis;
      const pnlPct = input.avg_buy_price > 0 ? ((curPx - input.avg_buy_price) / input.avg_buy_price) * 100 : 0;
      const status =
        pnlPct >= 8 ? 'OUTPERFORMING' : pnlPct <= -8 ? 'DRAWDOWN_ALERT' : 'STABLE';

      const newStock = {
        ticker,
        company_name: input.company_name.trim() || ticker,
        country_code: countryCode,
        shares: input.shares,
        avg_buy_price: input.avg_buy_price,
        current_price: curPx,
        currency: input.currency || 'USD',
        sector: input.sector || 'Equities',
        status,
        sentiment_score: 0.35,
        last_catalyst_headline: 'Position saved and actively monitored across Seeking Alpha, GuruFocus & Country Macro feeds.',
        last_catalyst_source: 'Portfolio Monitor',
        cost_basis: costBasis,
        market_value: mktVal,
        unrealized_pnl: pnl,
        unrealized_pnl_pct: pnlPct,
        updated_ts_ms: Date.now(),
      };

      const newNotif = {
        notification_id: `ntf-${Date.now()}`,
        category: 'STOCK_STATUS',
        severity: 'INFO',
        ticker,
        country_code: countryCode,
        title: `Saved ${ticker} (${newStock.company_name}) — Status: ${status}`,
        message: `Tracking ${input.shares} shares of ${ticker} in ${countryCode}. Live alerts enabled for ${countryCode} Inflation, CPI, and Tax changes.`,
        source: 'Portfolio Monitor',
        metric_name: 'UNREALIZED_PNL_PCT',
        previous_value: 0,
        new_value: Number(pnlPct.toFixed(2)),
        affected_tickers: [ticker],
        ts_ms: Date.now(),
        acknowledged: false,
      };

      setTelemetry((prev) => ({
        ...prev,
        invested_stocks: [
          newStock,
          ...prev.invested_stocks.filter((s) => s.ticker !== ticker),
        ],
        notifications: [newNotif, ...prev.notifications],
      }));
    },
    removeInvestedStock: (ticker: string) => {
      client.removeInvestedStock(ticker);
      setTelemetry((prev) => ({
        ...prev,
        invested_stocks: prev.invested_stocks.filter((s) => s.ticker !== ticker),
      }));
    },
    updateCountryMacro: (input: UpdateCountryMacroInput) => {
      client.updateCountryMacro(input);
      const code = input.country_code.trim().toUpperCase();
      setTelemetry((prev) => {
        const existing = prev.country_macro[code] || {
          country_code: code,
          country_name: code,
          currency: 'USD',
          inflation_rate_yoy_pct: 2.5,
          cpi_index_yoy_pct: 2.5,
          cpi_mom_pct: 0.2,
          central_bank_rate_pct: 4.0,
          corporate_tax_rate_pct: 21.0,
          capital_gains_tax_pct: 20.0,
          last_updated_source: 'Sovereign Macro Feed',
          updated_ts_ms: Date.now(),
        };

        const oldInf = existing.inflation_rate_yoy_pct;
        const newInf = input.inflation_rate_yoy_pct ?? oldInf;
        const oldCpi = existing.cpi_index_yoy_pct;
        const newCpi = input.cpi_index_yoy_pct ?? oldCpi;
        const oldTax = existing.capital_gains_tax_pct;
        const newTax = input.capital_gains_tax_pct ?? oldTax;

        const updatedMacro = {
          ...existing,
          inflation_rate_yoy_pct: newInf,
          cpi_index_yoy_pct: newCpi,
          cpi_mom_pct: input.cpi_mom_pct ?? existing.cpi_mom_pct,
          central_bank_rate_pct: input.central_bank_rate_pct ?? existing.central_bank_rate_pct,
          corporate_tax_rate_pct: input.corporate_tax_rate_pct ?? existing.corporate_tax_rate_pct,
          capital_gains_tax_pct: newTax,
          last_updated_source: input.source || 'Sovereign Macro / Tax Feed',
          updated_ts_ms: Date.now(),
        };

        const affected = prev.invested_stocks
          .filter((s) => s.country_code === code)
          .map((s) => s.ticker);

        const newNotifs = [...prev.notifications];
        if (Math.abs(newInf - oldInf) > 1e-4 || Math.abs(newCpi - oldCpi) > 1e-4) {
          newNotifs.unshift({
            notification_id: `ntf-macro-${Date.now()}`,
            category: 'INFLATION_ALERT',
            severity: newInf > oldInf ? 'WARNING' : 'BULLISH_CATALYST',
            ticker: affected.join(',') || code,
            country_code: code,
            title: `[${code}] Inflation / CPI Updated: ${oldInf.toFixed(2)}% -> ${newInf.toFixed(2)}%`,
            message: `${updatedMacro.country_name} (${code}) Inflation/CPI shifted from ${oldInf.toFixed(2)}% to ${newInf.toFixed(2)}%. Affected invested stocks: [${affected.join(', ') || 'None'}].`,
            source: updatedMacro.last_updated_source,
            metric_name: 'INFLATION_RATE_YOY_PCT',
            previous_value: oldInf,
            new_value: newInf,
            affected_tickers: affected,
            ts_ms: Date.now(),
            acknowledged: false,
          });
        }
        if (Math.abs(newTax - oldTax) > 1e-4) {
          newNotifs.unshift({
            notification_id: `ntf-tax-${Date.now() + 1}`,
            category: 'TAX_POLICY_CHANGE',
            severity: newTax > oldTax ? 'CRITICAL' : 'BULLISH_CATALYST',
            ticker: affected.join(',') || code,
            country_code: code,
            title: `[${code}] Capital Gains Tax Changed: ${oldTax.toFixed(1)}% -> ${newTax.toFixed(1)}%`,
            message: `${updatedMacro.country_name} (${code}) Capital Gains Tax changed from ${oldTax.toFixed(1)}% to ${newTax.toFixed(1)}%. Affected invested stocks: [${affected.join(', ') || 'None'}].`,
            source: updatedMacro.last_updated_source,
            metric_name: 'CAPITAL_GAINS_TAX_PCT',
            previous_value: oldTax,
            new_value: newTax,
            affected_tickers: affected,
            ts_ms: Date.now(),
            acknowledged: false,
          });
        }

        return {
          ...prev,
          country_macro: {
            ...prev.country_macro,
            [code]: updatedMacro,
          },
          notifications: newNotifs,
        };
      });
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
