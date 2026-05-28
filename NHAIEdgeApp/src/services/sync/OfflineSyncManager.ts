import { open, QuickSQLiteConnection } from 'react-native-quick-sqlite';
import NetInfo from '@react-native-community/netinfo';
import { v4 as uuidv4 } from 'uuid';
import { cryptoSigner } from '../crypto/CryptoSigner';
import { JsonValue } from '../crypto/canonicalJson';

export interface AttendancePayload {
  id: string;
  worker_id: string;
  timestamp_utc: string;
  confidence: number;
  liveness_score: number;
  liveness_passed: boolean;
}

export interface AttendanceRecord extends AttendancePayload {
  signature_hex: string;
}

interface SyncConfig {
  backendBaseUrl: string;
  deviceId: string;
  deviceJwt: string;
}

class OfflineSyncManager {
  private db: QuickSQLiteConnection | null = null;
  private isSyncing = false;
  private config: Partial<SyncConfig> = {};
  private unsubscribeNetInfo: (() => void) | null = null;

  public configure(config: Partial<SyncConfig>) {
    this.config = { ...this.config, ...config };
  }

  public initDB() {
    if (this.db) return;

    this.db = open({ name: 'nhai_offline.sqlite' });
    this.db.execute(`
      CREATE TABLE IF NOT EXISTS pending_sync (
        id TEXT PRIMARY KEY,
        worker_id TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        confidence REAL NOT NULL,
        liveness_score REAL NOT NULL,
        liveness_passed INTEGER NOT NULL,
        signature_hex TEXT NOT NULL
      )
    `);
  }

  public startNetworkSync() {
    if (this.unsubscribeNetInfo) return;

    this.unsubscribeNetInfo = NetInfo.addEventListener((state) => {
      if (state.isConnected) {
        this.triggerSync();
      }
    });
  }

  public async saveAttendance(
    workerId: string,
    livenessScore: number,
    confidence: number,
  ): Promise<AttendanceRecord> {
    if (!this.db) this.initDB();

    const payload: AttendancePayload = {
      id: uuidv4(),
      worker_id: workerId,
      timestamp_utc: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
      confidence,
      liveness_score: livenessScore,
      liveness_passed: livenessScore >= 0.65,
    };
    const signature_hex = cryptoSigner.signPayload(payload as unknown as JsonValue);
    const record: AttendanceRecord = { ...payload, signature_hex };

    this.db!.execute(
      `INSERT INTO pending_sync (
        id,
        worker_id,
        timestamp_utc,
        confidence,
        liveness_score,
        liveness_passed,
        signature_hex
      ) VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        record.id,
        record.worker_id,
        record.timestamp_utc,
        record.confidence,
        record.liveness_score,
        record.liveness_passed ? 1 : 0,
        record.signature_hex,
      ],
    );

    await this.triggerSync();
    return record;
  }

  public async triggerSync() {
    if (this.isSyncing || !this.db) return;

    const { backendBaseUrl, deviceId, deviceJwt } = this.config;
    if (!backendBaseUrl || !deviceId || !deviceJwt) {
      return;
    }

    const state = await NetInfo.fetch();
    if (!state.isConnected) {
      return;
    }

    this.isSyncing = true;
    try {
      const result = this.db.execute('SELECT * FROM pending_sync ORDER BY timestamp_utc ASC LIMIT 500');
      const rows = result.rows?._array ?? [];
      const records = rows.map((row: any): AttendanceRecord => ({
        id: row.id,
        worker_id: row.worker_id,
        timestamp_utc: row.timestamp_utc,
        confidence: Number(row.confidence),
        liveness_score: Number(row.liveness_score),
        liveness_passed: row.liveness_passed === 1,
        signature_hex: row.signature_hex,
      }));

      if (records.length === 0) return;

      const response = await fetch(`${backendBaseUrl.replace(/\/$/, '')}/attendance/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${deviceJwt}`,
        },
        body: JSON.stringify({ device_id: deviceId, records }),
      });

      if (!response.ok) {
        return;
      }

      const placeholders = records.map(() => '?').join(',');
      this.db.execute(
        `DELETE FROM pending_sync WHERE id IN (${placeholders})`,
        records.map((record) => record.id),
      );
    } finally {
      this.isSyncing = false;
    }
  }
}

export const offlineSyncManager = new OfflineSyncManager();
