import Foundation
import AVFoundation
import React
import TensorFlowLite

@objc(NHAIFaceRecognitionModule)
class FaceRecognitionModule: RCTEventEmitter {
  
  private var detectorInterpreter: Interpreter?
  private var livenessInterpreter: Interpreter?
  private var embedderInterpreter: Interpreter?
  
  private let keychainService = "com.nhai.biometrics.keychain"
  private let keychainAccount = "NHAIKeystoreMasterKey"
  
  override func supportedEvents() -> [String]! {
    return ["onBiometricAlert"]
  }
  
  @objc override static func requiresMainQueueSetup() -> Bool {
    return false
  }
  
  /**
   * Initializes iOS Edge ML inference engines
   */
  @objc
  func initializeModels(_ resolve: @escaping RCTPromiseResolveBlock, rejecter reject: @escaping RCTPromiseRejectBlock) {
    do {
      var options = Interpreter.Options()
      options.threadCount = 4
      
      // Try to load weights from app main bundle
      guard let detectorPath = Bundle.main.path(forResource: "yunet", ofType: "tflite"),
            let livenessPath = Bundle.main.path(forResource: "minifasnet", ofType: "tflite"),
            let embedderPath = Bundle.main.path(forResource: "mobilefacenet", ofType: "tflite") else {
        throw NSError(domain: "NHAIError", code: 404, userInfo: [NSLocalizedDescriptionKey: "Model files missing from main bundle"])
      }
      
      detectorInterpreter = try Interpreter(modelPath: detectorPath, options: options)
      livenessInterpreter = try Interpreter(modelPath: livenessPath, options: options)
      embedderInterpreter = try Interpreter(modelPath: embedderPath, options: options)
      
      // Secure local keychain storage setup for database encryption keys
      setupSecureKeychainKey()
      
      resolve("iOS Face Verification Engines Successfully Loaded")
    } catch {
      reject("INIT_ERROR", "Failed to load iOS TFLite interpreters: \(error.localizedDescription)", error)
    }
  }
  
  /**
   * Main dual-gate offline verification entry point for iOS devices
   */
  @objc
  func verifyFace(_ enrolledTemplate: [Double], resolver resolve: @escaping RCTPromiseResolveBlock, rejecter reject: @escaping RCTPromiseRejectBlock) {
    let template = enrolledTemplate.map { Float($0) }
    
    // Execute on global background QoS utility thread to prevent blocking main UI loop
    DispatchQueue.global(qos: .userInitiated).async { [weak self] in
      guard let self = self else { return }
      
      do {
        // 1. Fetch current pixel buffer from iOS AVFoundation camera stream
        guard let pixelBuffer = NativeCameraManager.shared.getLatestBuffer() else {
          throw NSError(domain: "NHAIError", code: 500, userInfo: [NSLocalizedDescriptionKey: "iOS Camera buffer unavailable"])
        }
        
        // 2. Perform Face landmarks detection (YuNet)
        guard let faceBounds = self.detectFaceNative(pixelBuffer) else {
          resolve("NO_FACE_DETECTED")
          return
        }
        
        // 3. Affine eye alignment and rotation
        let alignedFaceBuffer = self.alignFace(pixelBuffer, bounds: faceBounds)
        
        // 4. Passive Presentation Attack Detection (MiniFASNet)
        let isLive = self.runPassiveLiveness(alignedFaceBuffer)
        guard isLive else {
          self.sendEvent(withName: "onBiometricAlert", body: ["message": "SECURITY_ALERT: SCREEN_SPOOF_DETECTED"])
          resolve("SPOOF_DETECTED")
          return
        }
        
        // 5. Active Temporal eye blink validation
        let activeCheck = ActiveLivenessTracker.shared.checkBlink()
        guard activeCheck else {
          resolve("BLINK_REQUIRED")
          return
        }
        
        // 6. MobileFaceNet 128-D Embedding extraction
        let currentEmbedding = self.extractEmbedding(alignedFaceBuffer)
        
        // 7. Calculate Cosine Distance
        let score = self.computeCosineSimilarity(currentEmbedding, template)
        
        var response = [String: Any]()
        if score >= 0.78 {
          // Encrypt and log attendance record local database
          self.saveAttendanceLogToQueue(score)
          response["status"] = "SUCCESS"
          response["matchScore"] = score
          resolve(response)
        } else {
          response["status"] = "MATCH_FAILED"
          response["matchScore"] = score
          resolve(response)
        }
        
      } catch {
        reject("VERIFICATION_FAILED", error.localizedDescription, error)
      }
    }
  }
  
  /**
   * Secures a unique symmetric encryption key inside the iOS Keychain
   * utilizing kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly to survive reboot cycles safely.
   */
  private func setupSecureKeychainKey() {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: keychainService,
      kSecAttrAccount as String: keychainAccount
    ]
    
    let status = SecItemCopyMatching(query as CFDictionary, nil)
    if status == errSecItemNotFound {
      let keyData = (0..<32).map { _ in UInt8.random(in: 0...255) }
      let addQuery: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: keychainService,
        kSecAttrAccount as String: keychainAccount,
        kSecValueData as String: Data(keyData),
        kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
      ]
      SecItemAdd(addQuery as CFDictionary, nil)
    }
  }
  
  private func computeCosineSimilarity(_ v1: [Float], _ v2: [Float]) -> Float {
    var dotProduct: Float = 0.0
    var normA: Float = 0.0
    var normB: Float = 0.0
    for i in 0..<v1.count {
      dotProduct += v1[i] * v2[i]
      normA += v1[i] * v1[i]
      normB += v2[i] * v2[i]
    }
    return (normA == 0.0 || normB == 0.0) ? 0.0 : (dotProduct / (sqrt(normA) * sqrt(normB)))
  }
  
  // Swift native ML stubs
  private func detectFaceNative(_ buffer: CVPixelBuffer) -> CGRect? { return CGRect(x: 100, y: 100, width: 200, height: 200) }
  private func alignFace(_ buffer: CVPixelBuffer, bounds: CGRect) -> CVPixelBuffer { return buffer }
  private func runPassiveLiveness(_ buffer: CVPixelBuffer) -> Bool { return true }
  private func extractEmbedding(_ buffer: CVPixelBuffer) -> [Float] { return Array(repeating: 0.0, count: 128) }
  private func saveAttendanceLogToQueue(_ score: Float) {}
}

// Dummy singletons representing iOS AVFoundation streams & active eyes buffers
class NativeCameraManager {
  static let shared = NativeCameraManager()
  func getLatestBuffer() -> CVPixelBuffer? { return nil }
}
class ActiveLivenessTracker {
  static let shared = ActiveLivenessTracker()
  func checkBlink() -> Bool { return true }
}
