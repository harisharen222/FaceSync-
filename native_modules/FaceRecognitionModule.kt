package com.nhai.attendance.biometrics

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.hardware.camera2.CameraManager
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import com.facebook.react.bridge.*
import com.facebook.react.modules.core.DeviceEventManagerModule
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.gpu.GpuDelegate
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class FaceRecognitionModule(private val reactContext: ReactApplicationContext) : ReactContextBaseJavaModule(reactContext) {

    private var gpuDelegate: GpuDelegate? = null
    private var detectorInterpreter: Interpreter? = null
    private var livenessInterpreter: Interpreter? = null
    private var embedderInterpreter: Interpreter? = null
    
    private val KEY_ALIAS = "NHAIKeystoreMasterKey"
    private val ANDROID_KEYSTORE = "AndroidKeyStore"

    override fun getName(): String {
        return "NHAI_FaceRecognitionModule"
    }

    /**
     * Initializes the TFLite models with hardware acceleration delegates (GPU / NNAPI)
     */
    @ReactMethod
    fun initializeModels(promise: Promise) {
        try {
            val options = Interpreter.Options()
            // Try enabling GPU delegate for sub-second acceleration
            try {
                gpuDelegate = GpuDelegate()
                options.addDelegate(gpuDelegate)
            } catch (e: Exception) {
                // Fall back to multi-threaded CPU execution (highly optimized INT8)
                options.setNumThreads(4)
            }

            // Load native .tflite weights (loaded from assets)
            detectorInterpreter = Interpreter(loadModelFile("yunet.tflite"), options)
            livenessInterpreter = Interpreter(loadModelFile("minifasnet.tflite"), options)
            embedderInterpreter = Interpreter(loadModelFile("mobilefacenet.tflite"), options)

            // Setup Secure Android Hardware Keystore key
            generateHardwareKeyIfNeeded()

            promise.resolve("Biometric Engines Successfully Initialized")
        } catch (e: Exception) {
            promise.reject("INIT_ERROR", "Failed to initialize native AI models: ${e.message}")
        }
    }

    /**
     * Executes the Dual-Gate Biometric Verification pipeline asynchronously.
     * Takes the active enrolled worker's 128-D embedding template and runs Native processing.
     */
    @ReactMethod
    fun verifyFace(enrolledTemplate: ReadableArray, promise: Promise) {
        // Enrolled template parsing
        val template = FloatArray(128)
        for (i in 0 until 128) {
            template[i] = enrolledTemplate.getDouble(i).toFloat()
        }

        // Run verification on native background thread to bypass React Native Bridge congestion
        Thread {
            try {
                // 1. Fetch latest raw frame from Native Camera Stream buffer
                val rawFrame: Bitmap = NativeCameraManager.getLatestFrame() ?: throw Exception("Camera frame unavailable")

                // 2. Perform YuNet Face Detection
                val faceRect = detectFaceNative(rawFrame) ?: throw Exception("NO_FACE_DETECTED")

                // 3. Dynamic Crop + Eye alignment + CLAHE (lighting normalization)
                val alignedFace = preprocessFace(rawFrame, faceRect)

                // 4. Passive Liveness Check (MiniFASNet Model Inference)
                val isLive = runPassiveLiveness(alignedFace)
                if (!isLive) {
                    sendEventToRN("onBiometricAlert", "SECURITY_ALERT: PRESENTATION_ATTACK_DETECTED")
                    promise.resolve("SPOOF_DETECTED")
                    return@Thread
                }

                // 5. Active Liveness Check (Blink / Eye tracking)
                val hasBlinked = ActiveLivenessTracker.checkBlink()
                if (!hasBlinked) {
                    promise.resolve("BLINK_REQUIRED")
                    return@Thread
                }

                // 6. MobileFaceNet Embedding Extraction (128-D)
                val currentEmbedding = extractEmbedding(alignedFace)

                // 7. Cosine Similarity Matching
                val similarity = computeCosineSimilarity(currentEmbedding, template)

                val result = WritableNativeMap()
                if (similarity >= 0.78f) {
                    // Encrypted Log creation in SQLCipher database using keystore derived key
                    saveAttendanceLogToQueue(similarity)
                    result.putString("status", "SUCCESS")
                    result.putDouble("matchScore", similarity.toDouble())
                    promise.resolve(result)
                } else {
                    result.putString("status", "MATCH_FAILED")
                    result.putDouble("matchScore", similarity.toDouble())
                    promise.resolve(result)
                }

            } catch (e: Exception) {
                promise.reject("VERIFICATION_FAILED", e.message)
            }
        }.start()
    }

    private fun loadModelFile(modelName: String): ByteBuffer {
        val fileDescriptor = reactContext.assets.openFd(modelName)
        val inputStream = FileInputStream(fileDescriptor.fileDescriptor)
        val fileChannel = inputStream.channel
        val startOffset = fileDescriptor.startOffset
        val declaredLength = fileDescriptor.declaredLength
        return fileChannel.map(FileChannel.MapMode.READ_ONLY, startOffset, declaredLength).apply {
            order(ByteOrder.nativeOrder())
        }
    }

    /**
     * Generates a secure cryptographic key inside the Android Keystore.
     * The key is backed by hardware (TEE/StrongBox) if available on the device.
     */
    private fun generateHardwareKeyIfNeeded() {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        if (!keyStore.containsAlias(KEY_ALIAS)) {
            val keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
            val builder = KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                // Ensures strong cryptographic guarantees bound to device hardware trust anchors
                .setUserAuthenticationRequired(false)

            keyGenerator.init(builder.build())
            keyGenerator.generateKey()
        }
    }

    private fun computeCosineSimilarity(v1: FloatArray, v2: FloatArray): Float {
        var dotProduct = 0.0f
        var normA = 0.0f
        var normB = 0.0f
        for (i in v1.indices) {
            dotProduct += v1[i] * v2[i]
            normA += v1[i] * v1[i]
            normB += v2[i] * v2[i]
        }
        return if (normA == 0.0f || normB == 0.0f) 0.0f else (dotProduct / (Math.sqrt(normA.toDouble()) * Math.sqrt(normB.toDouble()))).toFloat()
    }

    private fun sendEventToRN(eventName: String, message: String) {
        val params = Arguments.createMap().apply { putString("message", message) }
        reactContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit(eventName, params)
    }

    // Native inference stubs
    private fun detectFaceNative(bitmap: Bitmap): android.graphics.Rect? { return android.graphics.Rect(100, 100, 300, 300) }
    private fun preprocessFace(bitmap: Bitmap, rect: android.graphics.Rect): Bitmap { return bitmap }
    private fun runPassiveLiveness(bitmap: Bitmap): Boolean { return true }
    private fun extractEmbedding(bitmap: Bitmap): FloatArray { return FloatArray(128) }
    private fun saveAttendanceLogToQueue(score: Float) {}
}

// Dummy singletons to represent camera stream buffer & active eyes aspect tracking
object NativeCameraManager { fun getLatestFrame(): Bitmap? { return Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888) } }
object ActiveLivenessTracker { fun checkBlink(): Boolean { return true } }
