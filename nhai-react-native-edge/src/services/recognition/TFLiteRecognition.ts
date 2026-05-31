export class TFLiteRecognition {
  async loadModel() {
    console.log('TFLite disabled for debugging');
    return true;
  }

  async generateEmbedding() {
    return new Array(128).fill(0);
  }

  cosineSimilarity() {
    return 0;
  }
}

export default new TFLiteRecognition();