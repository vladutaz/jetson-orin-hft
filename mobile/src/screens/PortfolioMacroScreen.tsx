import React, { useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useTrading } from '../context/TradingContext';

type SubView = 'PORTFOLIO' | 'MACRO_ALERTS' | 'GURU_NEWS';

const COUNTRIES = ['US', 'EU', 'UK', 'RO', 'JP', 'CA'];

export const PortfolioMacroScreen: React.FC = () => {
  const {
    telemetry,
    saveInvestedStock,
    removeInvestedStock,
    updateCountryMacro,
  } = useTrading();

  const [subView, setSubView] = useState<SubView>('PORTFOLIO');

  // Form state for saving a new or updated invested stock
  const [ticker, setTicker] = useState<string>('');
  const [companyName, setCompanyName] = useState<string>('');
  const [countryCode, setCountryCode] = useState<string>('US');
  const [shares, setShares] = useState<string>('10');
  const [avgBuyPx, setAvgBuyPx] = useState<string>('150.00');
  const [currentPx, setCurrentPx] = useState<string>('155.00');

  // Form state for simulating/updating country CPI / Inflation / Tax rates
  const [selectedMacroCountry, setSelectedMacroCountry] = useState<string>('US');
  const [newInflationInput, setNewInflationInput] = useState<string>('2.9');
  const [newTaxInput, setNewTaxInput] = useState<string>('20.0');

  const handleSaveStock = () => {
    if (!ticker.trim()) return;
    const sh = parseFloat(shares);
    const avg = parseFloat(avgBuyPx);
    const cur = parseFloat(currentPx);
    if (isNaN(sh) || sh <= 0 || isNaN(avg) || avg <= 0) return;

    saveInvestedStock({
      ticker: ticker.trim().toUpperCase(),
      company_name: companyName.trim() || ticker.trim().toUpperCase(),
      country_code: countryCode,
      shares: sh,
      avg_buy_price: avg,
      current_price: isNaN(cur) || cur <= 0 ? avg : cur,
      currency: countryCode === 'EU' ? 'EUR' : countryCode === 'UK' ? 'GBP' : countryCode === 'RO' ? 'RON' : 'USD',
    });
    setTicker('');
    setCompanyName('');
  };

  const handleSimulateMacroUpdate = () => {
    const inf = parseFloat(newInflationInput);
    const tax = parseFloat(newTaxInput);
    updateCountryMacro({
      country_code: selectedMacroCountry,
      inflation_rate_yoy_pct: isNaN(inf) ? undefined : inf,
      cpi_index_yoy_pct: isNaN(inf) ? undefined : inf,
      capital_gains_tax_pct: isNaN(tax) ? undefined : tax,
      source: 'Sovereign CPI / Tax Release Wire',
    });
    setSubView('MACRO_ALERTS');
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {/* Sub-Navigation Pills */}
      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tabPill, subView === 'PORTFOLIO' && styles.tabPillActive]}
          onPress={() => setSubView('PORTFOLIO')}
        >
          <Text style={[styles.tabPillText, subView === 'PORTFOLIO' && styles.tabPillTextActive]}>
            SAVED STOCKS ({telemetry.invested_stocks.length})
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tabPill, subView === 'MACRO_ALERTS' && styles.tabPillActive]}
          onPress={() => setSubView('MACRO_ALERTS')}
        >
          <Text
            style={[styles.tabPillText, subView === 'MACRO_ALERTS' && styles.tabPillTextActive]}
          >
            CPI / TAX ALERTS ({telemetry.notifications.length})
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tabPill, subView === 'GURU_NEWS' && styles.tabPillActive]}
          onPress={() => setSubView('GURU_NEWS')}
        >
          <Text style={[styles.tabPillText, subView === 'GURU_NEWS' && styles.tabPillTextActive]}>
            SEEKING ALPHA / GURU
          </Text>
        </TouchableOpacity>
      </View>

      {subView === 'PORTFOLIO' && (
        <>
          {/* Add / Save Invested Stock Card */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>SAVE INVESTED STOCK & COUNTRY MACRO MONITOR</Text>
            <View style={styles.row}>
              <View style={styles.col30}>
                <Text style={styles.label}>TICKER</Text>
                <TextInput
                  style={styles.input}
                  value={ticker}
                  onChangeText={setTicker}
                  placeholder="e.g. MSFT"
                  placeholderTextColor="#475569"
                  autoCapitalize="characters"
                />
              </View>
              <View style={styles.col68}>
                <Text style={styles.label}>COMPANY NAME</Text>
                <TextInput
                  style={styles.input}
                  value={companyName}
                  onChangeText={setCompanyName}
                  placeholder="e.g. Microsoft Corp."
                  placeholderTextColor="#475569"
                />
              </View>
            </View>

            <Text style={styles.label}>COUNTRY (FOR CPI, INFLATION & TAX ALERTS)</Text>
            <View style={styles.countrySelector}>
              {COUNTRIES.map((c) => (
                <TouchableOpacity
                  key={c}
                  style={[styles.countryBtn, countryCode === c && styles.countryBtnActive]}
                  onPress={() => setCountryCode(c)}
                >
                  <Text
                    style={[
                      styles.countryBtnText,
                      countryCode === c && styles.countryBtnTextActive,
                    ]}
                  >
                    {c}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={styles.row}>
              <View style={styles.col30}>
                <Text style={styles.label}>SHARES</Text>
                <TextInput
                  style={styles.input}
                  value={shares}
                  onChangeText={setShares}
                  keyboardType="decimal-pad"
                />
              </View>
              <View style={styles.col30}>
                <Text style={styles.label}>AVG BUY PX</Text>
                <TextInput
                  style={styles.input}
                  value={avgBuyPx}
                  onChangeText={setAvgBuyPx}
                  keyboardType="decimal-pad"
                />
              </View>
              <View style={styles.col30}>
                <Text style={styles.label}>CURRENT PX</Text>
                <TextInput
                  style={styles.input}
                  value={currentPx}
                  onChangeText={setCurrentPx}
                  keyboardType="decimal-pad"
                />
              </View>
            </View>

            <TouchableOpacity style={styles.saveBtn} onPress={handleSaveStock}>
              <Text style={styles.saveBtnText}>+ SAVE INVESTED STOCK & ENABLE ALERTS</Text>
            </TouchableOpacity>
          </View>

          {/* Saved Invested Stocks List */}
          {telemetry.invested_stocks.map((stk) => {
            const macro = telemetry.country_macro[stk.country_code];
            const isPos = stk.unrealized_pnl >= 0;
            return (
              <View key={stk.ticker} style={styles.stockCard}>
                <View style={styles.stockHeader}>
                  <View>
                    <View style={styles.tickerRow}>
                      <Text style={styles.stockTicker}>{stk.ticker}</Text>
                      <View style={styles.countryTag}>
                        <Text style={styles.countryTagText}>{stk.country_code}</Text>
                      </View>
                      <View
                        style={[
                          styles.statusTag,
                          stk.status === 'OUTPERFORMING'
                            ? styles.statusBull
                            : stk.status.includes('ALERT') || stk.status.includes('HEADWIND')
                            ? styles.statusWarn
                            : styles.statusNeutral,
                        ]}
                      >
                        <Text style={styles.statusTagText}>{stk.status}</Text>
                      </View>
                    </View>
                    <Text style={styles.companySub}>
                      {stk.company_name} · {stk.shares} sh @ {stk.avg_buy_price.toFixed(2)} {stk.currency}
                    </Text>
                  </View>

                  <View style={styles.pnlRight}>
                    <Text style={styles.stockPrice}>
                      {stk.current_price.toFixed(2)} {stk.currency}
                    </Text>
                    <Text
                      style={[
                        styles.stockPnl,
                        { color: isPos ? '#00E676' : '#FF5252' },
                      ]}
                    >
                      {isPos ? '+' : ''}
                      {stk.unrealized_pnl.toFixed(2)} ({isPos ? '+' : ''}
                      {stk.unrealized_pnl_pct.toFixed(2)}%)
                    </Text>
                  </View>
                </View>

                {/* Country Sovereign Inflation, CPI & Tax Strip */}
                {macro && (
                  <View style={styles.macroStrip}>
                    <View style={styles.macroCell}>
                      <Text style={styles.macroCellLabel}>{stk.country_code} INFLATION</Text>
                      <Text style={styles.macroCellVal}>
                        {macro.inflation_rate_yoy_pct.toFixed(1)}%
                      </Text>
                    </View>
                    <View style={styles.macroCell}>
                      <Text style={styles.macroCellLabel}>{stk.country_code} CPI (YoY/MoM)</Text>
                      <Text style={styles.macroCellVal}>
                        {macro.cpi_index_yoy_pct.toFixed(1)}% / {macro.cpi_mom_pct.toFixed(1)}%
                      </Text>
                    </View>
                    <View style={styles.macroCell}>
                      <Text style={styles.macroCellLabel}>CORP / CAPGAINS TAX</Text>
                      <Text style={styles.macroCellVal}>
                        {macro.corporate_tax_rate_pct.toFixed(0)}% / {macro.capital_gains_tax_pct.toFixed(1)}%
                      </Text>
                    </View>
                    <View style={styles.macroCell}>
                      <Text style={styles.macroCellLabel}>POLICY RATE</Text>
                      <Text style={styles.macroCellVal}>
                        {macro.central_bank_rate_pct.toFixed(2)}%
                      </Text>
                    </View>
                  </View>
                )}

                <View style={styles.catalystFooter}>
                  <Text style={styles.catalystText} numberOfLines={2}>
                    [{stk.last_catalyst_source}] {stk.last_catalyst_headline}
                  </Text>
                  <TouchableOpacity onPress={() => removeInvestedStock(stk.ticker)}>
                    <Text style={styles.removeLink}>REMOVE</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
        </>
      )}

      {subView === 'MACRO_ALERTS' && (
        <>
          {/* Sovereign Country Macro & Tax Table + Live Update Trigger */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>
              SOVEREIGN INFLATION, CPI & TAX MONITOR (RESPECTIVE COUNTRIES)
            </Text>
            {Object.values(telemetry.country_macro).map((m) => (
              <View key={m.country_code} style={styles.countryRow}>
                <View>
                  <Text style={styles.countryTitle}>
                    {m.country_name} ({m.country_code})
                  </Text>
                  <Text style={styles.countrySource}>{m.last_updated_source}</Text>
                </View>
                <View style={styles.countryMetricsRight}>
                  <Text style={styles.countryMetricLine}>
                    Inflation: <Text style={styles.highlight}>{m.inflation_rate_yoy_pct.toFixed(1)}%</Text> · CPI:{' '}
                    <Text style={styles.highlight}>{m.cpi_index_yoy_pct.toFixed(1)}%</Text>
                  </Text>
                  <Text style={styles.countryMetricLine}>
                    CapGains Tax: <Text style={styles.highlight}>{m.capital_gains_tax_pct.toFixed(1)}%</Text> · Corp Tax:{' '}
                    <Text style={styles.highlight}>{m.corporate_tax_rate_pct.toFixed(1)}%</Text>
                  </Text>
                </View>
              </View>
            ))}

            {/* Test / Dispatch Sovereign CPI or Tax Rate Change */}
            <View style={styles.simBox}>
              <Text style={styles.label}>
                UPDATE / TEST COUNTRY CPI, INFLATION OR TAX CHANGE NOTIFICATION
              </Text>
              <View style={styles.countrySelector}>
                {COUNTRIES.map((c) => (
                  <TouchableOpacity
                    key={c}
                    style={[
                      styles.countryBtn,
                      selectedMacroCountry === c && styles.countryBtnActive,
                    ]}
                    onPress={() => setSelectedMacroCountry(c)}
                  >
                    <Text
                      style={[
                        styles.countryBtnText,
                        selectedMacroCountry === c && styles.countryBtnTextActive,
                      ]}
                    >
                      {c}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <View style={styles.row}>
                <View style={styles.col48}>
                  <Text style={styles.label}>NEW INFLATION / CPI (%)</Text>
                  <TextInput
                    style={styles.input}
                    value={newInflationInput}
                    onChangeText={setNewInflationInput}
                    keyboardType="decimal-pad"
                  />
                </View>
                <View style={styles.col48}>
                  <Text style={styles.label}>NEW CAP GAINS TAX (%)</Text>
                  <TextInput
                    style={styles.input}
                    value={newTaxInput}
                    onChangeText={setNewTaxInput}
                    keyboardType="decimal-pad"
                  />
                </View>
              </View>
              <TouchableOpacity style={styles.saveBtn} onPress={handleSimulateMacroUpdate}>
                <Text style={styles.saveBtnText}>
                  APPLY {selectedMacroCountry} MACRO / TAX UPDATE & NOTIFY
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Real-Time Notifications Log */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>
              STOCK STATUS, CPI, INFLATION & TAX NOTIFICATION LOG
            </Text>
            {telemetry.notifications.map((n) => (
              <View key={n.notification_id} style={styles.notifCard}>
                <View style={styles.notifHeader}>
                  <Text
                    style={[
                      styles.notifBadge,
                      n.severity === 'CRITICAL' || n.severity === 'WARNING'
                        ? { color: '#FF5252' }
                        : { color: '#00E676' },
                    ]}
                  >
                    {n.category} · {n.country_code}
                  </Text>
                  <Text style={styles.notifSource}>{n.source}</Text>
                </View>
                <Text style={styles.notifTitle}>{n.title}</Text>
                <Text style={styles.notifMsg}>{n.message}</Text>
              </View>
            ))}
          </View>
        </>
      )}

      {subView === 'GURU_NEWS' && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>
            TRUSTED MARKET INTELLIGENCE (SEEKING ALPHA, GURUFOCUS, BLS, SEC EDGAR)
          </Text>
          {telemetry.trusted_news_feed.map((item, idx) => {
            const isBull = item.sentiment_score >= 0;
            return (
              <View key={idx} style={styles.newsRow}>
                <View style={styles.newsTop}>
                  <Text style={styles.newsSource}>{item.source}</Text>
                  <Text
                    style={[
                      styles.newsScore,
                      { color: isBull ? '#00E676' : '#FF5252' },
                    ]}
                  >
                    FinBERT: {isBull ? '+' : ''}
                    {item.sentiment_score.toFixed(2)} ({(item.confidence * 100).toFixed(0)}% conf)
                  </Text>
                </View>
                <Text style={styles.newsHeadline}>{item.headline}</Text>
                <Text style={styles.newsSymbols}>
                  Impacted Assets: {item.symbols.join(', ')}
                </Text>
              </View>
            );
          })}
        </View>
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#070A0F',
  },
  content: {
    padding: 14,
    paddingBottom: 32,
  },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: '#0E141F',
    borderRadius: 10,
    padding: 4,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  tabPill: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 7,
  },
  tabPillActive: {
    backgroundColor: '#1E293B',
  },
  tabPillText: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '800',
  },
  tabPillTextActive: {
    color: '#38BDF8',
  },
  card: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#1E293B',
    marginBottom: 14,
  },
  cardTitle: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.6,
    marginBottom: 10,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  col30: {
    width: '31%',
  },
  col48: {
    width: '48%',
  },
  col68: {
    width: '66%',
  },
  label: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '700',
    marginBottom: 4,
  },
  input: {
    backgroundColor: '#090D16',
    color: '#F8FAFC',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
    fontSize: 13,
    fontWeight: '700',
    borderWidth: 1,
    borderColor: '#1E293B',
  },
  countrySelector: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  countryBtn: {
    flex: 1,
    marginHorizontal: 2,
    paddingVertical: 7,
    backgroundColor: '#090D16',
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#1E293B',
    alignItems: 'center',
  },
  countryBtnActive: {
    backgroundColor: '#0C2D48',
    borderColor: '#38BDF8',
  },
  countryBtnText: {
    color: '#64748B',
    fontSize: 11,
    fontWeight: '800',
  },
  countryBtnTextActive: {
    color: '#38BDF8',
  },
  saveBtn: {
    backgroundColor: '#0284C7',
    borderRadius: 8,
    paddingVertical: 11,
    alignItems: 'center',
    marginTop: 4,
  },
  saveBtnText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  stockCard: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 13,
    borderWidth: 1,
    borderColor: '#1E293B',
    marginBottom: 12,
  },
  stockHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  tickerRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  stockTicker: {
    color: '#F8FAFC',
    fontSize: 16,
    fontWeight: '900',
    marginRight: 8,
  },
  countryTag: {
    backgroundColor: '#1E293B',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    marginRight: 6,
  },
  countryTagText: {
    color: '#38BDF8',
    fontSize: 10,
    fontWeight: '800',
  },
  statusTag: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  statusBull: {
    backgroundColor: 'rgba(0, 230, 118, 0.16)',
  },
  statusWarn: {
    backgroundColor: 'rgba(255, 82, 82, 0.2)',
  },
  statusNeutral: {
    backgroundColor: 'rgba(148, 163, 184, 0.16)',
  },
  statusTagText: {
    color: '#F8FAFC',
    fontSize: 9,
    fontWeight: '800',
  },
  companySub: {
    color: '#94A3B8',
    fontSize: 11,
    marginTop: 3,
  },
  pnlRight: {
    alignItems: 'flex-end',
  },
  stockPrice: {
    color: '#F8FAFC',
    fontSize: 15,
    fontWeight: '800',
  },
  stockPnl: {
    fontSize: 12,
    fontWeight: '700',
    marginTop: 2,
  },
  macroStrip: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#090D16',
    borderRadius: 8,
    padding: 8,
    marginVertical: 10,
    borderWidth: 1,
    borderColor: '#162032',
  },
  macroCell: {
    flex: 1,
  },
  macroCellLabel: {
    color: '#64748B',
    fontSize: 8,
    fontWeight: '700',
  },
  macroCellVal: {
    color: '#E2E8F0',
    fontSize: 11,
    fontWeight: '800',
    marginTop: 2,
  },
  catalystFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  catalystText: {
    color: '#94A3B8',
    fontSize: 10,
    flex: 1,
    marginRight: 8,
  },
  removeLink: {
    color: '#FF5252',
    fontSize: 10,
    fontWeight: '800',
  },
  countryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 9,
    borderBottomWidth: 1,
    borderBottomColor: '#162032',
  },
  countryTitle: {
    color: '#F8FAFC',
    fontSize: 13,
    fontWeight: '700',
  },
  countrySource: {
    color: '#64748B',
    fontSize: 9,
    marginTop: 2,
  },
  countryMetricsRight: {
    alignItems: 'flex-end',
  },
  countryMetricLine: {
    color: '#94A3B8',
    fontSize: 11,
  },
  highlight: {
    color: '#38BDF8',
    fontWeight: '800',
  },
  simBox: {
    marginTop: 12,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#1E293B',
  },
  notifCard: {
    backgroundColor: '#090D16',
    borderRadius: 8,
    padding: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#162032',
  },
  notifHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  notifBadge: {
    fontSize: 10,
    fontWeight: '800',
  },
  notifSource: {
    color: '#64748B',
    fontSize: 9,
  },
  notifTitle: {
    color: '#F8FAFC',
    fontSize: 12,
    fontWeight: '800',
    marginBottom: 3,
  },
  notifMsg: {
    color: '#CBD5E1',
    fontSize: 11,
    lineHeight: 15,
  },
  newsRow: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#162032',
  },
  newsTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  newsSource: {
    color: '#38BDF8',
    fontSize: 10,
    fontWeight: '800',
  },
  newsScore: {
    fontSize: 10,
    fontWeight: '800',
  },
  newsHeadline: {
    color: '#F8FAFC',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 16,
  },
  newsSymbols: {
    color: '#64748B',
    fontSize: 10,
    marginTop: 4,
  },
});
