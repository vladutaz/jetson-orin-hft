# NVIDIA Jetson Orin High-Frequency & Systematic Trading Platform + Mobile Client

[![Target Hardware](https://img.shields.io/badge/Hardware-NVIDIA%20Jetson%20Orin%20(JetPack%206.x)-76B900?logo=nvidia)](https://developer.nvidia.com/embedded/jetson-orin)
[![Compute Stack](https://img.shields.io/badge/Compute-CUDA%2012.x%20%7C%20TensorRT%2010.x%20(FP16%2FINT8)-00B4D8)](https://developer.nvidia.com/tensorrt)
[![IPC Bus](https://img.shields.io/badge/IPC-ZeroMQ%20%2B%20POSIX%20Shared%20Memory-FF6B6B)](https://zeromq.org/)
[![Mobile App](https://img.shields.io/badge/Mobile-React%20Native%20%2B%20TypeScript%20(Expo)-61DAFB?logo=react)](https://reactnative.dev/)

An institutional-grade, multi-process, ultra-low-latency algorithmic trading platform engineered specifically for **NVIDIA Jetson Orin (AGX Orin / Orin NX / Orin Nano running Ubuntu 22.04 L4T / JetPack 6.x)**, paired with a dark-themed **React Native (TypeScript) Mobile Management, Telemetry & Biometric Kill-Switch Application**.

---

## Table of Contents
1. [System Architecture & Dataflow](#1-system-architecture--dataflow)
2. [Repository Structure](#2-repository-structure)
3. [Part I: NVIDIA Jetson Orin Implementation Guide (Edge Server)](#3-part-i-nvidia-jetson-orin-implementation-guide-edge-server)
   - [Step 1: Hardware & JetPack 6.x Preparation](#step-1-hardware--jetpack-6x-preparation)
   - [Step 2: MAXN Power Mode, Clocks & Kernel Network Tuning](#step-2-maxn-power-mode-clocks--kernel-network-tuning)
   - [Step 3: Python Environment & System Dependencies](#step-3-python-environment--system-dependencies)
   - [Step 4: Compiling the TensorRT FP16/INT8 Inference Engine](#step-4-compiling-the-tensorrt-fp16int8-inference-engine)
   - [Step 5: Configuring Exchange Ed25519 Keys & Risk Limits](#step-5-configuring-exchange-ed25519-keys--risk-limits)
   - [Step 6: Setting Up Secure Peer-to-Peer Connectivity (Tailscale / WireGuard / mTLS)](#step-6-setting-up-secure-peer-to-peer-connectivity-tailscale--wireguard--mtls)
   - [Step 7: Installing Real-Time FIFO Systemd Daemons & Watchdog Recovery](#step-7-installing-real-time-fifo-systemd-daemons--watchdog-recovery)
4. [Part II: Mobile Client Implementation Guide (iOS & Android Phone)](#4-part-ii-mobile-client-implementation-guide-ios--android-phone)
   - [Step 1: Prerequisites & Installing Dependencies](#step-1-prerequisites--installing-dependencies)
   - [Step 2: Connecting Your Phone to the Jetson Orin Gateway](#step-2-connecting-your-phone-to-the-jetson-orin-gateway)
   - [Step 3: Running on a Physical Phone (Expo Go / Native Build)](#step-3-running-on-a-physical-phone-expo-go--native-build)
   - [Step 4: Mobile Screens & Biometric Kill-Switch Walkthrough](#step-4-mobile-screens--biometric-kill-switch-walkthrough)
5. [Subsystems Deep-Dive](#5-subsystems-deep-dive)
6. [Testing & Verification](#6-testing--verification)

---

## 1. System Architecture & Dataflow

```mermaid
flowchart TD
    subgraph Exchanges["External Venues & Alternative Data"]
        BF["Binance Futures WS + REST"]
        BY["Bybit V5 Linear WS"]
        CB["Coinbase Advanced Trade WS"]
        NW["SEC EDGAR Atom / Financial RSS"]
    end

    subgraph Jetson["NVIDIA Jetson Orin SoC (Ubuntu 22.04 L4T / JetPack 6.x)"]
        subgraph Layer1["Layer 1: Ingestion Daemon (jetson-ingest | Cores 0-3 | FIFO 90)"]
            OB["LocalL2OrderBook Delta Reconstructor (U, u, pu & CRC32 Parity)"]
            NS["Token-Bucket News Scraper + TensorRT FinBERT (<15ms)"]
        end

        subgraph Layer2["Layer 2: Sub-Millisecond IPC Bus"]
            SHM["POSIX Shared Memory (/dev/shm/jetson_l2_ring | 136B Slot)"]
            ZMQ["ZeroMQ IPC Sockets (ipc:///tmp/jetson_*.ipc)"]
        end

        subgraph Layer3["Layer 3: Prediction Engine (Cores 4-7 | Unified Memory)"]
            FE["Online Microstructure Features (OFI, VPIN, Micro-Price, 1s-300s VWAP, Skew)"]
            TRT["NVIDIA TensorRT 10.x Worker (FP16/INT8 | cudaHostAllocMapped Zero-Copy)"]
        end

        subgraph Layer4["Layer 4: Risk & Execution Engine (jetson-engine | Cores 4-7 | FIFO 99)"]
            RG["Pre-Trade Risk Gatekeeper (3% Daily Drawdown Breaker, 150ms Stale Feed Gate)"]
            SOR["Smart Order Router (Ed25519 Signer + Passive Maker Post-Only Chase Loop)"]
            SM["Deterministic Order State Machine + SQLite WAL Ledger"]
        end

        subgraph Layer5["Layer 5: Telemetry & Command Bridge (jetson-bridge | Cores 8-9 | FIFO 85)"]
            HW["Sysfs Hardware Reader (GPU Temp, 12C Load, LPDDR5, INA3221 Watts, /dev/watchdog)"]
            GW["TLS 1.3 / mTLS WebSocket Gateway + Ed25519 JWT Auth + 10Hz Delta Compressor"]
        end
    end

    subgraph Mobile["Layer 6: Cross-Platform Mobile Client (React Native + TypeScript)"]
        DASH["Dashboard & Jetson Hardware HUD"]
        TERM["Candlestick Chart + L2 Depth Ladder + Alpha Readouts"]
        ORD["Active Orders, Fills/Slippage Log & Manual Override"]
        KILL["Biometric (FaceID/TouchID) + 2s Hold Emergency Kill-Switch"]
    end

    BF & BY & CB --> OB
    NW --> NS
    OB --> SHM & ZMQ
    NS --> ZMQ
    SHM & ZMQ --> FE --> TRT --> RG --> SOR --> SM
    SM --> ZMQ
    ZMQ & HW --> GW
    GW <==>|"10Hz Delta Stream / Priority Kill-Switch (Tailscale / WireGuard / LAN)"| Mobile
```

---

## 2. Repository Structure

```text
jetson/
├── config/
│   └── settings.yaml                 # Master platform, IPC, risk, execution & gateway configuration
├── edge/
│   ├── config.py                     # Typed configuration dataclasses & loader
│   ├── bus/
│   │   ├── schema.py                 # Binary MessagePack & 136-byte C-struct shared memory codecs
│   │   └── zmq_bus.py                # Async ZeroMQ PUB/SUB, PUSH/PULL & POSIX SharedMemoryL2Ring
│   ├── ingestion/
│   │   ├── orderbook.py              # L2 order book delta reconstruction, sequence & parity checks
│   │   ├── ws_feeds.py               # Async WS feed handlers (Binance Futures, Bybit V5, Coinbase)
│   │   ├── news_scraper.py           # Token-bucket scraper, proxy rotation & <15ms NLP sentiment
│   │   └── main.py                   # Layer 1 entrypoint (`python3 -m edge.ingestion.main`)
│   ├── prediction/
│   │   ├── features.py               # Online OFI, VPIN, Micro-price, Multi-horizon VWAP, Skew, RVol
│   │   ├── trt_engine.py             # TensorRT 10.x FP16/INT8 zero-copy (`cudaHostAllocMapped`) engine
│   │   └── worker.py                 # Layer 3 feature & inference worker
│   ├── execution/
│   │   ├── risk.py                   # Pre-trade risk gatekeeper, 3% drawdown breaker, 150ms stale gate
│   │   ├── state_machine.py          # Deterministic order lifecycle state machine
│   │   ├── ledger.py                 # SQLite WAL persistent trade, latency, fee & risk ledger
│   │   ├── router.py                 # Ed25519 microsecond signer, Smart Order Router & Kill-Switch
│   │   └── main.py                   # Layer 3 & 4 entrypoint (`python3 -m edge.execution.main`)
│   └── gateway/
│       ├── jetson_telemetry.py       # Jetson Orin sysfs/procfs telemetry & `/dev/watchdog` feeder
│       ├── auth.py                   # Ed25519 challenge-response, EdDSA JWTs & TLS 1.3 / mTLS
│       ├── delta.py                  # 10Hz recursive dictionary delta compression
│       └── server.py                 # Layer 5 entrypoint (`python3 -m edge.gateway.server`)
├── deploy/
│   ├── systemd/
│   │   ├── jetson-ingest.service     # Real-time FIFO 90 service pinned to cores 0-3
│   │   ├── jetson-engine.service     # Real-time FIFO 99 service pinned to cores 4-7
│   │   └── jetson-bridge.service     # Real-time FIFO 85 service pinned to cores 8-9
│   └── scripts/
│       ├── setup_jetson_max_perf.sh  # Enables MAXN (`nvpmodel -m 0`), `jetson_clocks` & sysctl tuning
│       ├── watchdog_recovery.sh      # Automated crash, IPC socket, SHM & network recovery supervisor
│       └── build_trt_engines.py      # Builds serialized TensorRT `.engine` plans for Orin GPU/DLA
├── mobile/                           # React Native (Expo + TypeScript) iOS & Android Client
│   ├── App.tsx
│   ├── package.json
│   └── src/
│       ├── types/telemetry.ts
│       ├── services/CryptoAuth.ts
│       ├── services/GatewayClient.ts
│       ├── context/TradingContext.tsx
│       ├── components/               # HardwareHud, CandlestickChart, OrderBookLadder
│       └── screens/                  # DashboardScreen, TerminalScreen, OrdersScreen, EmergencyScreen
└── tests/
    └── test_pipeline.py              # End-to-end automated pytest suite
```

---

## 3. Part I: NVIDIA Jetson Orin Implementation Guide (Edge Server)

### Step 1: Hardware & JetPack 6.x Preparation
1. **Supported Hardware:** NVIDIA Jetson AGX Orin (64GB / 32GB), Jetson Orin NX (16GB), or Jetson Orin Nano (8GB) with an NVMe SSD installed.
2. **Operating System:** Flash **NVIDIA JetPack 6.x (L4T R36.x / Ubuntu 22.04 LTS)** using NVIDIA SDK Manager or the JetPack SD/NVMe image.
3. Verify CUDA 12.x and TensorRT 10.x are installed on your Jetson:
   ```bash
   cat /etc/nv_tegra_release
   nvcc --version
   dpkg -l | grep nvinfer
   ```

### Step 2: MAXN Power Mode, Clocks & Kernel Network Tuning
Clone the repository to `/opt/jetson-hft` on your Jetson Orin and run the hardware optimization script:
```bash
sudo git clone https://github.com/vladutaz/jetson-orin-hft.git /opt/jetson-hft
cd /opt/jetson-hft
sudo chmod +x deploy/scripts/*.sh
sudo ./deploy/scripts/setup_jetson_max_perf.sh
```
**What this script configures:**
- Sets `nvpmodel -m 0` (**MAXN** full-wattage mode unlocking all Cortex-A78AE CPU cores and Ampere GPU SMs).
- Runs `jetson_clocks --fan` to lock CPU, GPU, and LPDDR5 memory controller (EMC) frequencies to maximum, eliminating DVFS frequency-scaling jitter.
- Sets all CPU governors to `performance`.
- Tunes Linux kernel network buffers (`rmem_max=67108864`, `busy_poll=50`, `tcp_low_latency=1`, `sched_rt_runtime_us=-1`).

### Step 3: Python Environment & System Dependencies
Install the required system libraries and Python packages:
```bash
sudo apt-get update && sudo apt-get install -y \
    python3-pip python3-dev python3-venv numactl libzmq3-dev sqlite3

pip3 install -r requirements.txt
pip3 install uvloop
```

### Step 4: Compiling the TensorRT FP16/INT8 Inference Engine
Compile the microstructure alpha neural network directly into a hardware-optimized TensorRT `.engine` plan for your specific Orin SoC:
```bash
# Compile FP16 TensorRT Engine for Orin Ampere GPU Tensor Cores:
sudo python3 deploy/scripts/build_trt_engines.py \
    --output /opt/jetson-hft/models/alpha_tft_fp16.engine

# Or offload to NVIDIA Deep Learning Accelerator (NVDLA Core 0) in INT8/FP16 mode:
sudo python3 deploy/scripts/build_trt_engines.py \
    --output /opt/jetson-hft/models/alpha_tft_fp16.engine \
    --int8 --dla-core 0
```
> **Note on Unified Memory Zero-Copy:** Because the Jetson Orin CPU and GPU share physical LPDDR5 DRAM, `edge/prediction/trt_engine.py` allocates tensors via `cudaHostAllocMapped` (`0x02`) and passes the mapped device pointer (`cudaHostGetDevicePointer`) directly to TensorRT's `execute_async_v3`, eliminating PCIe H2D/D2H copy overhead.

### Step 5: Configuring Exchange Ed25519 Keys & Risk Limits
1. Generate an **Ed25519** API keypair for your exchange sub-account:
   ```bash
   openssl genpkey -algorithm ed25519 -out /opt/jetson-hft/config/ed25519_private.pem
   openssl pkey -in /opt/jetson-hft/config/ed25519_private.pem -pubout -out /opt/jetson-hft/config/ed25519_public.pem
   ```
2. Upload the public key (`ed25519_public.pem`) to your Binance Futures / exchange sub-account API management console with ** Futures Trading** permissions enabled (and withdrawals disabled).
3. Create `/opt/jetson-hft/config/secrets.env` (restricted to `chmod 600`):
   ```bash
   sudo tee /opt/jetson-hft/config/secrets.env > /dev/null << 'EOF'
   JETSON_EXCHANGE_API_KEY="your_exchange_subaccount_api_key"
   JETSON_ED25519_PRIVATE_KEY_PEM="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
   EOF
   sudo chmod 600 /opt/jetson-hft/config/secrets.env
   ```
4. Review `/opt/jetson-hft/config/settings.yaml` to customize `initial_equity_usd`, `max_daily_drawdown_pct` (default `0.03` = 3.0% hard stop), and per-symbol `instrument_limits`. Set `paper_trading: true` under `execution:` during initial staging verification.

### Step 6: Setting Up Secure Peer-to-Peer Connectivity (Tailscale / WireGuard / mTLS)
To connect your smartphone to the Jetson anywhere in the world without opening router ports or exposing a public IP:
1. **Install Tailscale (or WireGuard) on the Jetson Orin:**
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   tailscale ip -4   # Note your Jetson's 100.x.y.z P2P IP address
   ```
2. **(Optional) Generate TLS 1.3 Server & Client mTLS Certificates:**
   ```bash
   mkdir -p /opt/jetson-hft/config/certs
   openssl req -x509 -newkey ed25519 -days 365 -nodes \
       -keyout /opt/jetson-hft/config/certs/server.key \
       -out /opt/jetson-hft/config/certs/server.crt \
       -subj "/CN=jetson-orin.local"
   ```

### Step 7: Installing Real-Time FIFO Systemd Daemons & Watchdog Recovery
Install and enable the three core services and automated recovery supervisor:
```bash
sudo cp /opt/jetson-hft/deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jetson-ingest.service
sudo systemctl enable --now jetson-engine.service
sudo systemctl enable --now jetson-bridge.service
```
Verify real-time process priorities (`chrt -f 99`) and live logs:
```bash
systemctl status jetson-ingest jetson-engine jetson-bridge
journalctl -u jetson-engine -f
```
Schedule the automated recovery script (`deploy/scripts/watchdog_recovery.sh`) via root cron every minute (with 10s sub-loops) to monitor ZeroMQ sockets, `/dev/shm/jetson_l2_ring` freshness, and network tunnels:
```bash
(crontab -l 2>/dev/null; echo "* * * * * /opt/jetson-hft/deploy/scripts/watchdog_recovery.sh >> /var/log/jetson-recovery.log 2>&1") | sudo crontab -
```

---

## 4. Part II: Mobile Client Implementation Guide (iOS & Android Phone)

### Step 1: Prerequisites & Installing Dependencies
1. On your development computer, install **Node.js (v18+)** and **npm**.
2. Install the mobile app dependencies:
   ```bash
   cd mobile
   npm install
   ```

### Step 2: Connecting Your Phone to the Jetson Orin Gateway
1. Install the **Tailscale** (or **WireGuard**) app on your iPhone or Android phone and sign into the same mesh network as your Jetson Orin.
2. Open `mobile/src/context/TradingContext.tsx` and update the `JetsonGatewayClient` endpoint list with your Jetson's Tailscale IP (`100.x.y.z`) and LAN IP:
   ```ts
   new JetsonGatewayClient([
     'wss://100.64.0.10:8443',       // Your Jetson's Tailscale P2P IP
     'wss://192.168.1.50:8443',      // Your Jetson's Local LAN IP
     'ws://100.64.0.10:8443',        // Unencrypted fallback over encrypted Tailscale tunnel
   ])
   ```
3. On first connection, `MobileCryptoAuth` (`mobile/src/services/CryptoAuth.ts`) generates an Ed25519 keypair stored inside the phone's hardware **Secure Enclave / Keystore** (`expo-secure-store`), signs the gateway's cryptographic nonce challenge, and receives a short-lived EdDSA JWT token.

### Step 3: Running on a Physical Phone (Expo Go / Native Build)
- **Quick Development Run (Expo Go):**
  ```bash
  cd mobile
  npx expo start
  ```
  Scan the QR code in the terminal using your iPhone Camera or the Android Expo Go app.
- **Standalone Production Native App Build (iOS / Android):**
  ```bash
  # Android APK / AAB
  npx expo run:android --variant release

  # iOS (macOS with Xcode)
  npx expo run:ios --configuration Release
  ```

### Step 4: Mobile Screens & Biometric Kill-Switch Walkthrough
1. **DASHBOARD (`DashboardScreen.tsx`):**
   - Displays live Net Account Equity, Realized & Unrealized PnL, Daily Sharpe, Win Rate, Margin Utilization, and Daily Drawdown % against the 3.0% circuit breaker limit.
   - **Jetson Orin Hardware HUD (`HardwareHud.tsx`):** Live GPU Temperature (°C), 12-Core CPU Load (%), Unified LPDDR5 Memory Usage (GB), INA3221 SoC Power Draw (Watts), and P2P Network Ping (ms).
2. **TERMINAL (`TerminalScreen.tsx`):**
   - Switch between `BTCUSDT`, `ETHUSDT`, and `SOLUSDT`.
   - Real-time OHLCV Candlestick Chart + Micro-Price overlay (`CandlestickChart.tsx`).
   - Live TensorRT FP16 Alpha readouts: Target Position (`-1.0` to `+1.0`), Confidence %, Order Flow Imbalance (OFI), VPIN toxicity, Depth Skew, FinBERT Sentiment, and TensorRT inference time in microseconds (`µs`).
   - Visualized L2 Order Book Depth Ladder (`OrderBookLadder.tsx`) with cumulative liquidity bars and live trade tape.
3. **ORDERS (`OrdersScreen.tsx`):**
   - **Discretionary Manual Override:** Dispatch manual `SOR POST-ONLY` or `MARKET` Buy/Sell orders directly from your phone.
   - **Active Orders & Fills Log:** View open resting orders (with one-tap Cancel) and historical fills with Ed25519 wire latency (`µs`) and execution slippage (`bps`).
4. **STOCKS & CPI (`PortfolioMacroScreen.tsx` & `edge/execution/portfolio_macro.py`):**
   - **Save Invested Stocks (`save_invested_stock`):** Save your stock holdings (`Ticker`, `Company Name`, `Shares`, `Avg Buy Price`, `Current Price`, and `Country` such as `US`, `EU`, `UK`, `RO`, `JP`, `CA`) into the persistent SQLite WAL database (`invested_stocks` table).
   - **Trusted Multi-Source Market News & Guru Catalysts:** Continuously scrapes **Seeking Alpha** (`seekingalpha.com`), **GuruFocus / Trading Guru** (`gurufocus.com`), **TradingView**, **SEC EDGAR**, **US BLS / Federal Reserve**, **Eurostat**, **MarketWatch / Dow Jones**, **CNBC**, and **Investing.com** with source credibility weighting.
   - **Sovereign Inflation, CPI & Tax Change Notifications:** Automatically monitors each saved stock's home country for changes in **Annual Inflation Rate (%)**, **Consumer Price Index (CPI YoY & MoM %)**, **Central Bank Policy Rate (%)**, **Corporate Income Tax (%)**, and **Capital Gains / Dividend Tax (%)**. Whenever a stock's status changes or its country's CPI, inflation, or tax rate shifts, the Jetson emits a real-time `PortfolioNotification` to your phone's top alert banner and notification log listing all affected holdings.
5. **EMERGENCY KILL-SWITCH (`EmergencyScreen.tsx`):**
   - **Two-Factor Physical Confirmation:**
     1. Tap **STEP 1: UNLOCK WITH FACEID / BIOMETRICS** to authenticate via `expo-local-authentication`.
     2. Press and hold the red **EMERGENCY FLATTEN** button continuously for **2.0 seconds** (with haptic feedback).
   - **Action on Jetson:** Immediately sends `EMERGENCY_FLATTEN` to the `jetson-engine` real-time daemon (`chrt -f 99`), canceling all open orders, market-closing all open perpetual positions (`reduceOnly=true`), and locking the risk gatekeeper into `HALTED` mode.

---

## 5. Subsystems Deep-Dive

| Layer | Module | Key Institutional Capabilities |
| :--- | :--- | :--- |
| **Layer 1** | `edge/ingestion/` | Multi-venue WebSocket L2 delta reconstruction (`U`, `u`, `pu`), CRC32 checksum & crossed-book parity validation, Token-Bucket EDGAR/RSS scraper, `<15ms` FinBERT sentiment polarity. |
| **Layer 2** | `edge/bus/` | ZeroMQ `ipc:///tmp/` PUB/SUB & PUSH/PULL sockets + lock-free POSIX shared memory ring buffer (`/dev/shm/jetson_l2_ring`) with 136-byte aligned binary slots. |
| **Layer 3** | `edge/prediction/` | Online $O(1)$ OFI, VPIN, Micro-price, 1s/5s/30s/300s VWAP, Book Depth Skew, Realized Volatility + TensorRT FP16/INT8 inference using zero-copy `cudaHostAllocMapped`. |
| **Layer 4** | `edge/execution/` | Hardcoded Pre-Trade Risk Gatekeeper (3.0% drawdown breaker, 150ms stale feed gate, fat-finger & slippage filters), Ed25519 microsecond signing, Passive Maker Post-Only SOR loop, SQLite WAL ledger. |
| **Layer 5** | `edge/gateway/` | TLS 1.3 / mTLS WebSocket server, Ed25519 challenge-response + short-lived EdDSA JWTs, 10Hz recursive delta compression, Linux sysfs/INA3221 telemetry reader, `/dev/watchdog` heartbeat. |
| **Layer 6** | `mobile/` | Dark-themed React Native + TypeScript app with Hardware HUD, Candlestick chart, L2 Depth Ladder, Manual Order Override, and Biometric + 2s Hold Emergency Kill-Switch. |

---

## 6. Testing & Verification

Run the automated end-to-end verification suite covering L2 order book sequence reconstruction, gap detection, POSIX shared memory ring buffers, NLP sentiment scoring, TensorRT feature inference, pre-trade risk gates, Smart Order Routing, Kill-Switch flattening, Ed25519/JWT authentication, and 10Hz delta compression:

```bash
pytest -v
```
