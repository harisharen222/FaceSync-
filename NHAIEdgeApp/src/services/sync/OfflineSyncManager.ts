// Dynamic require used inside initDB to prevent static evaluation crashes during Chrome Debugging
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
  private db: any = null;
  private isSyncing = false;
  private config: Partial<SyncConfig> = {};
  private unsubscribeNetInfo: (() => void) | null = null;
  private isJsiAvailable = true;

  public configure(config: Partial<SyncConfig>) {
    this.config = { ...this.config, ...config };
  }

  public initDB() {
    if (this.db) return;

    try {
      const sqliteModule = require('react-native-quick-sqlite');
      const openFn = sqliteModule ? sqliteModule.open : undefined;
      if (typeof openFn === 'undefined') {
        throw new Error('JSI open() function is undefined. This usually happens when Chrome Remote Debugging is enabled.');
      }
      this.db = openFn({ name: 'nhai_offline.sqlite' });
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
      this.isJsiAvailable = true;
      console.log('OfflineSyncManager initialized successfully with SQLite JSI ✓');
    } catch (error) {
      console.warn('SQLite JSI not available. Falling back to in-memory mock storage. Detail:', error);
      this.isJsiAvailable = false;
      // Initialize an in-memory mock database interface to prevent runtime errors
      this.db = {
        execute: (query: string, params?: any[]) => {
          console.log('[MOCK DB EXECUTE]', query, params);
          return { rows: { _array: [] } };
        }
      };
    }
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

    if (this.isJsiAvailable && this.db) {
      this.db.execute(
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
    } else {
      console.log('[OfflineSyncManager JSI-Mock] Saved offline record successfully:', record);
      // Attempt direct network sync fallback as the SQLite queue is disabled in debugger mode
      try {
        const { backendBaseUrl, deviceId, deviceJwt } = this.config;
        if (backendBaseUrl && deviceId && deviceJwt) {
          let targetUrl = backendBaseUrl.replace(/\/$/, '');
          if (targetUrl.includes(':8000')) {
            targetUrl = targetUrl.replace(':8000', ':8003');
          }
          fetch(`${targetUrl}/attendance/sync`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${deviceJwt}`,
            },
            body: JSON.stringify({ device_id: deviceId, records: [record] }),
          }).catch(err => console.warn('Direct fallback sync failed:', err));
        }
      } catch (e) {
        console.warn('Fallback sync failed:', e);
      }
    }

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

      let targetUrl = backendBaseUrl.replace(/\/$/, '');
      if (targetUrl.includes(':8000')) {
        targetUrl = targetUrl.replace(':8000', ':8003');
      }

      const response = await fetch(`${targetUrl}/attendance/sync`, {
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
    } catch (error) {
      console.warn('OfflineSyncManager sync request failed (AWS connection error):', error);
    } finally {
      this.isSyncing = false;
    }
  }
}

export const offlineSyncManager = new OfflineSyncManager();