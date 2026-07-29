"use client";

import { useEffect, useRef, useState } from "react";
import HelpPanel from "@/components/HelpPanel";
import RecordFlow, { UPLOAD_ACCEPT } from "@/components/RecordFlow";
import Waveform from "@/components/Waveform";
import {
  cleanupVoice,
  createVoice,
  deleteVoice,
  exportVoiceUrl,
  getVoices,
  importVoice,
  revertVoiceCleanup,
  updateVoice,
  voiceSampleUrl,
  windowVoice,
  type Voice,
} from "@/lib/api";
import { languageName } from "@/lib/languages";

const ALL = "__all__";
const FAVORITES = "__fav__";

/** Good enough that a cleanup would cost more delivery than it buys back. */
const CLEAN_SNR_DB = 55;

type Edits = { name: string; description: string; collection: string };

function voiceFormFromFile(file: File): FormData {
  const form = new FormData();
  form.append("name", file.name.replace(/\.[^.]+$/, "").slice(0, 80) || "Imported voice");
  form.append("description", "Imported recording");
  form.append("language", "en");
  form.append("consent", "true");
  form.append("source", "upload");
  form.append("samples", file, file.name);
  return form;
}

export default function VoicesPage() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [edits, setEdits] = useState<Edits>({ name: "", description: "", collection: "" });
  const [editBusy, setEditBusy] = useState(false);
  const [filter, setFilter] = useState<string>(ALL);
  const [busyId, setBusyId] = useState<string | null>(null);
  const importRef = useRef<HTMLInputElement>(null);

  const collections = [...new Set(voices.map((v) => v.collection).filter(Boolean))].sort();
  const visible = voices.filter((v) =>
    filter === ALL ? true : filter === FAVORITES ? v.favorite : v.collection === filter
  );

  const onImport = async (file: File) => {
    setImporting(true);
    setError("");
    try {
      const bundle = /\.(voice|zip)$/i.test(file.name);
      // A .voice carries its own metadata; a plain recording becomes a voice
      // named after the file. Either way the server lands it as usable audio.
      const voice = bundle
        ? await importVoice(file)
        : await createVoice(voiceFormFromFile(file));
      setVoices((list) => [voice, ...list]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not import the voice.");
    } finally {
      setImporting(false);
    }
  };

  useEffect(() => {
    getVoices().then(setVoices).catch(() => {});
  }, []);

  const remove = async (v: Voice) => {
    if (!window.confirm(`Delete the voice "${v.name}"? Its reference recording is removed too.`))
      return;
    try {
      await deleteVoice(v.id);
      setVoices((list) => list.filter((x) => x.id !== v.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete the voice.");
    }
  };

  const startEdit = (v: Voice) => {
    setEditingId(v.id);
    setEdits({ name: v.name, description: v.description, collection: v.collection });
  };

  const replace = (v: Voice) =>
    setVoices((list) => list.map((x) => (x.id === v.id ? v : x)));

  const commitEdit = async (v: Voice) => {
    const name = edits.name.trim();
    if (!name) return;
    setEditBusy(true);
    setError("");
    try {
      replace(
        await updateVoice(v.id, {
          name,
          description: edits.description.trim(),
          collection: edits.collection.trim(),
        })
      );
      setEditingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the changes.");
    } finally {
      setEditBusy(false);
    }
  };

  const toggleFavorite = async (v: Voice) => {
    const next = { ...v, favorite: !v.favorite };
    replace(next); // optimistic: the star should not wait on a round trip
    try {
      replace(await updateVoice(v.id, { favorite: next.favorite }));
    } catch (e) {
      replace(v);
      setError(e instanceof Error ? e.message : "Could not update the favorite.");
    }
  };

  const runCleanup = async (v: Voice) => {
    const ok = window.confirm(
      `Clean the room tone out of "${v.name}"?\n\n` +
        "This adds a second, cleaned voice and leaves this one untouched. Be aware " +
        "that a cleaned reference usually reads a little faster than the original, " +
        "so compare them before you pick one."
    );
    if (!ok) return;
    setBusyId(v.id);
    setError("");
    try {
      const cleaned = await cleanupVoice(v.id, "derive");
      setVoices((list) => [cleaned, ...list]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not clean this voice.");
    } finally {
      setBusyId(null);
    }
  };

  const runWindow = async (v: Voice) => {
    const ok = window.confirm(
      `Tune "${v.name}" to its best ten seconds?\n\n` +
        "The engine listens hardest to about ten seconds of a reference. This " +
        "adds a second voice that leads with the strongest ten seconds of the " +
        "take and leaves this one untouched, so compare them by ear before " +
        "you pick one."
    );
    if (!ok) return;
    setBusyId(v.id);
    setError("");
    try {
      const tuned = await windowVoice(v.id);
      setVoices((list) => [tuned, ...list]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not tune this voice.");
    } finally {
      setBusyId(null);
    }
  };

  const undoCleanup = async (v: Voice) => {
    setBusyId(v.id);
    setError("");
    try {
      replace(await revertVoiceCleanup(v.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not restore the original.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <header className="screen-head">
        <div className="screen-eyebrow">Voice profiles</div>
        <h1 className="screen-title">Voices</h1>
        <p className="screen-sub">
          Each voice is cloned from a single recording. Record in the register
          you plan to generate in.
        </p>
      </header>

      <HelpPanel>
        <ul>
          <li>
            Create a voice below. Start with the master reference, the 90 second
            script at the top: it covers the full range of sounds and is the one
            to record first. The situation scripts under it are shorter and
            tuned to one register. Or upload a recording you already have.
          </li>
          <li>
            One continuous take of 60 to 90 seconds gives the clone the most to
            work with. The spoken consent line must be part of the recording.
          </li>
          <li>
            The check after recording measures your microphone, not just your
            speech: how far up it reaches, how bright it is, and how far your
            voice sits above the room. It says so in plain language. Worth
            reading, because a microphone that cuts off the top of your voice
            cannot be fixed afterwards, and the clone will invent what is
            missing.
          </li>
          <li>
            Under the scripts, “Write your own reference script” explains what
            makes one work and hands you a prompt to paste into any assistant,
            so you can build one in your own language and your own words.
          </li>
          <li>
            If you leave before saving, the take is kept as a draft and offered
            back next time. Delete it there if you do not want it.
          </li>
          <li>
            Each card plays its reference recording. Click anywhere on the wave
            to jump to that spot. The pencil edits the name, description and
            collection; the star marks a favourite, which sorts it to the top
            here and in the Generate list.
          </li>
          <li>
            A collection is just a name you type, like a folder. Give two voices
            the same one and they group together.
          </li>
          <li>
            The quality chip reads the reference recording: “clean” means your
            voice sits well above the room, “roomy” means the clone will inherit
            some background. Hover it for the numbers.
          </li>
          <li>
            The engine listens hardest to about ten seconds of a reference, so
            new voices automatically condition on the strongest ten seconds of
            the take (the “10s window” chip). The full recording is kept for
            playback and future fine-tuning. Older voices get the same
            treatment with the Best window button, which builds a second voice
            so you can compare by ear first.
          </li>
          <li>
            Clean up offers to denoise a roomy reference. It builds a second
            voice rather than changing this one, because a cleaned reference
            usually reads a little faster. Compare the two and keep what sounds
            like you.
          </li>
          <li>
            Export creates a portable .voice file. The same Import button takes
            one back, or any ordinary recording: mp3, m4a, wav, wma, amr and
            most others are converted for you, so whatever your phone or
            recorder produced will work.
          </li>
        </ul>
      </HelpPanel>

      {voices.length > 0 && (collections.length > 0 || voices.some((v) => v.favorite)) && (
        <div className="suggest-row" style={{ marginBottom: 16 }}>
          <button
            type="button"
            className={`chip suggest${filter === ALL ? " accent" : ""}`}
            onClick={() => setFilter(ALL)}
          >
            All {voices.length}
          </button>
          {voices.some((v) => v.favorite) && (
            <button
              type="button"
              className={`chip suggest${filter === FAVORITES ? " accent" : ""}`}
              onClick={() => setFilter(FAVORITES)}
            >
              ★ Favorites
            </button>
          )}
          {collections.map((c) => (
            <button
              key={c}
              type="button"
              className={`chip suggest${filter === c ? " accent" : ""}`}
              onClick={() => setFilter(c)}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      {voices.length > 0 && (
        <div className="voice-grid" style={{ marginBottom: 18 }}>
          {visible.map((v) => (
            <article className="voice-card" key={v.id}>
              {editingId === v.id ? (
                <div style={{ marginBottom: 8 }}>
                  <div className="field">
                    <label htmlFor={`n-${v.id}`}>Name</label>
                    <input
                      id={`n-${v.id}`}
                      className="input"
                      value={edits.name}
                      autoFocus
                      onChange={(e) => setEdits({ ...edits, name: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEdit(v);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                    />
                  </div>
                  <div className="field" style={{ marginTop: 8 }}>
                    <label htmlFor={`d-${v.id}`}>Description</label>
                    <input
                      id={`d-${v.id}`}
                      className="input"
                      placeholder="What this voice is for"
                      value={edits.description}
                      onChange={(e) => setEdits({ ...edits, description: e.target.value })}
                    />
                  </div>
                  <div className="field" style={{ marginTop: 8 }}>
                    <label htmlFor={`c-${v.id}`}>Collection</label>
                    <input
                      id={`c-${v.id}`}
                      className="input"
                      list="voice-collections"
                      placeholder="e.g. Video narration"
                      value={edits.collection}
                      onChange={(e) => setEdits({ ...edits, collection: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEdit(v);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                    />
                  </div>
                  <div className="row" style={{ marginTop: 10 }}>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={editBusy || edits.name.trim().length === 0}
                      onClick={() => commitEdit(v)}
                    >
                      Save
                    </button>
                    <button type="button" className="btn" onClick={() => setEditingId(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="voice-name-row">
                  <div className="voice-name">{v.name}</div>
                  <span style={{ display: "flex", gap: 2 }}>
                    <button
                      type="button"
                      className={`icon-btn${v.favorite ? " on" : ""}`}
                      aria-label={v.favorite ? "Remove from favorites" : "Add to favorites"}
                      aria-pressed={v.favorite}
                      title={v.favorite ? "Remove from favorites" : "Add to favorites"}
                      onClick={() => toggleFavorite(v)}
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
                        <path
                          d="M8 1.6l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.4l-3.8 2 .7-4.3-3.1-3 4.3-.6L8 1.6Z"
                          fill={v.favorite ? "currentColor" : "none"}
                          stroke="currentColor"
                          strokeWidth="1.3"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="Edit voice"
                      title="Edit name, description and collection"
                      onClick={() => startEdit(v)}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                        <path
                          d="M11.3 1.9a1.9 1.9 0 0 1 2.7 2.7l-8.5 8.5-3.6.9.9-3.6 8.5-8.5Z"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </span>
                </div>
              )}
              <div className="voice-desc">{v.description || "No description"}</div>
              <Waveform src={voiceSampleUrl(v.id)} />
              <div className="voice-foot">
                <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <span className="chip">{languageName(v.language)}</span>
                  {v.collection && <span className="chip">{v.collection}</span>}
                  {v.qc && (
                    <span
                      className={`chip${v.qc.snr_db >= CLEAN_SNR_DB ? " accent" : ""}`}
                      title={
                        `${(v.qc.sample_rate / 1000).toFixed(0)} kHz · ` +
                        `reach ${(v.qc.reach_hz / 1000).toFixed(1)} kHz · ` +
                        `voice above room ${v.qc.snr_db.toFixed(0)} dB`
                      }
                    >
                      {v.qc.snr_db >= CLEAN_SNR_DB ? "clean" : "roomy"}
                    </span>
                  )}
                  {v.cleanup?.applied && <span className="chip">cleaned</span>}
                  {v.window && (
                    <span
                      className="chip"
                      title={
                        `Conditions on the strongest ten seconds of the take ` +
                        `(${Math.floor(v.window.start_s)}s to ${Math.ceil(v.window.end_s)}s). ` +
                        `The full recording stays for playback and future fine-tuning.`
                      }
                    >
                      10s window
                    </span>
                  )}
                </span>
                <span style={{ display: "flex", gap: 8 }}>
                  {!v.window && (v.qc?.duration_s ?? 0) > 12 && (
                    <button
                      type="button"
                      className="btn"
                      disabled={busyId === v.id}
                      onClick={() => runWindow(v)}
                    >
                      {busyId === v.id ? "Tuning…" : "Best window"}
                    </button>
                  )}
                  {v.qc && v.qc.snr_db < CLEAN_SNR_DB && !v.cleanup?.applied && (
                    <button
                      type="button"
                      className="btn"
                      disabled={busyId === v.id}
                      onClick={() => runCleanup(v)}
                    >
                      {busyId === v.id ? "Cleaning…" : "Clean up"}
                    </button>
                  )}
                  {v.cleanup?.mode === "replace" && (
                    <button
                      type="button"
                      className="btn"
                      disabled={busyId === v.id}
                      onClick={() => undoCleanup(v)}
                    >
                      Revert
                    </button>
                  )}
                  <a className="btn" href={exportVoiceUrl(v.id)} download>
                    Export
                  </a>
                  <button type="button" className="btn danger" onClick={() => remove(v)}>
                    Delete
                  </button>
                </span>
              </div>
            </article>
          ))}
        </div>
      )}
      <datalist id="voice-collections">
        {collections.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      {error && <p className="error-note">{error}</p>}
      <div className="row" style={{ marginBottom: 18, alignItems: "center" }}>
        <button
          type="button"
          className="btn"
          disabled={importing}
          onClick={() => importRef.current?.click()}
        >
          {importing ? "Importing…" : "Import a voice or a recording"}
        </button>
        <input
          ref={importRef}
          type="file"
          accept={`.voice,.zip,${UPLOAD_ACCEPT}`}
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onImport(f);
            e.target.value = "";
          }}
        />
        <span className="hint" style={{ margin: 0 }}>
          A .voice file from another machine, or any recording: mp3, m4a, wav,
          ogg, wma, amr and most others are converted for you.
        </span>
      </div>

      <RecordFlow onCreated={(v) => setVoices((list) => [v, ...list])} />
    </>
  );
}
