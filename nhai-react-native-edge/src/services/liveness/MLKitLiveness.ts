import { Frame } from 'react-native-vision-camera';
import FaceDetection, { Face } from '@react-native-ml-kit/face-detection';

/**
 * Interface defining the state of our active liveness checks.
 */
export interface LivenessState {
  hasBlinked: boolean;
  hasSmiled: boolean;
  isLive: boolean;
  prompt: string;
}

/**
 * Tracks the progression of liveness challenges.
 * We want the user to first BLINK, and then SMILE.
 */
class LivenessTracker {
  private blinkDetected = false;
  private smileDetected = false;
  private wasEyeClosed = false;

  public reset() {
    this.blinkDetected = false;
    this.smileDetected = false;
    this.wasEyeClosed = false;
  }

  public processFace(face: Face): LivenessState {
    const leftEyeOpen = face.leftEyeOpenProbability ?? 1.0;
    const rightEyeOpen = face.rightEyeOpenProbability ?? 1.0;
    const smiling = face.smilingProbability ?? 0.0;

    // Detect Blink: eyes must go from open -> closed -> open
    // A threshold < 0.2 indicates the eye is closed
    if (leftEyeOpen < 0.2 && rightEyeOpen < 0.2) {
      this.wasEyeClosed = true;
    } else if (this.wasEyeClosed && leftEyeOpen > 0.8 && rightEyeOpen > 0.8) {
      this.blinkDetected = true;
    }

    // Detect Smile: only if they have already blinked (forces a sequence)
    if (this.blinkDetected && smiling > 0.7) {
      this.smileDetected = true;
    }

    // Determine the prompt to show the user
    let prompt = "Please blink your eyes";
    if (this.blinkDetected && !this.smileDetected) {
      prompt = "Now, please smile!";
    } else if (this.blinkDetected && this.smileDetected) {
      prompt = "Liveness Verified! Hold still for matching...";
    }

    return {
      hasBlinked: this.blinkDetected,
      hasSmiled: this.smileDetected,
      isLive: this.blinkDetected && this.smileDetected,
      prompt,
    };
  }
}

export const livenessTracker = new LivenessTracker();

/**
 * Frame processor plugin for react-native-vision-camera that runs Google ML Kit.
 * Extracts face bounds and liveness probabilities.
 * Note: ML Kit face detection is extremely fast (< 30ms per frame) and runs natively on-device.
 */
export async function detectFacesInFrame(frame: Frame): Promise<Face[]> {
  'worklet';
  // Note: in a real react-native-vision-camera v4 worklet, you would use a native C++ plugin
  // or a wrapper like @react-native-ml-kit/face-detection's frame processor support.
  // We simulate the API boundary here for the Datalake 3.0 integration.
  try {
    const faces = await FaceDetection.detect(frame, {
      landmarkMode: 'all',
      contourMode: 'none',
      classificationMode: 'all', // Required for blink/smile detection
      performanceMode: 'fast',
    });
    return faces;
  } catch (error) {
    console.error("ML Kit Error:", error);
    return [];
  }
}
