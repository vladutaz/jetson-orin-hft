import { MobileTelemetryState } from '../types/telemetry';
import { MobileCryptoAuth } from './CryptoAuth';

export type TelemetryListener = (state: MobileTelemetryState, connected: boolean, endpoint: string) => void;

/**
 * Recursively applies a 10Hz delta-compressed dictionary patch onto the current client state.
 */
export function applyDeltaPatch<T extends Record<string, any>>(base: T, delta: Record<string, any>): T {
  const next: Record<string, any> = Array.isArray(base) ? [...base] : { ...base };
  for (const key of Object.keys(delta)) {
    const val = delta[key];
    if (val === null) {
      delete next[key];
    } else if (
      typeof val === 'object' &&
      !Array.isArray(val) &&
      typeof next[key] === 'object' &&
      next[key] !== null &&
      !Array.isArray(next[key])
    ) {
      next[key] = applyDeltaPatch(next[key], val);
    } else {
      next[key] = val;
    }
  }
  return next as T;
}

/**
 * Multi-path Peer-to-Peer WebSocket Gateway Client supporting:
 *   1. Direct Tailscale / WireGuard P2P IP (`wss://100.x.y.z:8443`)
 *   2. Direct Local Area Network IP (`wss://jetson-orin.local:8443`)
 *   3. Outbound Encrypted Cloud Relay (`wss://relay.jetson-quant.io/stream`)
 */
export class JetsonGatewayClient {
  private endpoints: string[];
  private currentEndpointIdx = 0;
  private ws: WebSocket | null = null;
  private jwtToken: string = '';
  private state: MobileTelemetryState | null = null;
  private listeners: Set<TelemetryListener> = new Set();
  private cryptoAuth = new MobileCryptoAuth();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private shouldRun = false;

  constructor(endpoints: string[]) {
    this.endpoints = endpoints.length > 0 ? endpoints : ['ws://100.64.0.10:8443', 'ws://127.0.0.1:8443'];
  }

  public subscribe(listener: TelemetryListener): () => void {
    this.listeners.add(listener);
    if (this.state) {
      listener(this.state, this.isConnected(), this.currentEndpoint());
    }
    return () => {
      this.listeners.delete(listener);
    };
  }

  public currentEndpoint(): string {
    return this.endpoints[this.currentEndpointIdx % this.endpoints.length];
  }

  public isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  public start(): void {
    this.shouldRun = true;
    this.connect();
  }

  public stop(): void {
    this.shouldRun = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private connect(): void {
    if (!this.shouldRun) return;
    const url = this.currentEndpoint();
    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.startPingLoop();
        this.notifyListeners();
      };

      this.ws.onmessage = async (event: WebSocketMessageEvent) => {
        try {
          const msg = JSON.parse(String(event.data));
          await this.handlePacket(msg);
        } catch {
          // Ignore malformed frame
        }
      };

      this.ws.onerror = () => {
        // Handled by onclose failover rotation
      };

      this.ws.onclose = () => {
        this.stopPingLoop();
        this.notifyListeners();
        if (this.shouldRun) {
          this.currentEndpointIdx = (this.currentEndpointIdx + 1) % this.endpoints.length;
          this.reconnectTimer = setTimeout(() => this.connect(), 1500);
        }
      };
    } catch {
      if (this.shouldRun) {
        this.currentEndpointIdx = (this.currentEndpointIdx + 1) % this.endpoints.length;
        this.reconnectTimer = setTimeout(() => this.connect(), 2000);
      }
    }
  }

  private async handlePacket(msg: Record<string, any>): Promise<void> {
    switch (msg.type) {
      case 'AUTH_CHALLENGE': {
        const deviceId = String(msg.device_id || 'mobile-operator-01');
        const nonce = String(msg.nonce || '');
        const { signatureBase64, publicKeyBase64 } = await this.cryptoAuth.signChallenge(deviceId, nonce);
        this.sendRaw({
          type: 'AUTH_RESPONSE',
          device_id: deviceId,
          nonce,
          signature: signatureBase64,
          public_key: publicKeyBase64,
        });
        break;
      }
      case 'AUTH_OK': {
        this.jwtToken = String(msg.jwt || '');
        break;
      }
      case 'TELEMETRY_FULL': {
        this.state = msg.data as MobileTelemetryState;
        this.notifyListeners();
        break;
      }
      case 'TELEMETRY_DELTA': {
        if (this.state && msg.delta) {
          this.state = applyDeltaPatch(this.state, msg.delta);
          this.notifyListeners();
        }
        break;
      }
      case 'KILL_SWITCH_ACK': {
        if (this.state) {
          this.state = { ...this.state, engine_state: 'HALTED' };
          this.notifyListeners();
        }
        break;
      }
      default:
        break;
    }
  }

  public triggerEmergencyKillSwitch(biometricVerified: boolean): void {
    if (!biometricVerified) {
      throw new Error('Biometric verification required before dispatching Kill-Switch');
    }
    this.sendRaw({
      type: 'EMERGENCY_FLATTEN',
      biometric_verified: true,
      jwt: this.jwtToken,
      ts_ms: Date.now(),
    });
    if (this.state) {
      this.state = {
        ...this.state,
        engine_state: 'HALTED',
        active_orders: [],
      };
      this.notifyListeners();
    }
  }

  public resumeTradingEngine(): void {
    this.sendRaw({
      type: 'RESUME_TRADING',
      jwt: this.jwtToken,
      ts_ms: Date.now(),
    });
    if (this.state) {
      this.state = { ...this.state, engine_state: 'ACTIVE' };
      this.notifyListeners();
    }
  }

  public submitManualOrder(
    symbol: string,
    side: 'BUY' | 'SELL',
    quantity: number,
    orderType: 'LIMIT_POST_ONLY' | 'MARKET'
  ): void {
    this.sendRaw({
      type: 'MANUAL_ORDER',
      symbol,
      side,
      quantity,
      order_type: orderType,
      jwt: this.jwtToken,
      ts_ms: Date.now(),
    });
  }

  public cancelOrder(clientOrderId: string): void {
    this.sendRaw({
      type: 'CANCEL_ORDER',
      client_order_id: clientOrderId,
      jwt: this.jwtToken,
      ts_ms: Date.now(),
    });
  }

  public saveInvestedStock(stock: {
    ticker: string;
    company_name: string;
    country_code: string;
    shares: number;
    avg_buy_price: number;
    current_price?: number;
    currency?: string;
    sector?: string;
  }): void {
    this.sendRaw({
      type: 'SAVE_STOCK',
      ...stock,
      jwt: this.jwtToken,
      ts_ms: Date.now(),
    });
  }

  public removeInvestedStock(ticker: string): void {
    this.sendRaw({
      type: 'REMOVE_STOCK',
      ticker,
      jwt: this.jwtToken,
      ts_ms: Date.now(),
    });
  }

  public updateCountryMacro(update: {
    country_code: string;
    inflation_rate_yoy_pct?: number;
    cpi_index_yoy_pct?: number;
    cpi_mom_pct?: number;
    central_bank_rate_pct?: number;
    corporate_tax_rate_pct?: number;
    capital_gains_tax_pct?: number;
    source?: string;
    headline?: string;
  }): void {
    this.sendRaw({
      type: 'UPDATE_COUNTRY_MACRO',
      ...update,
      jwt: this.jwtToken,
      ts_ms: Date.now(),
    });
  }

  private startPingLoop(): void {
    this.stopPingLoop();
    this.pingTimer = setInterval(() => {
      this.sendRaw({ type: 'PING', ts_ms: Date.now() });
    }, 2000);
  }

  private stopPingLoop(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private sendRaw(payload: Record<string, any>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  private notifyListeners(): void {
    if (!this.state) return;
    const connected = this.isConnected();
    const ep = this.currentEndpoint();
    for (const listener of this.listeners) {
      listener(this.state, connected, ep);
    }
  }
}
