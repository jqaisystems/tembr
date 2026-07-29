"use client";

// Guided voice-creation flow: pick a situation script → record (or upload) →
// QC check → name + consent → save. The register you record in is the
// register the clone speaks in, so the script choice matters.

import { useEffect, useRef, useState } from "react";
import Waveform from "@/components/Waveform";
import {
  API,
  cleanupTake,
  convertAudio,
  createVoice,
  getScriptGuide,
  getScripts,
  getVoices,
  transcribe,
  type CleanupResult,
  type RecordingScript,
  type ScriptGuide,
  type Transcription,
  type Voice,
} from "@/lib/api";
import { audioBufferToWav, decodeBlob, formatTimecode } from "@/lib/audio";
import { relativeTime } from "@/lib/dates";
import { clearDraft, loadDraft, saveDraft, type RecordingDraft } from "@/lib/drafts";
import { LANGUAGES } from "@/lib/languages";
import { suggestVoiceNames } from "@/lib/voiceNames";

type Step = "script" | "record" | "review" | "save";

// Deliberately wide: anything ffmpeg can decode becomes a usable reference, and
// the server converts whatever the browser cannot read. The named extensions
// are the ones Windows hides behind "audio/*".
export const UPLOAD_ACCEPT =
  "audio/*,video/mp4,.m4a,.m4b,.mp4,.amr,.wma,.aiff,.aif,.3gp,.opus,.webm,.caf,.aac";

export default function RecordFlow({ onCreated }: { onCreated: (v: Voice) => void }) {
  const [scripts, setScripts] = useState<RecordingScript[]>([]);
  const [language, setLanguage] = useState("en");
  const [script, setScript] = useState<RecordingScript | null>(null);
  const [step, setStep] = useState<Step>("script");

  const [recording, setRecording] = useState(false);
  const [recSeconds, setRecSeconds] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [wavBlob, setWavBlob] = useState<Blob | null>(null);
  const [qc, setQc] = useState<Transcription | null>(null);
  const [qcBusy, setQcBusy] = useState(false);

  const [name, setName] = useState("");
  const nameTouched = useRef(false);
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [converting, setConverting] = useState(false);
  const [guide, setGuide] = useState<ScriptGuide | null>(null);
  const [copied, setCopied] = useState(false);

  const [clean, setClean] = useState<CleanupResult | null>(null);
  const [cleanBlob, setCleanBlob] = useState<Blob | null>(null);
  const [cleanBusy, setCleanBusy] = useState(false);
  const [useClean, setUseClean] = useState(false);

  const [draft, setDraft] = useState<RecordingDraft | null>(null);
  const [takeLabel, setTakeLabel] = useState<string | null>(null);
  const [takeSituation, setTakeSituation] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getScripts(language)
      .then((s) => {
        setScripts(s);
        setScript(null);
      })
      .catch(() => setScripts([]));
    getScriptGuide(language).then(setGuide).catch(() => setGuide(null));
  }, [language]);

  useEffect(() => {
    loadDraft().then(setDraft);
  }, []);

  // A take in progress should survive an accidental tab close.
  useEffect(() => {
    if (!wavBlob || step === "script") return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [wavBlob, step]);

  useEffect(() => {
    if (step !== "save") return;
    getVoices()
      .then((vs) => {
        const names = suggestVoiceNames(vs, { language, situation: takeSituation });
        setSuggestions(names);
        // Fill the field so Create is not dead on arrival; the chips stay as
        // alternatives, and anything the user types wins from then on.
        if (!nameTouched.current && names[0]) setName(names[0]);
      })
      .catch(() => setSuggestions([]));
  }, [step, language, takeSituation]);

  const startRecording = async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false },
      });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => chunksRef.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const raw = new Blob(chunksRef.current, { type: rec.mimeType });
        await acceptAudio(raw);
      };
      rec.start();
      recorderRef.current = rec;
      setRecording(true);
      setRecSeconds(0);
      timerRef.current = setInterval(() => setRecSeconds((s) => s + 0.1), 100);
    } catch {
      setError("Microphone access was blocked. Allow it in the browser and try again.");
    }
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setRecording(false);
    if (timerRef.current) clearInterval(timerRef.current);
  };

  // Everything (webm from the recorder, any uploaded format the browser can
  // decode) is converted to 16-bit WAV client-side so the engine always
  // receives a format it reads natively.
  const runQc = (wav: Blob, draftBase: Omit<RecordingDraft, "qc">) => {
    setQc(null);
    setQcBusy(true);
    transcribe(wav, "sample.wav")
      .then((t) => {
        setQc(t);
        // Re-save the draft with QC attached so a restore can skip re-checking.
        saveDraft({ ...draftBase, qc: t });
      })
      .catch(() => {})
      .finally(() => setQcBusy(false));
  };

  const acceptAudio = async (raw: Blob, filename = "upload") => {
    setError("");
    try {
      let source = raw;
      try {
        await decodeBlob(raw);
      } catch {
        // The browser cannot decode everything a phone or recorder writes.
        // ffmpeg on the server can, so hand it over rather than refusing.
        setConverting(true);
        source = await convertAudio(raw, filename);
      } finally {
        setConverting(false);
      }
      const buffer = await decodeBlob(source);
      const wav = audioBufferToWav(buffer);
      setWavBlob(wav);
      setStep("review");
      setTakeLabel(script ? `${script.title} script (${script.situation})` : "Uploaded sample");
      setTakeSituation(script?.situation ?? null);
      // Keep the take safe immediately: drafts live in the browser only, so the
      // consent step stays mandatory before anything becomes a voice.
      const draftBase = {
        blob: wav,
        scriptTitle: script?.title ?? null,
        situation: script?.situation ?? null,
        language,
        savedAt: Date.now(),
      };
      saveDraft({ ...draftBase, qc: null });
      runQc(wav, draftBase);
    } catch (e) {
      setError(
        e instanceof Error && e.message
          ? e.message
          : "Could not read any audio in that file."
      );
    }
  };

  const restoreDraft = () => {
    if (!draft) return;
    setWavBlob(draft.blob);
    setLanguage(draft.language);
    setTakeLabel(
      draft.scriptTitle ? `${draft.scriptTitle} script (${draft.situation})` : "Uploaded sample"
    );
    setTakeSituation(draft.situation);
    setStep("review");
    if (draft.qc) {
      setQc(draft.qc);
    } else {
      runQc(draft.blob, { ...draft });
    }
  };

  const discardDraft = () => {
    clearDraft();
    setDraft(null);
  };

  const save = async () => {
    const blob = useClean && cleanBlob ? cleanBlob : wavBlob;
    if (!blob) return;
    setSaving(true);
    setError("");
    const form = new FormData();
    form.append("name", name.trim());
    form.append("description", takeLabel ?? "Uploaded sample");
    form.append("language", language);
    form.append("consent", "true");
    form.append("source", takeSituation ?? "upload");
    form.append("samples", blob, "sample.wav");
    try {
      const voice = await createVoice(form);
      onCreated(voice);
      clearDraft();
      setDraft(null);
      // reset for a possible next recording
      setStep("script");
      setScript(null);
      setWavBlob(null);
      setQc(null);
      setName("");
      nameTouched.current = false;
      setConsent(false);
      setTakeLabel(null);
      setTakeSituation(null);
      setClean(null);
      setCleanBlob(null);
      setUseClean(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the voice.");
    } finally {
      setSaving(false);
    }
  };

  // ---- optional cleanup, offered only when the room is loud in the take ----

  const noisy =
    qc?.snr_db != null && qc.thresholds != null && qc.snr_db < qc.thresholds.good_snr_db;

  const tryCleanup = async () => {
    if (!wavBlob) return;
    setCleanBusy(true);
    setError("");
    try {
      const result = await cleanupTake(wavBlob, "sample.wav");
      const audio = await fetch(`${API}${result.audio_url}`).then((r) => r.blob());
      setClean(result);
      setCleanBlob(audio);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not clean this take.");
    } finally {
      setCleanBusy(false);
    }
  };

  return (
    <section className="panel">
      <div className="panel-title">New voice</div>

      {step === "script" && (
        <>
          {draft && !wavBlob && (
            <div className="draft-banner">
              <p className="hint" style={{ margin: 0 }}>
                You have an unsaved take from {relativeTime(draft.savedAt)}. It is
                kept safe here until you use it or delete it.
              </p>
              <Waveform blob={draft.blob} />
              <div className="row">
                <button type="button" className="btn primary" onClick={restoreDraft}>
                  Use this take
                </button>
                <button type="button" className="btn danger" onClick={discardDraft}>
                  Delete take
                </button>
              </div>
            </div>
          )}
          <div className="row" style={{ marginBottom: 16 }}>
            <div className="field">
              <label htmlFor="rec-lang">Recording language</label>
              <select
                id="rec-lang"
                className="select"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                {LANGUAGES.filter(([id]) => ["en", "pt"].includes(id)).map(
                  ([id, n]) => (
                    <option key={id} value={id}>
                      {n}
                    </option>
                  )
                )}
              </select>
            </div>
          </div>
          <p className="hint" style={{ marginBottom: 12 }}>
            Pick the situation you'll mostly generate speech for. The clone keeps
            the energy you record with, so read in that register.
          </p>
          {scripts
            .filter((s) => s.situation === "reference")
            .map((s) => (
              <button
                key={s.situation}
                type="button"
                className="script-card recommended"
                onClick={() => {
                  setScript(s);
                  setStep("record");
                }}
              >
                <span className="recommend-badge">{s.label}</span>
                <span className="script-card-title">{s.title}</span>
                <span className="script-card-dir">{s.direction}</span>
              </button>
            ))}
          {scripts.some((s) => s.situation === "reference") && (
            <p className="panel-title" style={{ marginTop: 20, marginBottom: 10 }}>
              Or record for one situation
            </p>
          )}
          <div className="script-grid">
            {scripts
              .filter((s) => s.situation !== "reference")
              .map((s) => (
                <button
                  key={s.situation}
                  type="button"
                  className={`script-card${script?.situation === s.situation ? " selected" : ""}`}
                  onClick={() => {
                    setScript(s);
                    setStep("record");
                  }}
                >
                  <span className="script-card-title">{s.title}</span>
                  <span className="script-card-dir">{s.direction}</span>
                </button>
              ))}
          </div>
          <div className="row" style={{ marginTop: 16 }}>
            <button
              type="button"
              className="btn"
              disabled={converting}
              onClick={() => fileRef.current?.click()}
            >
              {converting ? "Converting…" : "Upload a recording instead"}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept={UPLOAD_ACCEPT}
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) acceptAudio(f, f.name);
                e.target.value = "";
              }}
            />
          </div>

          {guide && (
            <details style={{ marginTop: 18 }}>
              <summary className="panel-title" style={{ cursor: "pointer" }}>
                {guide.title}
              </summary>
              <ul className="hint" style={{ marginTop: 10, paddingLeft: 18 }}>
                {guide.checklist.map((item) => (
                  <li key={item} style={{ marginBottom: 6 }}>
                    {item}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  navigator.clipboard?.writeText(guide.prompt);
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 2000);
                }}
              >
                {copied ? "Copied" : "Copy the prompt"}
              </button>
              <p className="hint" style={{ marginTop: 8 }}>
                Paste it into any assistant to get a script written for your own
                language and the way you actually speak.
              </p>
            </details>
          )}
        </>
      )}

      {step === "record" && script && (
        <>
          <p className="hint" style={{ marginBottom: 10 }}>
            {/* The master reference states its own length; the short situation
                scripts do not, so only they get the duration hint. */}
            {script.direction}
            {script.situation === "reference" ? "" : " Aim for 15–30 seconds."}
          </p>
          <div className="script-lines">
            {script.lines.slice(0, -1).map((line) => (
              <p key={line}>{line}</p>
            ))}
            <p className="consent-line">{script.lines[script.lines.length - 1]}</p>
          </div>
          <div className="row" style={{ marginTop: 16, alignItems: "center" }}>
            {recording ? (
              <>
                <span className="rec-elapsed">
                  <span className="rec-dot pulsing" /> {formatTimecode(recSeconds)}
                </span>
                <button type="button" className="btn recording" onClick={stopRecording}>
                  Stop recording
                </button>
              </>
            ) : (
              <>
                <button type="button" className="btn primary" onClick={startRecording}>
                  Start recording
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    setStep("script");
                    setScript(null);
                  }}
                >
                  Choose another script
                </button>
              </>
            )}
          </div>
          {error && <p className="error-note">{error}</p>}
        </>
      )}

      {step === "review" && wavBlob && (
        <>
          <Waveform blob={wavBlob} />
          <div style={{ marginTop: 14 }}>
            {qcBusy && <p className="hint pulsing">Checking recording quality…</p>}
            {qc && qc.warnings.length > 0 && (
              <div className="warn-list">
                {qc.warnings.map((w) => (
                  <span className="warn" key={w}>
                    ▲ {w}
                  </span>
                ))}
              </div>
            )}
            {qc && qc.warnings.length === 0 && (
              <p className="ok-note">
                Good take: {qc.speech_s.toFixed(0)}s of clear speech detected
                {qc.language !== language
                  ? `, though it sounds like ${qc.language.toUpperCase()}`
                  : ""}
                .
              </p>
            )}
            {qc && (
              <p className="hint" style={{ marginTop: 8 }}>
                Heard: “{qc.text.slice(0, 180)}
                {qc.text.length > 180 ? "…" : ""}”
              </p>
            )}
          </div>

          {noisy && !clean && (
            <div style={{ marginTop: 16 }}>
              <p className="hint">
                Only {qc?.snr_db?.toFixed(0)} dB between your voice and the room. A gentle
                cleanup lifts that, but it also changes your delivery: a cleaned reference
                tends to read a little faster. Try it and keep whichever sounds more like
                you.
              </p>
              <button
                type="button"
                className="btn"
                style={{ marginTop: 10 }}
                onClick={tryCleanup}
                disabled={cleanBusy}
              >
                {cleanBusy ? "Cleaning…" : "Try a cleanup"}
              </button>
            </div>
          )}

          {clean && cleanBlob && (
            <div style={{ marginTop: 18 }}>
              <p className="panel-title">Cleaned version</p>
              <Waveform blob={cleanBlob} />
              <table className="spec-table" style={{ marginTop: 12 }}>
                <tbody>
                  <tr>
                    <td>Voice above room</td>
                    <td>
                      {clean.before?.snr_db.toFixed(1)} → {clean.after?.snr_db.toFixed(1)} dB
                      {clean.gain_db > 0 ? ` (+${clean.gain_db})` : ""}
                    </td>
                  </tr>
                  <tr>
                    <td>Reach</td>
                    <td>
                      {((clean.before?.reach_hz ?? 0) / 1000).toFixed(1)} →{" "}
                      {((clean.after?.reach_hz ?? 0) / 1000).toFixed(1)} kHz
                    </td>
                  </tr>
                  <tr>
                    <td>Presence</td>
                    <td>
                      {clean.before?.presence_db.toFixed(1)} →{" "}
                      {clean.after?.presence_db.toFixed(1)} dB
                    </td>
                  </tr>
                </tbody>
              </table>
              {!clean.worthwhile && (
                <p className="warn" style={{ marginTop: 10 }}>
                  ▲ The cleanup barely helped here
                  {clean.reach_kept ? "" : " and it cost you some detail up high"}. Keep the
                  original.
                </p>
              )}
              <div className="suggest-row" style={{ marginTop: 12 }}>
                <button
                  type="button"
                  className={`chip${useClean ? "" : " accent"}`}
                  onClick={() => setUseClean(false)}
                >
                  Use original
                </button>
                <button
                  type="button"
                  className={`chip${useClean ? " accent" : ""}`}
                  onClick={() => setUseClean(true)}
                >
                  Use cleaned
                </button>
              </div>
            </div>
          )}

          <div className="row" style={{ marginTop: 16 }}>
            <button type="button" className="btn primary" onClick={() => setStep("save")}>
              Use this take
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setWavBlob(null);
                setQc(null);
                setStep(script ? "record" : "script");
              }}
            >
              Re-record
            </button>
          </div>
          {error && <p className="error-note">{error}</p>}
        </>
      )}

      {step === "save" && (
        <>
          {suggestions.length > 0 && (
            <div className="suggest-row">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="chip suggest"
                  onClick={() => {
                    nameTouched.current = true;
                    setName(s);
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          <div className="row">
            <div className="field">
              <label htmlFor="voice-name">Voice name</label>
              <input
                id="voice-name"
                className="input"
                placeholder="e.g. Ana, sales energy"
                value={name}
                onChange={(e) => {
                  nameTouched.current = true;
                  setName(e.target.value);
                }}
              />
            </div>
          </div>
          <label
            style={{
              display: "flex",
              gap: 10,
              alignItems: "flex-start",
              margin: "14px 0",
              fontSize: 13.5,
              color: "var(--muted)",
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              style={{ marginTop: 3 }}
            />
            This is my own voice, or I have the speaker's explicit permission to
            clone it. The recording includes the spoken consent line.
          </label>
          <p style={{ fontSize: 13, color: "var(--faint)", margin: "0 0 14px" }}>
            Tembr conditions the clone on the strongest ten seconds of your
            take, found automatically. The rest is not wasted: it stays with
            the voice for playback, quality checks and future fine-tuning.
          </p>
          <div className="row">
            <button
              type="button"
              className="btn primary"
              disabled={saving || !consent || name.trim().length === 0}
              onClick={save}
            >
              {saving ? "Creating voice…" : "Create voice"}
            </button>
            <button type="button" className="btn" onClick={() => setStep("review")}>
              Back
            </button>
          </div>
          {error && <p className="error-note">{error}</p>}
        </>
      )}
    </section>
  );
}
