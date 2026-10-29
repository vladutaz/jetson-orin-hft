import { StatusBar } from 'expo-status-bar';
import React, { useState } from 'react';
import { SafeAreaView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { TradingProvider } from './src/context/TradingContext';
import { DashboardScreen } from './src/screens/DashboardScreen';
import { EmergencyScreen } from './src/screens/EmergencyScreen';
import { OrdersScreen } from './src/screens/OrdersScreen';
import { TerminalScreen } from './src/screens/TerminalScreen';

type ScreenTab = 'DASHBOARD' | 'TERMINAL' | 'ORDERS' | 'KILL_SWITCH';

export default function App() {
  const [activeTab, setActiveTab] = useState<ScreenTab>('DASHBOARD');

  return (
    <TradingProvider>
      <SafeAreaView style={styles.container}>
        <StatusBar style="light" />

        {/* Top Institutional Header Bar */}
        <View style={styles.topHeader}>
          <View>
            <Text style={styles.brandTitle}>JETSON ORIN // EDGE HFT</Text>
            <Text style={styles.brandSub}>JetPack 6.x · TensorRT FP16 · ZeroMQ IPC</Text>
          </View>
          <TouchableOpacity
            style={styles.quickKillPill}
            onPress={() => setActiveTab('KILL_SWITCH')}
          >
            <Text style={styles.quickKillText}>KILL-SWITCH</Text>
          </TouchableOpacity>
        </View>

        {/* Active Screen Viewport */}
        <View style={styles.viewport}>
          {activeTab === 'DASHBOARD' && <DashboardScreen />}
          {activeTab === 'TERMINAL' && <TerminalScreen />}
          {activeTab === 'ORDERS' && <OrdersScreen />}
          {activeTab === 'KILL_SWITCH' && <EmergencyScreen />}
        </View>

        {/* Bottom Navigation Bar */}
        <View style={styles.bottomNav}>
          <TouchableOpacity
            style={styles.navItem}
            onPress={() => setActiveTab('DASHBOARD')}
          >
            <Text style={[styles.navText, activeTab === 'DASHBOARD' && styles.navTextActive]}>
              DASHBOARD
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.navItem}
            onPress={() => setActiveTab('TERMINAL')}
          >
            <Text style={[styles.navText, activeTab === 'TERMINAL' && styles.navTextActive]}>
              TERMINAL
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.navItem}
            onPress={() => setActiveTab('ORDERS')}
          >
            <Text style={[styles.navText, activeTab === 'ORDERS' && styles.navTextActive]}>
              ORDERS
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.navItem}
            onPress={() => setActiveTab('KILL_SWITCH')}
          >
            <Text
              style={[
                styles.navText,
                styles.navKillText,
                activeTab === 'KILL_SWITCH' && styles.navKillActive,
              ]}
            >
              EMERGENCY
            </Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </TradingProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#070A0F',
  },
  topHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1E293B',
    backgroundColor: '#0B0F19',
  },
  brandTitle: {
    color: '#F8FAFC',
    fontSize: 15,
    fontWeight: '900',
    letterSpacing: 1.0,
  },
  brandSub: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '600',
    marginTop: 2,
  },
  quickKillPill: {
    backgroundColor: '#991B1B',
    borderWidth: 1,
    borderColor: '#EF4444',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
  },
  quickKillText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.6,
  },
  viewport: {
    flex: 1,
  },
  bottomNav: {
    flexDirection: 'row',
    backgroundColor: '#0B0F19',
    borderTopWidth: 1,
    borderTopColor: '#1E293B',
    paddingVertical: 10,
  },
  navItem: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 4,
  },
  navText: {
    color: '#64748B',
    fontSize: 11,
    fontWeight: '800',
  },
  navTextActive: {
    color: '#38BDF8',
  },
  navKillText: {
    color: '#F87171',
  },
  navKillActive: {
    color: '#EF4444',
    textDecorationLine: 'underline',
  },
});
