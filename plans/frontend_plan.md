# NHAI Biometric Attendance — FRONTEND PLAN
### React Native Mobile Application (Android + iOS)

---

## Overview

The frontend is a **React Native mobile app** that acts purely as the presentation and coordination layer. All heavy computation (camera buffering, ML inference, encryption) runs in **native threads** (Kotlin/Swift), passing only clean status tokens back to React Native over the bridge.

```
┌─────────────────────────────────────────────┐
│           REACT NATIVE (UI Layer)           │
│  Screens / Navigation / State Management   │
└────────────────┬────────────────────────────┘
                 │  NativeModule Bridge (token only)
                 ▼
┌─────────────────────────────────────────────┐
│     NATIVE LAYER (Kotlin / Swift)           │
│  Camera → Detection → Liveness → Matching  │
└────────────────┬────────────────────────────┘
                 │  Encrypted Result + Signed Log
                 ▼
┌─────────────────────────────────────────────┐
│     SECURE LOCAL STORAGE (SQLCipher)        │
│  Enrollment Templates + Offline Queue       │
└─────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| App Framework | React Native 0.73+ (CLI, not Expo) |
| Language | TypeScript |
| Navigation | React Navigation v6 (Stack + Bottom Tab) |
| State Management | Zustand (lightweight global store) |
| Native Modules | Kotlin (Android) / Swift (iOS) |
| Camera Feed | Native AVFoundation (iOS) / Camera2 API (Android) |
| ML Inference | TFLite INT8 via native Kotlin/Swift |
| Local DB | SQLCipher via native module |
| UI Components | Custom-built (no heavy UI libraries) |
| Animations | React Native Reanimated 3 |
| Icons | React Native Vector Icons |

---

## Phase 1: Project Setup & Folder Architecture

**Goal:** Initialize the project, configure native bridges, and establish folder conventions.

### Steps:
1. **Initialize React Native project**
   ```bash
   npx react-native@latest init NHAIAttendance --template react-native-template-typescript
   cd NHAIAttendance
   ```

2. **Install core dependencies**
   ```bash
   npm install @react-navigation/native @react-navigation/stack @react-navigation/bottom-tabs
   npm install react-native-reanimated react-native-gesture-handler
   npm install zustand
   npm install react-native-vector-icons
   npm install @react-native-community/netinfo   # for offline detection
   npm install react-native-device-info          # for hardware device ID
   ```

3. **Place native modules**
   - Copy `FaceRecognitionModule.kt` → `android/app/src/main/java/com/nhaiattendance/biometrics/`
   - Copy `FaceRecognitionModule.swift` → `ios/NHAIAttendance/NativeModules/`
   - Register both in their respective package lists

4. **Folder Structure**
   ```
   src/
   ├── screens/
   │   ├── SplashScreen.tsx
   │   ├── LoginScreen.tsx
   │   ├── DashboardScreen.tsx
   │   ├── EnrollmentScreen.tsx
   │   ├── VerificationScreen.tsx
   │   ├── AttendanceLogScreen.tsx
   │   └── AdminScreen.tsx
   ├── components/
   │   ├── CameraViewport.tsx
   │   ├── LivenessIndicator.tsx
   │   ├── MatchScoreCard.tsx
   │   ├── BiometricStatusHUD.tsx
   │   ├── OfflineQueueBadge.tsx
   │   └── SecurityAlertModal.tsx
   ├── native/
   │   └── BiometricBridge.ts        # JS wrapper over NativeModules
   ├── store/
   │   └── useAppStore.ts            # Zustand global state
   ├── services/
   │   ├── syncService.ts            # Background AWS sync
   │   └── apiService.ts             # Cloud API calls
   ├── navigation/
   │   └── AppNavigator.tsx
   ├── theme/
   │   └── colors.ts                 # Design tokens
   └── utils/
       └── formatters.ts
   ```

---

## Phase 2: Design System & UI Theme

**Goal:** Build a premium dark-mode design language that feels authoritative and modern.

### Design Tokens (`src/theme/colors.ts`)
```typescript
export const colors = {
  // Backgrounds
  bg_primary:    '#0F172A',   // Deep navy — main background
  bg_surface:    '#1E293B',   // Cards and panels
  bg_elevated:   '#334155',   // Modals and overlays

  // Accents
  accent_cyan:   '#38BDF8',   // Primary action color
  accent_green:  '#10B981',   // Success / verified
  accent_red:    '#EF4444',   // Danger / spoof detected
  accent_amber:  '#F59E0B',   // Warning / pending

  // Text
  text_primary:  '#F1F5F9',
  text_secondary:'#94A3B8',
  text_muted:    '#475569',

  // Overlay feedback
  verified_bg:   '#064E3B',   // Full-screen verified glow
  spoof_bg:      '#450A0A',   // Full-screen spoof alert
};
```

### Typography
- Font family: **Inter** (from Google Fonts via `react-native-google-fonts`)
- Headings: `Inter_700Bold` — 22–28px
- Labels: `Inter_600SemiBold` — 14–16px
- Body: `Inter_400Regular` — 13–14px
- Monospace (latency display): `JetBrainsMono_400Regular`

### Micro-animations
All status transitions use Reanimated 3 spring physics:
- EAR blink confirmed → green scan overlay sweeps downward
- Spoof detected → screen pulses red 3×
- Verified → shimmer green glow from center outward

---

## Phase 3: Screen Implementations

### 3.1 SplashScreen
**Purpose:** App entry, load native models, verify device integrity.
```
┌─────────────────────────────┐
│   NHAI Logo (animated)      │
│   "Biometric Secure Gate"   │
│                             │
│   Initializing Models...    │
│   [████████░░] 80%          │
└─────────────────────────────┘
```
- Calls `BiometricBridge.initializeModels()`
- Checks if any worker profiles are enrolled in SQLCipher
- Routes to: `LoginScreen` (if enrolled) or `EnrollmentScreen` (first time)

---

### 3.2 LoginScreen
**Purpose:** Simple Worker ID + PIN entry before biometric gate.
```
┌─────────────────────────────┐
│   🏗  NHAI Field Terminal   │
│                             │
│   Worker ID  [__________]  │
│   4-digit PIN [____]        │
│                             │
│   [  PROCEED TO SCAN  ]     │
└─────────────────────────────┘
```
- Worker selects their ID from a locally stored list
- PIN entry creates a time-limited session token
- Routes to `VerificationScreen`

---

### 3.3 VerificationScreen *(Core screen)*
**Purpose:** Live biometric gate — face detection, liveness, matching.
```
┌─────────────────────────────────────────────┐
│  ● OFFLINE SECURE TERMINAL                  │
├─────────────────────────────────────────────┤
│                                             │
│      ┌──────────────────────┐              │
│      │                      │              │
│      │  [LIVE CAMERA FEED]  │              │
│      │   ╔══════════╗       │              │
│      │   ║          ║       │              │
│      │   ║  FACE    ║       │              │
│      │   ║  LOCK    ║       │              │
│      │   ╚══════════╝       │              │
│      └──────────────────────┘              │
│                                             │
│  Active Liveness:  🟡 BLINK REQUIRED        │
│  Passive FAS:      🟢 CLEAR                 │
│  Identity Match:   ── PENDING              │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  AWAITING VERIFICATION              │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

**State Machine:**
```
IDLE → FACE_LOCKED → BLINK_PENDING → PASSIVE_FAS_CHECK → MATCHING → VERIFIED / REJECTED
```

**Events consumed from native bridge:**
| Native Event | JS Action |
|---|---|
| `onBiometricAlert` | Show `SecurityAlertModal` with crimson overlay |
| `BLINK_REQUIRED` | Animate "blink prompt" pulsing eye icon |
| `SPOOF_DETECTED` | Trigger full-screen spoof lockout (3s cooldown) |
| `SUCCESS` | Green shimmer, log attendance, navigate to success card |
| `MATCH_FAILED` | Show failure card, retry after 2s |

---

### 3.4 EnrollmentScreen
**Purpose:** Admin-supervised one-time face template registration.
```
┌─────────────────────────────────────────────┐
│  Secure Profile Registration                │
├─────────────────────────────────────────────┤
│  Worker ID:   [NHAI-DEL-0419_________]      │
│  Full Name:   [Bala Saravanan_________]     │
│  Department:  [Highway Construction ▼]      │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │        [LIVE CAMERA FEED]            │   │
│  │    Face auto-captures after 3s lock  │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  [  REGISTER TEMPLATE (AES-256 SECURED)  ]  │
└─────────────────────────────────────────────┘
```
- Calls `BiometricBridge.enrollFace(workerId, name)`
- On success: encrypted 128-D vector written to SQLCipher
- Shows `EncryptionConfirmationModal` with key fingerprint

---

### 3.5 AttendanceLogScreen
**Purpose:** View offline queue status and sync history.
```
┌─────────────────────────────────────────────┐
│  Offline Queue     [3 logs pending] 🔒       │
│  Last Sync         25 May 2026, 14:22       │
├─────────────────────────────────────────────┤
│  ● NHAI-DEL-0419   08:02 AM   ✓ Verified   │
│  ● NHAI-DEL-0312   08:45 AM   ✓ Verified   │
│  ● NHAI-DEL-0512   09:10 AM   ✗ Failed     │
│  ● NHAI-DEL-0419   12:00 PM   ✓ Verified   │
├─────────────────────────────────────────────┤
│  [  SYNC TO CLOUD (AWS)  ]   ↑ 3 pending    │
└─────────────────────────────────────────────┘
```
- Reads decrypted attendance queue from SQLCipher
- Sync button calls `syncService.syncToCloud()`
- Shows per-record sync status: pending / synced / failed

---

### 3.6 AdminScreen
**Purpose:** Site supervisor management panel.
- View all enrolled worker profiles
- Delete / re-enroll workers
- Download attendance CSV report
- Configure site code and shift timings
- Toggle: enforce blink only / enforce blink + passive FAS

---

## Phase 4: Native Bridge Wrapper

**Goal:** Create a clean TypeScript API over the native modules so no screen directly calls `NativeModules`.

**`src/native/BiometricBridge.ts`**
```typescript
import { NativeModules, NativeEventEmitter, Platform } from 'react-native';

const NativeModule = NativeModules.NHAI_FaceRecognitionModule;
const emitter = new NativeEventEmitter(NativeModule);

export type VerificationResult =
  | 'BLINK_REQUIRED'
  | 'SPOOF_DETECTED'
  | 'NO_FACE_DETECTED'
  | { status: 'SUCCESS'; matchScore: number }
  | { status: 'MATCH_FAILED'; matchScore: number };

const BiometricBridge = {
  // Initialize TFLite engines + hardware keystore on boot
  initializeModels: (): Promise<string> =>
    NativeModule.initializeModels(),

  // Perform live 1:1 biometric verification against enrolled embedding
  verifyFace: (enrolledTemplate: number[]): Promise<VerificationResult> =>
    NativeModule.verifyFace(enrolledTemplate),

  // Register new worker embedding into encrypted SQLCipher DB
  enrollFace: (workerId: string, name: string): Promise<boolean> =>
    NativeModule.enrollFace(workerId, name),

  // Subscribe to security alerts (spoof events) from native thread
  onSecurityAlert: (callback: (msg: string) => void) =>
    emitter.addListener('onBiometricAlert', (e) => callback(e.message)),
};

export default BiometricBridge;
```

---

## Phase 5: Offline Sync Background Job

**Goal:** Auto-push encrypted attendance logs to AWS when network is restored.

**`src/services/syncService.ts`**
```typescript
import NetInfo from '@react-native-community/netinfo';
import apiService from './apiService';
import BiometricBridge from '../native/BiometricBridge';

export const initSyncListener = () => {
  NetInfo.addEventListener(async (state) => {
    if (state.isConnected) {
      await syncToCloud();
    }
  });
};

export const syncToCloud = async () => {
  // 1. Pull encrypted + signed logs from native SQLCipher queue
  const logs = await BiometricBridge.getPendingLogs();
  if (!logs.length) return;

  // 2. POST each signed payload to AWS API Gateway
  for (const log of logs) {
    const res = await apiService.submitAttendanceLog(log);
    if (res.ok) {
      // 3. Clear from local queue only after server confirmation
      await BiometricBridge.clearSyncedLog(log.queueId);
    }
  }
};
```

---

## Frontend Deliverable Checklist

| # | Deliverable | Status |
|---|---|---|
| 1 | Project bootstrapped with TypeScript + Navigation | ⬜ |
| 2 | Design system tokens + Inter font configured | ⬜ |
| 3 | SplashScreen with model initialization | ⬜ |
| 4 | LoginScreen with worker ID + PIN | ⬜ |
| 5 | VerificationScreen with live biometric HUD | ⬜ |
| 6 | EnrollmentScreen with encrypted template storage | ⬜ |
| 7 | AttendanceLogScreen with SQLCipher queue list | ⬜ |
| 8 | AdminScreen for site supervisor controls | ⬜ |
| 9 | BiometricBridge.ts native module wrapper | ⬜ |
| 10 | Offline sync background job via NetInfo | ⬜ |
| 11 | Presentation attack modal + animations | ⬜ |
| 12 | Android + iOS build and physical device test | ⬜ |
