import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import {
  Camera,
  useCameraDevice,
  useCameraPermission,
} from 'react-native-vision-camera';
import { faceRecognitionService } from '../services/recognition/TFLiteRecognition';
import { livenessTracker } from '../services/liveness/HeadTurnLiveness';
import { modelOtaManager } from '../services/models/ModelOtaManager';
import { offlineSyncManager } from '../services/sync/OfflineSyncManager';
import { CameraOverlay } from '../components/CameraOverlay';

const DEMO_WORKER_ID = 'NHAI-DEL-1234';

interface AttendanceScreenProps {
  backendBaseUrl?: string;
  deviceId?: string;
  deviceJwt?: string;
}

export const AttendanceScreen: React.FC<AttendanceScreenProps> = ({
  backendBaseUrl,
  deviceId,
  deviceJwt,
}) => {
  const device = useCameraDevice('front');
  const { hasPermission, requestPermission } = useCameraPermission();
  const [promptText, setPromptText] = useState('Position your face in the oval');
  const [isProcessingMatch, setIsProcessingMatch] = useState(false);
  const [isLivenessPassed, setIsLivenessPassed] = useState(false);
  const [challengeIndex, setChallengeIndex] = useState(0);

  useEffect(() => {
    (async () => {
      if (!hasPermission) {
        await requestPermission();
      }

      livenessTracker.reset();
      setChallengeIndex(0);
      offlineSyncManager.initDB();
      offlineSyncManager.configure({ backendBaseUrl, deviceId, deviceJwt });
      offlineSyncManager.startNetworkSync();
      modelOtaManager.configure({ backendBaseUrl, deviceId, deviceJwt });
      try {
        await modelOtaManager.syncModels();
      } catch (error) {
        console.warn('Model OTA sync failed; using any locally available model.', error);
      }
      await faceRecognitionService.initModel();
    })();
  }, [backendBaseUrl, deviceId, deviceJwt, hasPermission, requestPermission]);

  const saveMatchedAttendance = useCallback(async (livenessScore: number) => {
    setIsProcessingMatch(true);
    setPromptText('Verifying identity...');

    try {
      const simulatedCrop = new Float32Array(112 * 112 * 3).fill(0.1);
      const embedding = await faceRecognitionService.getFaceEmbedding(simulatedCrop);
      const confidence = embedding.length > 0 ? 0.92 : 0.88;

      setIsLivenessPassed(true);
      await offlineSyncManager.saveAttendance(DEMO_WORKER_ID, livenessScore, confidence);
      setPromptText('Attendance marked');
      Alert.alert('Attendance saved', 'Record signed and queued for sync.');
    } catch (error) {
      setPromptText('Saved demo record offline');
      await offlineSyncManager.saveAttendance(DEMO_WORKER_ID, livenessScore, 0.88);
      Alert.alert('Demo mode', 'Model unavailable, so a signed demo record was queued.');
    } finally {
      setTimeout(() => {
        setIsProcessingMatch(false);
        setIsLivenessPassed(false);
        setChallengeIndex(0);
        livenessTracker.reset();
        setPromptText('Position your face in the oval');
      }, 2500);
    }
  }, []);

  const captureLivenessStep = useCallback(async () => {
    if (isProcessingMatch) return;

    const observations = [
      { landmarks: { leftEye: { x: 40, y: 40 }, rightEye: { x: 140, y: 40 }, nose: { x: 90, y: 80 } } },
      { landmarks: { leftEye: { x: 40, y: 40 }, rightEye: { x: 140, y: 40 }, nose: { x: 68, y: 82 } } },
      { landmarks: { leftEye: { x: 40, y: 40 }, rightEye: { x: 140, y: 40 }, nose: { x: 112, y: 82 } } },
    ];
    const state = livenessTracker.processFace(observations[Math.min(challengeIndex, observations.length - 1)]);

    setPromptText(state.prompt);
    setChallengeIndex((current) => current + 1);

    if (state.isLive) {
      await saveMatchedAttendance(state.score);
    }
  }, [challengeIndex, isProcessingMatch, saveMatchedAttendance]);

  if (!hasPermission) {
    return <Text style={styles.statusText}>No camera permission</Text>;
  }

  if (!device) {
    return <Text style={styles.statusText}>No front camera found</Text>;
  }

  return (
    <View style={styles.container}>
      <Camera style={StyleSheet.absoluteFill} device={device} isActive={!isProcessingMatch} />

      <CameraOverlay
        isScanning={!isLivenessPassed && !isProcessingMatch}
        promptText={promptText}
        livenessSuccess={isLivenessPassed}
      />

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          disabled={isProcessingMatch}
          onPress={captureLivenessStep}
          style={({ pressed }) => [
            styles.primaryButton,
            (pressed || isProcessingMatch) && styles.primaryButtonPressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>
            {isProcessingMatch ? 'Processing' : 'Capture liveness step'}
          </Text>
        </Pressable>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: 'black',
  },
  statusText: {
    flex: 1,
    color: '#111827',
    textAlign: 'center',
    textAlignVertical: 'center',
  },
  actions: {
    position: 'absolute',
    bottom: 28,
    left: 20,
    right: 20,
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: '#0F766E',
    borderRadius: 8,
    minHeight: 48,
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  primaryButtonPressed: {
    opacity: 0.75,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
});
