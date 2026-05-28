export interface Point {
  x: number;
  y: number;
}

export interface FaceLandmarks {
  leftEye: Point;
  rightEye: Point;
  nose: Point;
  mouthLeft?: Point;
  mouthRight?: Point;
}

export interface FaceObservation {
  landmarks: FaceLandmarks;
}

export interface LivenessState {
  prompt: string;
  score: number;
  isLive: boolean;
  completedSteps: string[];
}

type Step = 'center' | 'left' | 'right';

class HeadTurnLivenessTracker {
  private completed = new Set<Step>();

  public reset() {
    this.completed.clear();
  }

  public processFace(face: FaceObservation): LivenessState {
    const yaw = this.estimateYaw(face.landmarks);

    if (Math.abs(yaw) <= 0.12) {
      this.completed.add('center');
    }

    if (this.completed.has('center') && yaw <= -0.18) {
      this.completed.add('left');
    }

    if (this.completed.has('left') && yaw >= 0.18) {
      this.completed.add('right');
    }

    const isLive = this.completed.has('center') && this.completed.has('left') && this.completed.has('right');
    const score = this.completed.size / 3;

    return {
      prompt: this.promptForState(isLive),
      score,
      isLive,
      completedSteps: Array.from(this.completed),
    };
  }

  private estimateYaw(landmarks: FaceLandmarks): number {
    const { leftEye, rightEye, nose } = landmarks;
    const eyeDistance = Math.max(1, rightEye.x - leftEye.x);
    const midpointX = (leftEye.x + rightEye.x) / 2;

    return (nose.x - midpointX) / eyeDistance;
  }

  private promptForState(isLive: boolean): string {
    if (isLive) return 'Liveness verified';
    if (!this.completed.has('center')) return 'Look straight';
    if (!this.completed.has('left')) return 'Turn head left';
    return 'Turn head right';
  }
}

export const livenessTracker = new HeadTurnLivenessTracker();
