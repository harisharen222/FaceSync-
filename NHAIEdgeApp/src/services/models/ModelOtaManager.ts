import RNFS from 'react-native-fs';
import { faceRecognitionService } from '../recognition/TFLiteRecognition';

interface ManifestModel {
  model_type: 'YUNET' | 'MOBILEFACENET' | string;
  version: string;
  download_url: string;
  file_size: number;
  sha256_hash: string;
}

interface ManifestResponse {
  models: ManifestModel[];
  requires_update: boolean;
}

interface ModelOtaConfig {
  backendBaseUrl: string;
  deviceJwt: string;
  deviceId: string;
}

class ModelOtaManager {
  private config: Partial<ModelOtaConfig> = {};

  public configure(config: Partial<ModelOtaConfig>) {
    this.config = { ...this.config, ...config };
  }

  public async syncModels() {
    const { backendBaseUrl, deviceJwt, deviceId } = this.config;
    if (!backendBaseUrl || !deviceJwt || !deviceId) return;

    let targetUrl = backendBaseUrl.replace(/\/$/, '');
    if (targetUrl.includes(':8000')) {
      targetUrl = targetUrl.replace(':8000', ':8004');
    }

    const response = await fetch(`${targetUrl}/models/manifest`, {
      headers: {
        Authorization: `Bearer ${deviceJwt}`,
      },
    });

    if (!response.ok) {
      throw new Error(`Model manifest failed: ${response.status}`);
    }

    const manifest = (await response.json()) as ManifestResponse;
    const modelsDir = `${RNFS.DocumentDirectoryPath}/nhai-models`;
    await RNFS.mkdir(modelsDir);

    const loadedVersions: Record<string, string> = {};
    for (const model of manifest.models) {
      const localPath = `${modelsDir}/${model.model_type}-${model.version}.tflite`;
      const exists = await RNFS.exists(localPath);

      if (!exists) {
        await RNFS.downloadFile({
          fromUrl: model.download_url,
          toFile: localPath,
        }).promise;
      }

      const actualHash = await RNFS.hash(localPath, 'sha256');
      if (actualHash.toLowerCase() !== model.sha256_hash.toLowerCase()) {
        await RNFS.unlink(localPath);
        throw new Error(`Model hash mismatch for ${model.model_type} ${model.version}`);
      }

      if (model.model_type.toUpperCase() === 'MOBILEFACENET') {
        faceRecognitionService.configureModelSource({ url: `file://${localPath}` });
      }

      loadedVersions[model.model_type] = model.version;
    }

    await this.reportStatus(loadedVersions);
  }

  private async reportStatus(models: Record<string, string>) {
    const { backendBaseUrl, deviceJwt, deviceId } = this.config;
    if (!backendBaseUrl || !deviceJwt || !deviceId || Object.keys(models).length === 0) return;

    let targetUrl = backendBaseUrl.replace(/\/$/, '');
    if (targetUrl.includes(':8000')) {
      targetUrl = targetUrl.replace(':8000', ':8004');
    }

    await fetch(`${targetUrl}/models/status`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${deviceJwt}`,
      },
      body: JSON.stringify({ device_id: deviceId, models }),
    });
  }
}

export const modelOtaManager = new ModelOtaManager();
