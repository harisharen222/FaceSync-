import React, { useEffect, useState, useCallback } from 'react';
import { View, StyleSheet, Text, Alert } from 'react-native';
import { Camera, useCameraDevice, useFrameProcessor } from 'react-native-vision-camera';
import { livenessTracker, detectFacesInFrame } from '../services/liveness/MLKitLiveness';
import { faceRecognitionService } from '../services/recognition/TFLiteRecognition';
import { offlineSyncManager } from '../services/sync/OfflineSyncManager';
import { CameraOverlay } from '../components/CameraOverlay';

/**
 * Main Offline Edge Attendance Screen.
 * Integrates Vision Camera, ML Kit (Liveness), TFLite (Recognition), and SQLite (Sync).
 */
export const AttendanceScreen: React.FC = () => {
  const device = useCameraDevice('front');
  const [hasPermission, setHasPermission] = useState(false);
  
  // UI State
  const [promptText, setPromptText] = useState("Position your face in the oval");
  const [isLivenessPassed, setIsLivenessPassed] = useState(false);
  const [isProcessingMatch, setIsProcessingMatch] = useState(false);

  // Initialize offline models and DB on mount
  useEffect(() => {
    (async () => {
      const status = await Camera.requestCameraPermission();
      setHasPermission(status === 'granted');
      
      await faceRecognitionService.initModel();
      offlineSyncManager.initDB();
    })();
  }, []);

  /**
   * The Frame Processor Worklet runs highly optimized C++ code natively on every frame
   * thrown by the camera (up to 60fps). We pass it to ML Kit to get face landmarks.
   */
  const frameProcessor = useFrameProcessor((frame) => {
    'worklet';
    if (isLivenessPassed || isProcessingMatch) return;

    // Call ML Kit natively (simulated API here)
    const faces = detectFacesInFrame(frame);
    
    if (faces && faces.length > 0) {
      const face = faces[0];
      
      // Pass ML Kit probabilities to our Liveness Tracker logic
      const livenessState = livenessTracker.processFace(face);
      
      // Update UI Worklet safely
      // @ts-ignore
      setPromptText(livenessState.prompt);

      if (livenessState.isLive) {
        // Liveness passed! Stop frame processing and run TFLite recognition
        // @ts-ignore
        setIsLivenessPassed(true);
        // @ts-ignore
        handleFaceMatch(frame); 
      }
    } else {
      // @ts-ignore
      setPromptText("No face detected");
      livenessTracker.reset();
    }
  }, [isLivenessPassed, isProcessingMatch]);

  /**
   * Called when Liveness passes. We extract the face embedding and verify.
   */
  const handleFaceMatch = useCallback(async (frame: any) => {
    setIsProcessingMatch(true);
    setPromptText("Verifying Identity...");

    try {
      // 1. In a real app, you would crop the face from the frame and preprocess it here.
      // We simulate passing the Float32Array of the crop to TFLite.
      const simulatedCrop = new Float32Array(112 * 112 * 3).fill(0.1); 
      
      // 2. Extract Embedding via TFLite (MobileFaceNet)
      const embedding = await faceRecognitionService.getFaceEmbedding(simulatedCrop);

      // 3. Compare with offline registered users (SQLite)
      // For the prototype, we assume we matched 'worker-123' with 92% confidence
      const matchedWorkerId = "worker-123";
      const confidenceScore = 0.92;
      const deviceId = "edge-tablet-001";

      if (confidenceScore > 0.6) {
        // 4. Cryptographically Sign & Save offline!
        await offlineSyncManager.saveAttendance(
          matchedWorkerId, 
          1.0, // Liveness score (100% since it passed)
          confidenceScore, 
          deviceId
        );

        setPromptText("Attendance Marked Successfully!");
        Alert.alert("Success", "Attendance marked offline and cryptographically secured.");
      } else {
        setPromptText("Face not recognized.");
        Alert.alert("Failed", "Please try again or register your face.");
      }
    } catch (error) {
      console.error(error);
      setPromptText("Verification Failed.");
    }

    // Reset after a few seconds
    setTimeout(() => {
      setIsLivenessPassed(false);
      setIsProcessingMatch(false);
      livenessTracker.reset();
      setPromptText("Position your face in the oval");
    }, 3000);
  }, []);

  if (!hasPermission) return <Text>No Camera Permission</Text>;
  if (device == null) return <Text>No Camera Device Found</Text>;

  return (
    <View style={styles.container}>
      <Camera
        style={StyleSheet.absoluteFill}
        device={device}
        isActive={true}
        frameProcessor={frameProcessor}
        frameProcessorFps={15} // Cap at 15fps to save battery on Edge device
      />
      
      <CameraOverlay 
        isScanning={!isLivenessPassed && !isProcessingMatch}
        promptText={promptText}
        livenessSuccess={isLivenessPassed}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: 'black'
  }
});
