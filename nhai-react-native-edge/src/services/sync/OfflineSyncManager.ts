import { open, QuickSQLiteConnection } from 'react-native-quick-sqlite';
import NetInfo from '@react-native-community/netinfo';
import { v4 as uuidv4 } from 'uuid';
import { cryptoSigner } from '../crypto/CryptoSigner';

export interface AttendanceRecord {
  id: string;
  worker_id: string;
  timestamp: string;
  liveness_score: number;
  confidence_score: number;
  device_id: string;
  synced: boolean;
  signature?: string;
}

/**
 * Manages the offline storage and synchronization of attendance records.
 * Uses react-native-quick-sqlite for high-performance local storage.
 */
class OfflineSyncManager {
  private db: QuickSQLiteConnection | null = null;
  private isSyncing = false;
  
  // Replace this with your actual deployed AWS API Gateway or ALB endpoint
  private readonly BACKEND_URL = "http://13.48.24.253:8002/attendance/sync"; 

  public initDB() {
    this.db = open({ name: 'nhai_offline.sqlite' });
    this.db.execute(`
      CREATE TABLE IF NOT EXISTS attendance (
        id TEXT PRIMARY KEY,
        worker_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        liveness_score REAL NOT NULL,
        confidence_score REAL NOT NULL,
        device_id TEXT NOT NULL,
        signature TEXT NOT NULL,
        synced INTEGER DEFAULT 0
      )
    `);
    console.log("Offline SQLite Database initialized.");
  }

  /**
   * Saves a new attendance record locally. Called immediately upon successful face match.
   */
  public async saveAttendance(
    workerId: string, 
    livenessScore: number, 
    confidenceScore: number,
    deviceId: string
  ): Promise<void> {
    if (!this.db) this.initDB();

    const record: AttendanceRecord = {
      id: uuidv4(),
      worker_id: workerId,
      timestamp: new Date().toISOString(),
      liveness_score: livenessScore,
      confidence_score: confidenceScore,
      device_id: deviceId,
      synced: false
    };

    // 1. Create the exact payload string the backend expects
    const payloadToSign = `${record.worker_id}|${record.timestamp}|${record.liveness_score}|${record.confidence_score}|${record.device_id}`;
    
    // 2. Cryptographically sign it offline
    record.signature = cryptoSigner.signPayload(payloadToSign);

    // 3. Save to local SQLite
    this.db!.execute(
      `INSERT INTO attendance (id, worker_id, timestamp, liveness_score, confidence_score, device_id, signature, synced)
       VALUES (?, ?, ?, ?, ?, ?, ?, 0)`,
      [record.id, record.worker_id, record.timestamp, record.liveness_score, record.confidence_score, record.device_id, record.signature]
    );
    console.log(`Saved record offline for worker: ${workerId}`);

    // 4. Opportunistically try to sync right now
    this.triggerSync();
  }

  /**
   * Checks network connectivity and pushes unsynced records to the backend.
   * If successful, purges the local records.
   */
  public async triggerSync() {
    if (this.isSyncing || !this.db) return;

    const state = await NetInfo.fetch();
    if (!state.isConnected) {
      console.log("No network connection. Records will remain offline until network is restored.");
      return;
    }

    this.isSyncing = true;
    try {
      const result = this.db.execute('SELECT * FROM attendance WHERE synced = 0');
      const records = result.rows?._array as AttendanceRecord[] | undefined;

      if (!records || records.length === 0) {
        this.isSyncing = false;
        return;
      }

      console.log(`Found ${records.length} offline records. Attempting sync to ${this.BACKEND_URL}...`);

      // Push to backend
      const response = await fetch(this.BACKEND_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer YOUR_DEVICE_JWT_TOKEN' // from auth-service
        },
        body: JSON.stringify({ records })
      });

      if (response.ok) {
        // Successful Sync -> PURGE local data to save space
        const syncedIds = records.map(r => `'${r.id}'`).join(',');
        this.db.execute(`DELETE FROM attendance WHERE id IN (${syncedIds})`);
        console.log(`Successfully synced and purged ${records.length} records.`);
      } else {
        console.error("Sync failed, server returned:", response.status);
      }
    } catch (error) {
      console.error("Sync process encountered an error:", error);
    } finally {
      this.isSyncing = false;
    }
  }
}

export const offlineSyncManager = new OfflineSyncManager();
