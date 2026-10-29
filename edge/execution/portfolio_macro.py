from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from edge.execution.ledger import ExecutionWallLedger


@dataclass
class CountryMacroMetrics:
    """
    Sovereign Macroeconomic & Tax Policy metrics for a specific country (`US`, `EU`, `UK`, `RO`, `JP`, `CA`, `CH`, etc.).
    """
    country_code: str
    country_name: str
    currency: str
    inflation_rate_yoy_pct: float      # Headline Annual Inflation Rate (%)
    cpi_index_yoy_pct: float           # Consumer Price Index YoY (%)
    cpi_mom_pct: float                 # Consumer Price Index MoM (%)
    central_bank_rate_pct: float       # Policy Interest Rate (%)
    corporate_tax_rate_pct: float      # Statutory Corporate Income Tax (%)
    capital_gains_tax_pct: float       # Investor Capital Gains / Dividend Tax (%)
    last_updated_source: str
    updated_ts_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InvestedStock:
    """
    Represents a user's saved equity/stock investment linked to its home country for
    automatic status tracking and CPI / Inflation / Tax change notifications.
    """
    ticker: str
    company_name: str
    country_code: str
    shares: float
    avg_buy_price: float
    current_price: float
    currency: str = "USD"
    sector: str = "Technology"
    status: str = "STABLE"             # OUTPERFORMING, STABLE, WATCH, DRAWDOWN_ALERT, MACRO_HEADWIND, MACRO_TAILWIND
    sentiment_score: float = 0.0       # Latest Seeking Alpha / Trading Guru sentiment (-1.0 to +1.0)
    last_catalyst_headline: str = ""
    last_catalyst_source: str = ""
    updated_ts_ms: int = 0

    @property
    def cost_basis(self) -> float:
        return self.shares * self.avg_buy_price

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_buy_price) * self.shares

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.avg_buy_price <= 0.0:
            return 0.0
        return ((self.current_price - self.avg_buy_price) / self.avg_buy_price) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["cost_basis"] = round(self.cost_basis, 2)
        d["market_value"] = round(self.market_value, 2)
        d["unrealized_pnl"] = round(self.unrealized_pnl, 2)
        d["unrealized_pnl_pct"] = round(self.unrealized_pnl_pct, 2)
        return d


@dataclass
class PortfolioNotification:
    """
    Real-time notification emitted when a saved stock's status changes or when
    inflation, CPI, or tax rates change in the stock's respective country.
    """
    notification_id: str
    category: str          # STOCK_STATUS, INFLATION_ALERT, CPI_RELEASE, TAX_POLICY_CHANGE, GURU_CATALYST
    severity: str          # INFO, WARNING, CRITICAL, BULLISH_CATALYST
    ticker: str            # Specific stock ticker or Country-wide affected tickers
    country_code: str
    title: str
    message: str
    source: str
    metric_name: str       # e.g. "CPI_YOY", "INFLATION_RATE", "CAPITAL_GAINS_TAX", "UNREALIZED_PNL_PCT"
    previous_value: float
    new_value: float
    affected_tickers: List[str]
    ts_ms: int
    acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DEFAULT_COUNTRY_MACRO: Dict[str, CountryMacroMetrics] = {
    "US": CountryMacroMetrics(
        country_code="US",
        country_name="United States",
        currency="USD",
        inflation_rate_yoy_pct=2.6,
        cpi_index_yoy_pct=2.6,
        cpi_mom_pct=0.2,
        central_bank_rate_pct=4.75,
        corporate_tax_rate_pct=21.0,
        capital_gains_tax_pct=20.0,
        last_updated_source="US Bureau of Labor Statistics (BLS) / Federal Reserve",
        updated_ts_ms=int(time.time() * 1000),
    ),
    "EU": CountryMacroMetrics(
        country_code="EU",
        country_name="Eurozone (ECB)",
        currency="EUR",
        inflation_rate_yoy_pct=2.0,
        cpi_index_yoy_pct=2.0,
        cpi_mom_pct=0.1,
        central_bank_rate_pct=3.25,
        corporate_tax_rate_pct=25.0,
        capital_gains_tax_pct=26.0,
        last_updated_source="Eurostat / European Central Bank",
        updated_ts_ms=int(time.time() * 1000),
    ),
    "UK": CountryMacroMetrics(
        country_code="UK",
        country_name="United Kingdom",
        currency="GBP",
        inflation_rate_yoy_pct=2.3,
        cpi_index_yoy_pct=2.3,
        cpi_mom_pct=0.3,
        central_bank_rate_pct=4.75,
        corporate_tax_rate_pct=25.0,
        capital_gains_tax_pct=24.0,
        last_updated_source="UK Office for National Statistics (ONS) / Bank of England",
        updated_ts_ms=int(time.time() * 1000),
    ),
    "RO": CountryMacroMetrics(
        country_code="RO",
        country_name="Romania",
        currency="RON",
        inflation_rate_yoy_pct=4.7,
        cpi_index_yoy_pct=4.7,
        cpi_mom_pct=0.4,
        central_bank_rate_pct=6.50,
        corporate_tax_rate_pct=16.0,
        capital_gains_tax_pct=10.0,
        last_updated_source="INSSE / National Bank of Romania (BNR)",
        updated_ts_ms=int(time.time() * 1000),
    ),
    "JP": CountryMacroMetrics(
        country_code="JP",
        country_name="Japan",
        currency="JPY",
        inflation_rate_yoy_pct=2.3,
        cpi_index_yoy_pct=2.3,
        cpi_mom_pct=0.2,
        central_bank_rate_pct=0.25,
        corporate_tax_rate_pct=23.2,
        capital_gains_tax_pct=20.315,
        last_updated_source="Statistics Bureau of Japan / Bank of Japan",
        updated_ts_ms=int(time.time() * 1000),
    ),
    "CA": CountryMacroMetrics(
        country_code="CA",
        country_name="Canada",
        currency="CAD",
        inflation_rate_yoy_pct=2.0,
        cpi_index_yoy_pct=2.0,
        cpi_mom_pct=0.1,
        central_bank_rate_pct=3.75,
        corporate_tax_rate_pct=26.5,
        capital_gains_tax_pct=25.0,
        last_updated_source="Statistics Canada / Bank of Canada",
        updated_ts_ms=int(time.time() * 1000),
    ),
}


class PortfolioAndMacroMonitor:
    """
    Persistent Invested Stocks & Sovereign Macro/CPI/Tax Notification Engine.
    - Saves user's invested stocks in SQLite WAL (`save_invested_stock`) and tracks their status.
    - Monitors sovereign Inflation Rate, CPI (YoY/MoM), Central Bank Rate, Corporate Tax,
      and Capital Gains/Dividend Tax in each invested stock's respective country.
    - Parses trusted financial & macro feeds (Seeking Alpha, GuruFocus, BLS, Eurostat, ONS, SEC EDGAR)
      for CPI releases, inflation shifts, tax policy changes, and company earnings/catalysts.
    - Dispatches instant update notifications (`PortfolioNotification`) to the user's mobile phone
      and adjusts trading engine sentiment/risk weights.
    """

    COUNTRY_ALIASES: Dict[str, List[str]] = {
        "US": ["u.s.", "us ", "united states", "american", "fed ", "federal reserve", "bls", "irs", "treasury", "wall street"],
        "EU": ["eurozone", "european union", "ecb", "eurostat", "germany", "france", "europe"],
        "UK": ["u.k.", "uk ", "united kingdom", "britain", "british", "bank of england", "boe", "ons", "hmrc", "chancellor"],
        "RO": ["romania", "romanian", "bnr", "insse", "bucharest", "anaf"],
        "JP": ["japan", "japanese", "bank of japan", "boj", "tokyo"],
        "CA": ["canada", "canadian", "bank of canada", "statcan", "ottawa"],
    }

    def __init__(
        self,
        ledger: ExecutionWallLedger,
        on_notification: Optional[Callable[[PortfolioNotification], None]] = None,
    ) -> None:
        self.ledger = ledger
        self.on_notification = on_notification
        self.countries: Dict[str, CountryMacroMetrics] = {}
        self.stocks: Dict[str, InvestedStock] = {}
        self._load_or_seed_state()

    def _load_or_seed_state(self) -> None:
        # 1. Load or seed sovereign country macro profiles
        stored_countries = self.ledger.load_country_macro_all()
        for code, default_metric in DEFAULT_COUNTRY_MACRO.items():
            if code in stored_countries:
                self.countries[code] = CountryMacroMetrics(**stored_countries[code])
            else:
                self.countries[code] = default_metric
                self.ledger.upsert_country_macro(default_metric.to_dict())

        # 2. Load saved invested stocks (or seed initial institutional portfolio if empty)
        stored_stocks = self.ledger.load_invested_stocks_all()
        if stored_stocks:
            for row in stored_stocks:
                stk = InvestedStock(
                    ticker=row["ticker"],
                    company_name=row["company_name"],
                    country_code=row["country_code"],
                    shares=float(row["shares"]),
                    avg_buy_price=float(row["avg_buy_price"]),
                    current_price=float(row["current_price"]),
                    currency=row["currency"],
                    sector=row["sector"],
                    status=row["status"],
                    sentiment_score=float(row["sentiment_score"]),
                    last_catalyst_headline=row["last_catalyst_headline"],
                    last_catalyst_source=row["last_catalyst_source"],
                    updated_ts_ms=int(row["updated_ts_ms"]),
                )
                self.stocks[stk.ticker] = stk
        else:
            # Default starter portfolio so the user immediately sees live tracking & notifications
            self.save_invested_stock(
                ticker="NVDA",
                company_name="NVIDIA Corporation",
                country_code="US",
                shares=45.0,
                avg_buy_price=118.50,
                current_price=138.60,
                currency="USD",
                sector="Semiconductors & AI",
                emit_welcome_notification=False,
            )
            self.save_invested_stock(
                ticker="AAPL",
                company_name="Apple Inc.",
                country_code="US",
                shares=60.0,
                avg_buy_price=212.00,
                current_price=231.40,
                currency="USD",
                sector="Consumer Technology",
                emit_welcome_notification=False,
            )
            self.save_invested_stock(
                ticker="ASML",
                company_name="ASML Holding N.V.",
                country_code="EU",
                shares=12.0,
                avg_buy_price=720.00,
                current_price=695.50,
                currency="EUR",
                sector="Semiconductor Lithography",
                emit_welcome_notification=False,
            )

    def save_invested_stock(
        self,
        ticker: str,
        company_name: str,
        country_code: str,
        shares: float,
        avg_buy_price: float,
        current_price: Optional[float] = None,
        currency: str = "USD",
        sector: str = "Equities",
        emit_welcome_notification: bool = True,
    ) -> InvestedStock:
        """
        Saves or updates an invested stock in the persistent SQLite WAL ledger, evaluates its
        current PnL & macroeconomic status in its home country, and emits a status notification.
        """
        clean_ticker = ticker.strip().upper()
        clean_country = country_code.strip().upper()
        if clean_country not in self.countries:
            self.countries[clean_country] = CountryMacroMetrics(
                country_code=clean_country,
                country_name=clean_country,
                currency=currency,
                inflation_rate_yoy_pct=2.5,
                cpi_index_yoy_pct=2.5,
                cpi_mom_pct=0.2,
                central_bank_rate_pct=4.0,
                corporate_tax_rate_pct=21.0,
                capital_gains_tax_pct=20.0,
                last_updated_source="Initial Country Baseline",
                updated_ts_ms=int(time.time() * 1000),
            )
            self.ledger.upsert_country_macro(self.countries[clean_country].to_dict())

        px = float(current_price) if (current_price is not None and current_price > 0) else float(avg_buy_price)
        prev_stock = self.stocks.get(clean_ticker)
        status = self._evaluate_stock_status(avg_buy_price, px, clean_country, prev_stock.sentiment_score if prev_stock else 0.0)

        stock = InvestedStock(
            ticker=clean_ticker,
            company_name=company_name.strip() or clean_ticker,
            country_code=clean_country,
            shares=float(shares),
            avg_buy_price=float(avg_buy_price),
            current_price=px,
            currency=currency.strip().upper(),
            sector=sector.strip(),
            status=status,
            sentiment_score=prev_stock.sentiment_score if prev_stock else 0.0,
            last_catalyst_headline=prev_stock.last_catalyst_headline if prev_stock else "Position saved and actively monitored.",
            last_catalyst_source=prev_stock.last_catalyst_source if prev_stock else "Portfolio Monitor",
            updated_ts_ms=int(time.time() * 1000),
        )
        self.stocks[clean_ticker] = stock
        self.ledger.upsert_invested_stock(stock.to_dict())

        if emit_welcome_notification:
            macro = self.countries[clean_country]
            self._emit_notification(
                category="STOCK_STATUS",
                severity="INFO",
                ticker=clean_ticker,
                country_code=clean_country,
                title=f"Saved {clean_ticker} ({stock.company_name}) — Status: {stock.status}",
                message=(
                    f"Tracking {stock.shares:g} shares of {clean_ticker} (Avg: {stock.avg_buy_price:.2f} {stock.currency}, "
                    f"Now: {stock.current_price:.2f} {stock.currency}, PnL: {stock.unrealized_pnl_pct:+.2f}%). "
                    f"Monitoring {clean_country} Macro: Inflation {macro.inflation_rate_yoy_pct:.1f}%, "
                    f"CPI YoY {macro.cpi_index_yoy_pct:.1f}%, CapGains Tax {macro.capital_gains_tax_pct:.1f}%."
                ),
                source="Portfolio Monitor",
                metric_name="UNREALIZED_PNL_PCT",
                previous_value=0.0,
                new_value=round(stock.unrealized_pnl_pct, 2),
                affected_tickers=[clean_ticker],
            )
        return stock

    def remove_invested_stock(self, ticker: str) -> bool:
        clean_ticker = ticker.strip().upper()
        existed = self.stocks.pop(clean_ticker, None) is not None
        self.ledger.delete_invested_stock(clean_ticker)
        return existed

    def update_stock_price_and_status(
        self,
        ticker: str,
        new_price: float,
        sentiment_score: Optional[float] = None,
        catalyst_headline: Optional[str] = None,
        catalyst_source: Optional[str] = None,
    ) -> Optional[InvestedStock]:
        """
        Updates the current market price and/or Seeking Alpha / Trading Guru sentiment for a saved stock,
        and emits a status notification if the stock crosses a status threshold or receives a new catalyst.
        """
        clean_ticker = ticker.strip().upper()
        stock = self.stocks.get(clean_ticker)
        if stock is None:
            return None

        prev_status = stock.status
        prev_pnl_pct = stock.unrealized_pnl_pct
        if new_price > 0.0:
            stock.current_price = float(new_price)
        if sentiment_score is not None:
            stock.sentiment_score = round(0.5 * stock.sentiment_score + 0.5 * float(sentiment_score), 4)
        if catalyst_headline:
            stock.last_catalyst_headline = catalyst_headline[:240]
        if catalyst_source:
            stock.last_catalyst_source = catalyst_source

        stock.status = self._evaluate_stock_status(
            stock.avg_buy_price,
            stock.current_price,
            stock.country_code,
            stock.sentiment_score,
        )
        stock.updated_ts_ms = int(time.time() * 1000)
        self.ledger.upsert_invested_stock(stock.to_dict())

        new_pnl_pct = stock.unrealized_pnl_pct
        status_changed = stock.status != prev_status
        large_pnl_swing = abs(new_pnl_pct - prev_pnl_pct) >= 3.0

        if status_changed or large_pnl_swing or catalyst_headline:
            sev = "WARNING" if "ALERT" in stock.status or "HEADWIND" in stock.status else (
                "BULLISH_CATALYST" if stock.status == "OUTPERFORMING" else "INFO"
            )
            self._emit_notification(
                category="GURU_CATALYST" if catalyst_headline else "STOCK_STATUS",
                severity=sev,
                ticker=clean_ticker,
                country_code=stock.country_code,
                title=f"{clean_ticker} Status Update: {stock.status} ({new_pnl_pct:+.2f}%)",
                message=(
                    f"{stock.company_name} ({clean_ticker}) is now at {stock.current_price:.2f} {stock.currency} "
                    f"(PnL: {stock.unrealized_pnl:+.2f} {stock.currency} / {new_pnl_pct:+.2f}%). "
                    + (f"Catalyst [{stock.last_catalyst_source}]: {stock.last_catalyst_headline}" if catalyst_headline else "")
                ),
                source=catalyst_source or "Portfolio Monitor",
                metric_name="UNREALIZED_PNL_PCT",
                previous_value=round(prev_pnl_pct, 2),
                new_value=round(new_pnl_pct, 2),
                affected_tickers=[clean_ticker],
            )
        return stock

    def update_country_macro(
        self,
        country_code: str,
        inflation_rate_yoy_pct: Optional[float] = None,
        cpi_index_yoy_pct: Optional[float] = None,
        cpi_mom_pct: Optional[float] = None,
        central_bank_rate_pct: Optional[float] = None,
        corporate_tax_rate_pct: Optional[float] = None,
        capital_gains_tax_pct: Optional[float] = None,
        source: str = "Macroeconomic Feed",
        headline: str = "",
    ) -> List[PortfolioNotification]:
        """
        Updates macroeconomic or tax policy metrics for a country.
        Whenever Inflation, CPI, Central Bank Rate, or Tax rates change, automatically identifies
        all saved stocks in that country, updates their status, and sends detailed notifications!
        """
        code = country_code.strip().upper()
        if code not in self.countries:
            self.countries[code] = CountryMacroMetrics(
                country_code=code,
                country_name=code,
                currency="USD",
                inflation_rate_yoy_pct=2.5,
                cpi_index_yoy_pct=2.5,
                cpi_mom_pct=0.2,
                central_bank_rate_pct=4.0,
                corporate_tax_rate_pct=21.0,
                capital_gains_tax_pct=20.0,
                last_updated_source=source,
                updated_ts_ms=int(time.time() * 1000),
            )

        macro = self.countries[code]
        affected = [s.ticker for s in self.stocks.values() if s.country_code == code]
        emitted: List[PortfolioNotification] = []

        # Helper to check and record changes for each sovereign indicator
        changes: List[Tuple[str, str, float, float, str]] = []

        if inflation_rate_yoy_pct is not None and abs(inflation_rate_yoy_pct - macro.inflation_rate_yoy_pct) >= 1e-4:
            changes.append(
                ("INFLATION_ALERT", "INFLATION_RATE_YOY_PCT", macro.inflation_rate_yoy_pct, float(inflation_rate_yoy_pct), "Inflation Rate (YoY)")
            )
            macro.inflation_rate_yoy_pct = float(inflation_rate_yoy_pct)

        if cpi_index_yoy_pct is not None and abs(cpi_index_yoy_pct - macro.cpi_index_yoy_pct) >= 1e-4:
            changes.append(
                ("CPI_RELEASE", "CPI_INDEX_YOY_PCT", macro.cpi_index_yoy_pct, float(cpi_index_yoy_pct), "CPI Index (YoY)")
            )
            macro.cpi_index_yoy_pct = float(cpi_index_yoy_pct)

        if cpi_mom_pct is not None and abs(cpi_mom_pct - macro.cpi_mom_pct) >= 1e-4:
            changes.append(
                ("CPI_RELEASE", "CPI_MOM_PCT", macro.cpi_mom_pct, float(cpi_mom_pct), "Monthly CPI (MoM)")
            )
            macro.cpi_mom_pct = float(cpi_mom_pct)

        if central_bank_rate_pct is not None and abs(central_bank_rate_pct - macro.central_bank_rate_pct) >= 1e-4:
            changes.append(
                ("INFLATION_ALERT", "CENTRAL_BANK_RATE_PCT", macro.central_bank_rate_pct, float(central_bank_rate_pct), "Central Bank Policy Rate")
            )
            macro.central_bank_rate_pct = float(central_bank_rate_pct)

        if corporate_tax_rate_pct is not None and abs(corporate_tax_rate_pct - macro.corporate_tax_rate_pct) >= 1e-4:
            changes.append(
                ("TAX_POLICY_CHANGE", "CORPORATE_TAX_RATE_PCT", macro.corporate_tax_rate_pct, float(corporate_tax_rate_pct), "Corporate Income Tax Rate")
            )
            macro.corporate_tax_rate_pct = float(corporate_tax_rate_pct)

        if capital_gains_tax_pct is not None and abs(capital_gains_tax_pct - macro.capital_gains_tax_pct) >= 1e-4:
            changes.append(
                ("TAX_POLICY_CHANGE", "CAPITAL_GAINS_TAX_PCT", macro.capital_gains_tax_pct, float(capital_gains_tax_pct), "Capital Gains / Dividend Tax Rate")
            )
            macro.capital_gains_tax_pct = float(capital_gains_tax_pct)

        if not changes:
            return emitted

        macro.last_updated_source = source
        macro.updated_ts_ms = int(time.time() * 1000)
        self.ledger.upsert_country_macro(macro.to_dict())

        # Re-evaluate all saved stocks domiciled in this country
        for stk in self.stocks.values():
            if stk.country_code == code:
                stk.status = self._evaluate_stock_status(
                    stk.avg_buy_price, stk.current_price, code, stk.sentiment_score
                )
                stk.updated_ts_ms = macro.updated_ts_ms
                self.ledger.upsert_invested_stock(stk.to_dict())

        for category, metric_key, old_val, new_val, label in changes:
            delta = new_val - old_val
            direction = "increased" if delta > 0 else "decreased"
            # Rising inflation/CPI/taxes is a headwind (WARNING/CRITICAL); cooling inflation/taxes is a tailwind
            severity = "CRITICAL" if (delta > 0 and abs(delta) >= 0.5) else (
                "WARNING" if delta > 0 else "BULLISH_CATALYST"
            )
            tickers_str = ", ".join(affected) if affected else "No currently saved stocks in this jurisdiction"
            extra_headline = f" Source headline: \"{headline}\"" if headline else ""

            notif = self._emit_notification(
                category=category,
                severity=severity,
                ticker=affected[0] if len(affected) == 1 else (",".join(affected[:3]) or code),
                country_code=code,
                title=f"[{code}] {label} {direction} from {old_val:.2f}% to {new_val:.2f}%",
                message=(
                    f"{macro.country_name} ({code}) {label} {direction} by {delta:+.2f}% "
                    f"(from {old_val:.2f}% to {new_val:.2f}%) via {source}. "
                    f"Affected invested stocks in your portfolio: [{tickers_str}].{extra_headline}"
                ),
                source=source,
                metric_name=metric_key,
                previous_value=round(old_val, 3),
                new_value=round(new_val, 3),
                affected_tickers=affected,
            )
            emitted.append(notif)

        return emitted

    def scan_headline_for_macro_and_stock_catalysts(
        self,
        headline: str,
        source: str,
        sentiment_score: float,
    ) -> List[PortfolioNotification]:
        """
        Inspects incoming headlines from Seeking Alpha, GuruFocus, MarketWatch, BLS, Eurostat,
        and SEC EDGAR for:
          1. Direct mentions of any saved stock ticker or company name in `self.stocks`.
          2. Country-level CPI, Inflation Rate, Central Bank Rate, or Tax rate changes.
        """
        notifications: List[PortfolioNotification] = []
        lower_hl = headline.lower()

        # 1. Check if any saved stock is mentioned in the headline
        for ticker, stock in self.stocks.items():
            company_first = stock.company_name.split()[0].lower() if stock.company_name else ""
            ticker_pattern = rf"\b{re.escape(ticker.lower())}\b"
            if re.search(ticker_pattern, lower_hl) or (len(company_first) >= 4 and company_first in lower_hl):
                self.update_stock_price_and_status(
                    ticker=ticker,
                    new_price=stock.current_price,
                    sentiment_score=sentiment_score,
                    catalyst_headline=headline,
                    catalyst_source=source,
                )

        # 2. Check for CPI / Inflation / Tax policy changes in tracked countries
        detected_country = self._detect_country_from_headline(lower_hl)
        pct_matches = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", headline)]
        if not pct_matches:
            return notifications

        val = pct_matches[0]
        if any(k in lower_hl for k in ("cpi", "consumer price index")):
            if "mom" in lower_hl or "month-over-month" in lower_hl or "monthly" in lower_hl:
                notifications.extend(
                    self.update_country_macro(
                        country_code=detected_country,
                        cpi_mom_pct=val,
                        source=source,
                        headline=headline,
                    )
                )
            else:
                notifications.extend(
                    self.update_country_macro(
                        country_code=detected_country,
                        cpi_index_yoy_pct=val,
                        inflation_rate_yoy_pct=val,
                        source=source,
                        headline=headline,
                    )
                )
        elif "inflation" in lower_hl:
            notifications.extend(
                self.update_country_macro(
                    country_code=detected_country,
                    inflation_rate_yoy_pct=val,
                    source=source,
                    headline=headline,
                )
            )
        elif any(k in lower_hl for k in ("capital gains tax", "dividend tax", "investment tax")):
            notifications.extend(
                self.update_country_macro(
                    country_code=detected_country,
                    capital_gains_tax_pct=val,
                    source=source,
                    headline=headline,
                )
            )
        elif any(k in lower_hl for k in ("corporate tax", "business tax", "statutory tax")):
            notifications.extend(
                self.update_country_macro(
                    country_code=detected_country,
                    corporate_tax_rate_pct=val,
                    source=source,
                    headline=headline,
                )
            )

        return notifications

    def _detect_country_from_headline(self, lower_hl: str) -> str:
        for code, aliases in self.COUNTRY_ALIASES.items():
            if any(alias in lower_hl for alias in aliases):
                return code
        return "US"

    def _evaluate_stock_status(
        self,
        avg_buy_price: float,
        current_price: float,
        country_code: str,
        sentiment_score: float,
    ) -> str:
        pnl_pct = ((current_price - avg_buy_price) / avg_buy_price * 100.0) if avg_buy_price > 0 else 0.0
        macro = self.countries.get(country_code)

        if pnl_pct <= -8.0:
            return "DRAWDOWN_ALERT"
        if macro and (macro.inflation_rate_yoy_pct >= 4.0 or macro.capital_gains_tax_pct >= 28.0):
            if pnl_pct < 2.0:
                return "MACRO_HEADWIND"
        if pnl_pct >= 8.0 or sentiment_score >= 0.45:
            return "OUTPERFORMING"
        if pnl_pct <= -3.5 or sentiment_score <= -0.40:
            return "WATCH"
        return "STABLE"

    def _emit_notification(
        self,
        category: str,
        severity: str,
        ticker: str,
        country_code: str,
        title: str,
        message: str,
        source: str,
        metric_name: str,
        previous_value: float,
        new_value: float,
        affected_tickers: List[str],
    ) -> PortfolioNotification:
        notif = PortfolioNotification(
            notification_id=f"ntf-{uuid.uuid4().hex[:10]}",
            category=category,
            severity=severity,
            ticker=ticker,
            country_code=country_code,
            title=title,
            message=message,
            source=source,
            metric_name=metric_name,
            previous_value=previous_value,
            new_value=new_value,
            affected_tickers=affected_tickers,
            ts_ms=int(time.time() * 1000),
            acknowledged=False,
        )
        self.ledger.insert_portfolio_notification(notif.to_dict())
        if self.on_notification is not None:
            self.on_notification(notif)
        return notif

    def get_portfolio_snapshot(self) -> Dict[str, Any]:
        return {
            "invested_stocks": [s.to_dict() for s in self.stocks.values()],
            "country_macro": {code: m.to_dict() for code, m in self.countries.items()},
            "notifications": self.ledger.get_portfolio_notifications(limit=40),
        }
