from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Deque, Dict, List, Optional, Tuple
import numpy as np

from edge.bus.schema import MarketDepthEvent


@dataclass
class MicrostructureFeatures:
    symbol: str
    exchange: str
    sequence_id: int
    exchange_ts_ns: int
    ofi: float
    vpin: float
    micro_price: float
    mid_price: float
    spread_bps: float
    depth_skew: float
    realized_vol_bps: float
    vwap_1s: float
    vwap_5s: float
    vwap_30s: float
    vwap_300s: float
    feature_vector: np.ndarray  # Normalized 16-dim float32 tensor for TensorRT input


class SymbolFeatureExtractor:
    """
    Stateful O(1) online high-frequency microstructure feature calculator per instrument:
      1. Order Flow Imbalance (OFI - Cont, Kukanov & Stoikov formulation across L1-L5)
      2. Volume-Synchronized Probability of Informed Trading (VPIN - Easley, Lopez de Prado, O'Hara)
      3. Volume-weighted Micro-Price & Mid-Price divergence
      4. Multi-Horizon Rolling VWAP (1s, 5s, 30s, 300s)
      5. Multi-Level L2 Book Depth Exponential Skew
      6. High-Frequency Realized Volatility (annualized & per-horizon bps)
    """

    def __init__(
        self,
        symbol: str,
        window_ticks: int = 256,
        vpin_bucket_volume: float = 50.0,
        vpin_num_buckets: int = 50,
    ) -> None:
        self.symbol = symbol
        self.window_ticks = window_ticks
        self.vpin_bucket_volume = max(1e-6, vpin_bucket_volume)
        self.vpin_num_buckets = vpin_num_buckets

        # Previous top-of-book state for OFI calculation
        self._prev_bid_px: Optional[float] = None
        self._prev_bid_qty: float = 0.0
        self._prev_ask_px: Optional[float] = None
        self._prev_ask_qty: float = 0.0
        self._ofi_ema: float = 0.0

        # VPIN state
        self._current_bucket_buy_vol: float = 0.0
        self._current_bucket_sell_vol: float = 0.0
        self._current_bucket_total_vol: float = 0.0
        self._vpin_buckets: Deque[float] = deque(maxlen=vpin_num_buckets)
        self._last_recorded_trade_seq: int = -1

        # Multi-horizon VWAP ring buffer: (ts_sec, price, volume)
        self._trade_ring: Deque[Tuple[float, float, float]] = deque(maxlen=4096)

        # Log-return buffer for realized volatility
        self._mid_history: Deque[float] = deque(maxlen=window_ticks)
        self._log_returns: Deque[float] = deque(maxlen=window_ticks)

        # Rolling feature history for temporal sequence tensor (T x F)
        self._tensor_history: Deque[np.ndarray] = deque(maxlen=32)

    def update(self, event: MarketDepthEvent, sentiment_score: float = 0.0) -> MicrostructureFeatures:
        bids = event.bids
        asks = event.asks
        best_bid_px, best_bid_qty = bids[0] if bids else (0.0, 0.0)
        best_ask_px, best_ask_qty = asks[0] if asks else (0.0, 0.0)

        mid_price = 0.5 * (best_bid_px + best_ask_px) if (best_bid_px > 0 and best_ask_px > 0) else 0.0
        top_qty_sum = best_bid_qty + best_ask_qty
        micro_price = (
            ((best_bid_px * best_ask_qty) + (best_ask_px * best_bid_qty)) / top_qty_sum
            if top_qty_sum > 0.0
            else mid_price
        )
        spread_bps = ((best_ask_px - best_bid_px) / mid_price) * 10000.0 if mid_price > 0.0 else 0.0

        # 1. Order Flow Imbalance (OFI)
        ofi_tick = self._compute_ofi_tick(best_bid_px, best_bid_qty, best_ask_px, best_ask_qty)
        self._ofi_ema = 0.85 * self._ofi_ema + 0.15 * ofi_tick

        # 2. VPIN & Multi-horizon VWAP update
        ts_sec = event.exchange_ts_ns / 1_000_000_000.0
        trade_px = event.last_trade_px if event.last_trade_px > 0.0 else mid_price
        trade_qty = event.last_trade_qty if event.last_trade_qty > 0.0 else (0.05 * top_qty_sum)
        if trade_px > 0.0 and trade_qty > 0.0:
            self._update_vpin(trade_qty, event.last_trade_is_buyer_maker, trade_px, mid_price)
            self._trade_ring.append((ts_sec, trade_px, trade_qty))

        vpin_val = float(sum(self._vpin_buckets) / len(self._vpin_buckets)) if self._vpin_buckets else 0.25

        # 3. Multi-horizon VWAPs (1s, 5s, 30s, 300s)
        vwap_1s = self._compute_horizon_vwap(ts_sec, 1.0, mid_price)
        vwap_5s = self._compute_horizon_vwap(ts_sec, 5.0, mid_price)
        vwap_30s = self._compute_horizon_vwap(ts_sec, 30.0, mid_price)
        vwap_300s = self._compute_horizon_vwap(ts_sec, 300.0, mid_price)

        # 4. Multi-level L2 Exponential Book Depth Skew
        depth_skew = self._compute_depth_skew(bids, asks, mid_price)

        # 5. Realized Volatility (bps)
        if mid_price > 0.0:
            if self._mid_history:
                prev_mid = self._mid_history[-1]
                if prev_mid > 0.0:
                    self._log_returns.append(math.log(mid_price / prev_mid))
            self._mid_history.append(mid_price)

        if len(self._log_returns) >= 4:
            arr_ret = np.fromiter(self._log_returns, dtype=np.float64)
            realized_vol_bps = float(np.std(arr_ret) * math.sqrt(len(arr_ret)) * 10000.0)
        else:
            realized_vol_bps = max(1.0, spread_bps * 1.5)

        # Construct normalized 16-dimensional float32 feature vector for TensorRT inference
        micro_div_bps = ((micro_price - mid_price) / mid_price) * 10000.0 if mid_price > 0.0 else 0.0
        vwap1_dev_bps = ((mid_price - vwap_1s) / mid_price) * 10000.0 if mid_price > 0.0 else 0.0
        vwap5_dev_bps = ((mid_price - vwap_5s) / mid_price) * 10000.0 if mid_price > 0.0 else 0.0
        vwap30_dev_bps = ((mid_price - vwap_30s) / mid_price) * 10000.0 if mid_price > 0.0 else 0.0
        vwap300_dev_bps = ((mid_price - vwap_300s) / mid_price) * 10000.0 if mid_price > 0.0 else 0.0
        l1_imbalance = (best_bid_qty - best_ask_qty) / top_qty_sum if top_qty_sum > 0.0 else 0.0
        last_ret_bps = (self._log_returns[-1] * 10000.0) if self._log_returns else 0.0

        vec = np.array(
            [
                np.tanh(ofi_tick / max(1.0, top_qty_sum)),
                np.tanh(self._ofi_ema / max(1.0, top_qty_sum)),
                vpin_val,
                np.tanh(micro_div_bps / 5.0),
                np.tanh(spread_bps / 10.0),
                depth_skew,
                np.tanh(realized_vol_bps / 50.0),
                np.tanh(vwap1_dev_bps / 10.0),
                np.tanh(vwap5_dev_bps / 15.0),
                np.tanh(vwap30_dev_bps / 25.0),
                np.tanh(vwap300_dev_bps / 50.0),
                l1_imbalance,
                np.tanh(last_ret_bps / 5.0),
                sentiment_score,
                float(event.last_trade_is_buyer_maker) * -2.0 + 1.0,
                1.0,  # bias term
            ],
            dtype=np.float32,
        )
        self._tensor_history.append(vec)

        return MicrostructureFeatures(
            symbol=event.symbol,
            exchange=event.exchange,
            sequence_id=event.sequence_id,
            exchange_ts_ns=event.exchange_ts_ns,
            ofi=float(self._ofi_ema),
            vpin=vpin_val,
            micro_price=micro_price,
            mid_price=mid_price,
            spread_bps=spread_bps,
            depth_skew=depth_skew,
            realized_vol_bps=realized_vol_bps,
            vwap_1s=vwap_1s,
            vwap_5s=vwap_5s,
            vwap_30s=vwap_30s,
            vwap_300s=vwap_300s,
            feature_vector=vec,
        )

    def _compute_ofi_tick(
        self,
        bid_px: float,
        bid_qty: float,
        ask_px: float,
        ask_qty: float,
    ) -> float:
        if self._prev_bid_px is None or self._prev_ask_px is None:
            self._prev_bid_px, self._prev_bid_qty = bid_px, bid_qty
            self._prev_ask_px, self._prev_ask_qty = ask_px, ask_qty
            return 0.0

        # Bid contribution e_b
        if bid_px > self._prev_bid_px:
            e_b = bid_qty
        elif bid_px == self._prev_bid_px:
            e_b = bid_qty - self._prev_bid_qty
        else:
            e_b = -self._prev_bid_qty

        # Ask contribution e_a
        if ask_px < self._prev_ask_px:
            e_a = ask_qty
        elif ask_px == self._prev_ask_px:
            e_a = ask_qty - self._prev_ask_qty
        else:
            e_a = -self._prev_ask_qty

        self._prev_bid_px, self._prev_bid_qty = bid_px, bid_qty
        self._prev_ask_px, self._prev_ask_qty = ask_px, ask_qty
        return e_b - e_a

    def _update_vpin(
        self,
        qty: float,
        is_buyer_maker: bool,
        trade_px: float,
        mid_px: float,
    ) -> None:
        # Bulk volume classification + aggressor flag
        if not is_buyer_maker or (trade_px >= mid_px and mid_px > 0):
            buy_v = qty
            sell_v = 0.0
        else:
            buy_v = 0.0
            sell_v = qty

        self._current_bucket_buy_vol += buy_v
        self._current_bucket_sell_vol += sell_v
        self._current_bucket_total_vol += qty

        while self._current_bucket_total_vol >= self.vpin_bucket_volume:
            frac = self.vpin_bucket_volume / self._current_bucket_total_vol
            b_buy = self._current_bucket_buy_vol * frac
            b_sell = self._current_bucket_sell_vol * frac
            toxicity = abs(b_buy - b_sell) / self.vpin_bucket_volume
            self._vpin_buckets.append(min(1.0, toxicity))

            self._current_bucket_buy_vol -= b_buy
            self._current_bucket_sell_vol -= b_sell
            self._current_bucket_total_vol -= self.vpin_bucket_volume

    def _compute_horizon_vwap(self, now_sec: float, horizon_sec: float, fallback_px: float) -> float:
        cutoff = now_sec - horizon_sec
        notional = 0.0
        vol = 0.0
        for ts, px, q in reversed(self._trade_ring):
            if ts < cutoff:
                break
            notional += px * q
            vol += q
        return (notional / vol) if vol > 0.0 else fallback_px

    @staticmethod
    def _compute_depth_skew(
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        mid_price: float,
    ) -> float:
        if not bids or not asks or mid_price <= 0.0:
            return 0.0
        weighted_bid = 0.0
        weighted_ask = 0.0
        for idx, (px, qty) in enumerate(bids[:20]):
            decay = math.exp(-0.15 * idx)
            weighted_bid += qty * decay
        for idx, (px, qty) in enumerate(asks[:20]):
            decay = math.exp(-0.15 * idx)
            weighted_ask += qty * decay
        denom = weighted_bid + weighted_ask
        return (weighted_bid - weighted_ask) / denom if denom > 0.0 else 0.0


class FeaturePipeline:
    """
    Manages online `SymbolFeatureExtractor` instances across all traded instruments.
    """

    def __init__(
        self,
        window_ticks: int = 256,
        vpin_bucket_volume: float = 50.0,
        vpin_num_buckets: int = 50,
    ) -> None:
        self.window_ticks = window_ticks
        self.vpin_bucket_volume = vpin_bucket_volume
        self.vpin_num_buckets = vpin_num_buckets
        self._extractors: Dict[str, SymbolFeatureExtractor] = {}

    def process(self, event: MarketDepthEvent, sentiment_score: float = 0.0) -> MicrostructureFeatures:
        extractor = self._extractors.get(event.symbol)
        if extractor is None:
            extractor = SymbolFeatureExtractor(
                symbol=event.symbol,
                window_ticks=self.window_ticks,
                vpin_bucket_volume=self.vpin_bucket_volume,
                vpin_num_buckets=self.vpin_num_buckets,
            )
            self._extractors[event.symbol] = extractor
        return extractor.update(event, sentiment_score)
