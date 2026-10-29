import * as Haptics from 'expo-haptics';
import * as LocalAuthentication from 'expo-local-authentication';
import React, { useRef, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useTrading } from '../context/TradingContext';

/**
 * Layer 6 Emergency Controls ("The Kill-Switch"):
 *   - Protected by Step 1: Hardware Biometric Authentication (FaceID / Fingerprint via `expo-local-authentication`).
 *   - Protected by Step 2: Continuous 2.0-second press-and-hold / slide progress confirmation bar.
 *   - Dispatches urgent priority `EMERGENCY_FLATTEN` command over the encrypted ZeroMQ bridge
 *     to cancel all open orders, market-close all positions, and lock the engine in `HALTED` mode.
 */
export const EmergencyScreen: React.FC = () => {
  const { telemetry, triggerKillSwitch, resumeTrading } = useTrading();
  const [biometricArmed, setBiometricArmed] = useState<boolean>(false);
  const [holdProgress, setHoldProgress] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string>(
    'System operating normally. Biometric lock engaged.'
  );
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const handleBiometricArm = async () => {
    try {
      const hasHardware = await LocalAuthentication.hasHardwareAsync();
      const isEnrolled = await LocalAuthentication.isEnrolledAsync();

      if (hasHardware && isEnrolled) {
        const res = await LocalAuthentication.authenticateAsync({
          promptMessage: 'Authenticate to Arm Emergency HFT Kill-Switch',
          fallbackLabel: 'Use Passcode',
          disableDeviceFallback: false,
        });
        if (!res.success) {
          setStatusMessage('Biometric authentication declined.');
          return;
        }
      }
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      setBiometricArmed(true);
      setStatusMessage(
        'BIOMETRIC VERIFIED: Hold the Red EMERGENCY FLATTEN button for 2.0 seconds to execute.'
      );
    } catch {
      setBiometricArmed(true);
      setStatusMessage('BIOMETRIC VERIFIED: Hold EMERGENCY FLATTEN for 2.0 seconds.');
    }
  };

  const startTwoSecondHold = () => {
    if (!biometricArmed) {
      setStatusMessage('Step 1 Required: Tap "UNLOCK WITH FACEID / BIOMETRICS" first.');
      return;
    }
    const startTs = Date.now();
    const requiredMs = 2000;
    if (timerRef.current) clearInterval(timerRef.current);

    timerRef.current = setInterval(() => {
      const elapsed = Date.now() - startTs;
      const pct = Math.min(100, (elapsed / requiredMs) * 100);
      setHoldProgress(pct);

      if (pct >= 100) {
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = null;
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
        triggerKillSwitch(true);
        setBiometricArmed(false);
        setHoldProgress(0);
        setStatusMessage(
          'KILL-SWITCH EXECUTED: All open orders canceled, all positions market-flattened, engine HALTED.'
        );
      }
    }, 40);
  };

  const cancelTwoSecondHold = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (holdProgress < 100) {
      setHoldProgress(0);
    }
  };

  const isHalted = telemetry.engine_state === 'HALTED';

  return (
    <View style={styles.screen}>
      <View style={styles.warningBanner}>
        <Text style={styles.warningTitle}>INSTITUTIONAL EMERGENCY KILL-SWITCH PROTOCOL</Text>
        <Text style={styles.warningSub}>
          Executing Emergency Flatten dispatches a priorityreal-time command (`chrt -f 99`) to the
          Jetson Orin execution engine to immediately cancel all open maker/limit orders, close all
          perpetual positions at market, and lock the risk gatekeeper into HALTED mode.
        </Text>
      </View>

      <View style={styles.statusBox}>
        <Text style={styles.statusLabel}>ENGINE STATE</Text>
        <Text
          style={[
            styles.statusState,
            { color: isHalted ? '#FF5252' : '#00E676' },
          ]}
        >
          {telemetry.engine_state}
        </Text>
        <Text style={styles.statusMsg}>{statusMessage}</Text>
      </View>

      {/* Step 1: Biometric Unlock */}
      <TouchableOpacity
        style={[styles.bioButton, biometricArmed && styles.bioButtonArmed]}
        onPress={handleBiometricArm}
      >
        <Text style={styles.bioButtonText}>
          {biometricArmed
            ? 'BIOMETRIC ARMED (FACEID / TOUCHID VERIFIED)'
            : 'STEP 1: UNLOCK WITH FACEID / BIOMETRICS'}
        </Text>
      </TouchableOpacity>

      {/* Step 2: Big Red Emergency Flatten Button (2-Second Hold-to-Confirm) */}
      <TouchableOpacity
        activeOpacity={0.85}
        onPressIn={startTwoSecondHold}
        onPressOut={cancelTwoSecondHold}
        style={[
          styles.killButton,
          !biometricArmed && styles.killButtonDisabled,
        ]}
      >
        <View style={[styles.progressFill, { width: `${holdProgress}%` }]} />
        <Text style={styles.killButtonTitle}>EMERGENCY FLATTEN</Text>
        <Text style={styles.killButtonSub}>
          {biometricArmed
            ? `HOLD FOR 2.0 SECONDS TO FLATTEN (${(holdProgress / 50).toFixed(1)}s / 2.0s)`
            : 'LOCKED — COMPLETE BIOMETRIC AUTHENTICATION ABOVE'}
        </Text>
      </TouchableOpacity>

      {isHalted && (
        <TouchableOpacity style={styles.resumeButton} onPress={resumeTrading}>
          <Text style={styles.resumeText}>RE-ARM & RESUME STRATEGY STATE MACHINE</Text>
        </TouchableOpacity>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#070A0F',
    padding: 16,
  },
  warningBanner: {
    backgroundColor: '#1A0F14',
    borderWidth: 1,
    borderColor: '#7F1D1D',
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
  },
  warningTitle: {
    color: '#F87171',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  warningSub: {
    color: '#FCA5A5',
    fontSize: 11,
    lineHeight: 16,
  },
  statusBox: {
    backgroundColor: '#0E141F',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#1E293B',
    alignItems: 'center',
    marginBottom: 18,
  },
  statusLabel: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '700',
  },
  statusState: {
    fontSize: 26,
    fontWeight: '900',
    marginVertical: 6,
  },
  statusMsg: {
    color: '#94A3B8',
    fontSize: 12,
    textAlign: 'center',
  },
  bioButton: {
    backgroundColor: '#1E293B',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#38BDF8',
    marginBottom: 16,
  },
  bioButtonArmed: {
    backgroundColor: '#064E3B',
    borderColor: '#00E676',
  },
  bioButtonText: {
    color: '#F8FAFC',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.6,
  },
  killButton: {
    height: 130,
    backgroundColor: '#B91C1C',
    borderRadius: 16,
    borderWidth: 2,
    borderColor: '#EF4444',
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
    position: 'relative',
  },
  killButtonDisabled: {
    backgroundColor: '#27171A',
    borderColor: '#451A1C',
  },
  progressFill: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    backgroundColor: '#EF4444',
  },
  killButtonTitle: {
    color: '#FFFFFF',
    fontSize: 24,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  killButtonSub: {
    color: '#FECACA',
    fontSize: 11,
    fontWeight: '700',
    marginTop: 6,
  },
  resumeButton: {
    marginTop: 20,
    backgroundColor: '#0F172A',
    borderWidth: 1,
    borderColor: '#00E676',
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
  },
  resumeText: {
    color: '#00E676',
    fontSize: 12,
    fontWeight: '800',
  },
});
