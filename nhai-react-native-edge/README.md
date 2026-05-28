# NHAI Datalake 3.0 Edge Application Integration

This React Native edge module is scoped to the deployed backend contracts and the Hackathon 7.0 constraints: Android + iOS, offline operation, lightweight OTA models, liveness, signed attendance records, and sync-purge when connectivity returns.

## Feasible Prototype Scope

1. **Open-source mobile stack:** React Native, Vision Camera, TensorFlow Lite runtime, SQLite, NetInfo, RNFS, and ECDSA signing libraries.
2. **Model footprint below 20 MB:** models are downloaded from `/models/manifest` and stored in the app document directory instead of being bundled into the APK/IPA.
3. **Offline liveness:** `HeadTurnLiveness.ts` implements a head-turn challenge from lightweight landmarks. It can be fed by YuNet/TFLite/OpenCV face landmarks without using proprietary ML Kit.
4. **Offline recognition:** `TFLiteRecognition.ts` loads MobileFaceNet from the OTA model path and returns normalized embeddings for cosine matching.
5. **Backend-compatible sync:** `OfflineSyncManager.ts` writes records to SQLite with the exact deployed `/attendance/sync` shape, signs canonical JSON, syncs when online, and purges accepted rows.

## Required Packages

```bash
npm install react-native-vision-camera react-native-worklets-core
npm install react-native-fast-tflite react-native-fs
npm install @react-native-community/netinfo react-native-quick-sqlite
npm install elliptic @noble/hashes uuid
```

## iOS Setup

Run `npx pod-install` or `cd ios && pod install`.

```xml
<key>NSCameraUsageDescription</key>
<string>NHAI needs camera access for biometric attendance.</string>
```

Minimum target: iOS 12+.

## Android Setup

```xml
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.INTERNET" />
```

Minimum target: Android 8.0+.

## Usage

Pass the already-issued device identity from your app's auth flow. The backend is not modified.

```tsx
import { AttendanceScreen } from './src/screens/AttendanceScreen';

export default function App() {
  return (
    <AttendanceScreen
      backendBaseUrl="https://your-api-gateway-url"
      deviceId="edge-tablet-001"
      deviceJwt="DEVICE_JWT_FROM_AUTH_SERVICE"
    />
  );
}
```

## Production Hook Points

- Replace the demo button path in `AttendanceScreen.tsx` with a Vision Camera frame processor that emits YuNet face landmarks and a 112x112 aligned face crop.
- Feed landmarks into `livenessTracker.processFace(...)`.
- Feed the crop into `faceRecognitionService.getFaceEmbedding(...)`.
- Compare the embedding with locally synced worker embeddings and call `offlineSyncManager.saveAttendance(...)` only when the threshold passes.
