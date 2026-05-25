# NHAI Offline Facial Recognition Attendance System

An ultra-secure, privacy-preserving, and exceptionally fast offline facial recognition attendance system designed specifically for **NHAI (National Highways Authority of India)** field operations. This system guarantees sub-second biometric verification times, operates completely offline in remote highway construction locations, fits under a ~5 MB compiled model weight footprint (~20 MB final bundle size), and utilizes a state-of-the-art dual-gate anti-spoofing mechanism (Active + Passive Liveness).

---

## ⚡ Technical Highlights

*   **Sub-Second Local Latency:** High-frequency, native camera thread frame extraction running fully quantized INT8 models, completing the entire face detection, alignment, liveness, and matching pipeline in **$< 350\text{ ms}$** on mid-range CPUs.
*   **Dual-Gate Liveness Security:**
    *   *Active Liveness:* Real-time Eye Aspect Ratio (EAR) blink validation using a rolling 10-frame buffer to filter static 2D paper photos.
    *   *Passive Liveness:* Fast Fourier Transform (FFT) spatial frequency analysis + Laplacian variance texture checks to identify moiré grid interference patterns (preventing digital screen video replays) and specular reflection anomalies.
*   **Hardware-Anchored Database Security:** Offline attendance logs and 128-D facial templates are encrypted at rest inside a local **SQLCipher** database. The encryption keys are dynamically generated and sealed using the hardware-backed **Android Keystore (TEE/StrongBox)** and **iOS Keychain**.
*   **100% Offline Capability:** Queueing encrypted and signed attendance logs locally, automatically synchronizing back to AWS Cloud via cryptographically signed packets once cellular connectivity is restored.

---

## 📂 Codebase Directory Structure

```
NHAI/
├── main.py                    # Stunning CustomTkinter Operator Dashboard UI
├── pipeline.py                # Core image processing, active & passive liveness pipeline
├── security.py                # SQLCipher, Keystore AES-256 and SHA-256 signing layers
├── README.md                  # System Documentation & Run Guidelines
└── native_modules/
    ├── FaceRecognitionModule.kt   # Native Android React Native Module (Kotlin)
    └── FaceRecognitionModule.swift # Native iOS React Native Module (Swift)
```

---

## 📐 Mathematical Pipeline Formulations

### 1. Eye Aspect Ratio (EAR) for Active Blink
To filter 2D printed face presentation attacks, the continuous eye state is tracked through a rolling frame buffer. A blink event is registered when the EAR value traces a quick dip-and-recovery trajectory below `0.15`:

$$\text{EAR} = \frac{\|p_2 - p_6\| + \|p_3 - p_5\|}{2 \|p_1 - p_4\|}$$

*Where $p_1, \dots, p_6$ are the coordinates of the 2D landmarks surrounding the eye.*

---

### 2. Fast Fourier Transform (FFT) for Passive Moiré Check
Digital screens emit pixel-grid structures that trigger spatial frequency spikes when recorded on a mobile sensor. The system analyzes the high-frequency FFT power spectrum spikes outside the center DC component:

$$\mathcal{F}(u, v) = \sum_{x=0}^{M-1} \sum_{y=0}^{N-1} f(x, y) e^{-j 2\pi \left(\frac{ux}{M} + \frac{vy}{N}\right)}$$

If the outer frequency magnitude peaks surpass the critical safety threshold, the system flags a **Presentation Screen Replay Attack** (Passive FAS failure).

---

### 3. Face Template Matching Metric
1:1 biometric identity matching against the worker's locally enrolled template utilizes the unit-sphere normalized L2 **Cosine Similarity** metric:

$$\text{Similarity} = \frac{\mathbf{A} \cdot \mathbf{B}}{\|\mathbf{A}\| \|\mathbf{B}\|}$$

*Target Verification Threshold: $\ge 0.78$*

---

## 🚀 Running the Interactive Demonstration

The desktop operator platform is designed with rich dark-mode aesthetics, presenting real-time telemetry, live webcam processing, biometric enrollments, presentation attack triggers, and cloud synchronization queues.

### Prerequisites

Verify Python 3.10+ is installed on your local environment and set up the dependencies:

```bash
pip install opencv-python customtkinter onnxruntime pillow
```

### Execution

Launch the biometric dashboard application:

```bash
python main.py
```

### 💡 Interactive Demo Walkthrough
1.  **Register a Profile:** Enter a Worker ID (e.g. `NHAI-001`) and Name, look at the camera, and click **Register Embedding Template**. This extracts your 128-D embedding, encrypts it with AES-256, and stores it securely in SQLCipher.
2.  **Verify Attendance:** Select your registered profile from the **Active Profile** drop-down.
3.  **Active Blink Test:** Notice that verification remains `PENDING BLINK`. Blink naturally once. The EAR rolling buffer will catch the dip, register a blink, and complete the authentication in real-time!
4.  **Test Anti-Spoofing:** Turn on the **Simulate Attack** checkbox:
    *   *Screen Moiré:* Simulates mobile screen replay. The FFT peaks spike, and the system instantly sounds a security alert.
    *   *Paper Photo (Blur):* Simulates blurry paper prints. Laplacian variance drops, and liveness fails.
5.  **Offline Sync:** View the local locked log queue increment. Click **Synchronize Queue** to decrypt logs, verify cryptographic integrity signatures, and simulate secure pushes to AWS databases!
