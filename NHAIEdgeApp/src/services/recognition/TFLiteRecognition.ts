import { loadTensorflowModel, Tensor } from 'react-native-fast-tflite';

/**
 * MobileFaceNet TFLite implementation for Face Recognition.
 * Extracts a feature vector (embedding) from an aligned face crop.
 */
class FaceRecognitionService {
  private model: any = null;
  private isLoaded: boolean = false;
  private modelSource: any = null;

  public configureModelSource(modelSource: any) {
    this.modelSource = modelSource;
    this.model = null;
    this.isLoaded = false;
  }

  /**
   * Initializes MobileFaceNet from an OTA-downloaded local file or a demo bundle fallback.
   */
  public async initModel() {
    if (this.isLoaded) return;
    try {
      const source = this.modelSource ?? require('../../../models/mobilefacenet.tflite');
      this.model = await loadTensorflowModel(source, []);
      this.isLoaded = true;
      console.log("MobileFaceNet model loaded successfully.");
    } catch (error) {
      console.error("Failed to load MobileFaceNet TFLite model:", error);
    }
  }

  /**
   * Extracts a 128D or 512D embedding from the provided image crop (Float32Array of RGB pixels).
   * Note: The input MUST be resized and normalized (e.g., 112x112, values [-1, 1]) before passing here.
   */
  public async getFaceEmbedding(preprocessedImagePixels: Float32Array): Promise<number[]> {
    if (!this.isLoaded) {
      throw new Error("Model not loaded");
    }

    try {
      // Run inference using react-native-fast-tflite
      const outputs: Tensor[] = await this.model.run([preprocessedImagePixels]);
      
      // The output is a flat array representing the embedding vector
      const embeddingArray = outputs[0] as unknown as Float32Array;
      
      // L2 Normalize the embedding for Cosine Similarity comparison
      return this.l2Normalize(Array.from(embeddingArray));
    } catch (error) {
      console.error("Error running TFLite inference:", error);
      return [];
    }
  }

  /**
   * Calculates the Cosine Similarity between two face embeddings.
   * Returns a score between -1 and 1. (Score > 0.6 generally indicates a match).
   */
  public compareEmbeddings(embedding1: number[], embedding2: number[]): number {
    if (embedding1.length !== embedding2.length) {
      throw new Error("Embeddings must be of the same dimension");
    }

    let dotProduct = 0;
    for (let i = 0; i < embedding1.length; i++) {
      dotProduct += embedding1[i] * embedding2[i];
    }
    return dotProduct;
  }

  private l2Normalize(vector: number[]): number[] {
    let sumSq = 0;
    for (let i = 0; i < vector.length; i++) {
      sumSq += vector[i] * vector[i];
    }
    const norm = Math.sqrt(sumSq);
    if (norm === 0) return vector;
    
    return vector.map(v => v / norm);
  }
}

export const faceRecognitionService = new FaceRecognitionService();
