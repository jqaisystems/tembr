// Client-side keep-safe for unsaved recording takes. One draft slot in
// IndexedDB, restored by the record flow after a refresh or accidental exit.
// Deliberately never server-side: creating a voice requires the consent step,
// and an auto-created voice would bypass it. Every function fails silently
// (private browsing, storage pressure) so the record flow never breaks.
import type { Transcription } from "./api";

export type RecordingDraft = {
  blob: Blob;
  qc: Transcription | null;
  scriptTitle: string | null;
  situation: string | null;
  language: string;
  savedAt: number;
};

const DB = "voice-studio";
const STORE = "drafts";
const KEY = "current";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveDraft(draft: RecordingDraft): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  try {
    const db = await open();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(draft, KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    // storage unavailable: the beforeunload guard is the fallback
  }
}

export async function loadDraft(): Promise<RecordingDraft | null> {
  if (typeof indexedDB === "undefined") return null;
  try {
    const db = await open();
    const draft = await new Promise<RecordingDraft | null>((resolve, reject) => {
      const req = db.transaction(STORE).objectStore(STORE).get(KEY);
      req.onsuccess = () => resolve(req.result ?? null);
      req.onerror = () => reject(req.error);
    });
    db.close();
    return draft;
  } catch {
    return null;
  }
}

export async function clearDraft(): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  try {
    const db = await open();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    // ignore
  }
}
