from __future__ import annotations

import copy
from typing import Any, Dict, Optional


def compute_dict_delta(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively computes the minimal delta between two state dictionaries so that
    unchanged subtrees and fields are omitted from 10Hz mobile telemetry broadcasts.
    """
    delta: Dict[str, Any] = {}
    for k, curr_val in curr.items():
        if k not in prev:
            delta[k] = curr_val
            continue
        prev_val = prev[k]
        if isinstance(curr_val, dict) and isinstance(prev_val, dict):
            nested = compute_dict_delta(prev_val, curr_val)
            if nested:
                delta[k] = nested
        elif curr_val != prev_val:
            delta[k] = curr_val

    for deleted_key in set(prev.keys()) - set(curr.keys()):
        delta[deleted_key] = None
    return delta


def apply_dict_delta(base: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstructs the full state dictionary by applying a compressed delta packet onto `base`.
    """
    result = copy.deepcopy(base)
    for k, val in delta.items():
        if val is None:
            result.pop(k, None)
        elif isinstance(val, dict) and isinstance(result.get(k), dict):
            result[k] = apply_dict_delta(result[k], val)
        else:
            result[k] = copy.deepcopy(val)
    return result


class TelemetryDeltaCompressor:
    """
    Per-client stateful delta encoder for 10Hz mobile telemetry streams.
    Emits a full snapshot on initial subscription or every `full_sync_interval` frames,
    and compact delta frames for all intermediate ticks.
    """

    def __init__(self, full_sync_interval: int = 100) -> None:
        self.full_sync_interval = full_sync_interval
        self._last_state: Optional[Dict[str, Any]] = None
        self._frame_count: int = 0

    def encode_frame(self, current_state: Dict[str, Any]) -> Dict[str, Any]:
        self._frame_count += 1
        if self._last_state is None or (self._frame_count % self.full_sync_interval == 0):
            self._last_state = copy.deepcopy(current_state)
            return {
                "type": "TELEMETRY_FULL",
                "seq": current_state.get("seq", self._frame_count),
                "ts_ms": current_state.get("ts_ms", 0),
                "data": current_state,
            }

        diff = compute_dict_delta(self._last_state, current_state)
        self._last_state = copy.deepcopy(current_state)
        return {
            "type": "TELEMETRY_DELTA",
            "seq": current_state.get("seq", self._frame_count),
            "ts_ms": current_state.get("ts_ms", 0),
            "delta": diff,
        }
