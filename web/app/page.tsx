"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import HelpPanel from "@/components/HelpPanel";
import Waveform from "@/components/Waveform";
import {
  audioUrl,
  deleteGeneration,
  generate,
  getGenerationProjects,
  getGenerations,
  getProfile,
  getVoices,
  updateGeneration,
  type Generation,
  type Voice,
} from "@/lib/api";
import { languageName, orderLanguages } from "@/lib/languages";
import { formatTimecode } from "@/lib/audio";
import { groupByDate } from "@/lib/dates";
import { groupVoices, voiceLabel } from "@/lib/voiceNames";

/** Starred clips lead, then the rest keep their date sections.
 *  Done here rather than in the SQL because groupByDate preserves order, so a
 *  server-side `favorite DESC` would drop old starred clips into "Today". */
function sectionHistory(history: Generation[]): [string, Generation[]][] {
  const favorites = history.filter((g) => g.favorite);
  const rest = history.filter((g) => !g.favorite);
  return [
    ...(favorites.length ? ([["Favorites", favorites]] as [string, Generation[]][]) : []),
    ...groupByDate(rest),
  ];
}

export default function GeneratePage() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [history, setHistory] = useState<Generation[]>([]);
  const [text, setText] = useState("");
  const [voiceId, setVoiceId] = useState<string>("");
  const [language, setLanguage] = useState("en");
  const [engine, setEngine] = useState<string>(""); // "" = auto-route
  const [format, setFormat] = useState<"wav" | "mp3">("wav");
  const [project, setProject] = useState("");
  const [projects, setProjects] = useState<string[]>([]);
  const [projectFilter, setProjectFilter] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [langOptions, setLangOptions] = useState<[string, string][]>(orderLanguages());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getVoices().then(setVoices).catch(() => {});
    getGenerationProjects().then(setProjects).catch(() => {});
    getProfile()
      .then((p) => {
        if (p.primary_language) setLanguage(p.primary_language);
        setLangOptions(orderLanguages(p.primary_language, p.secondary_languages));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    getGenerations(50, projectFilter || undefined)
      .then(setHistory)
      .catch(() => {});
  }, [projectFilter]);

  const removeGeneration = async (g: Generation) => {
    const sure = window.confirm(
      "Are you sure you want to delete this clip permanently? The audio file is removed from disk too. This cannot be undone."
    );
    if (!sure) return;
    try {
      await deleteGeneration(g.id);
      setHistory((h) => h.filter((x) => x.id !== g.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete the clip.");
    }
  };

  const replaceGen = (g: Generation) =>
    setHistory((h) => h.map((x) => (x.id === g.id ? g : x)));

  const toggleGenFavorite = async (g: Generation) => {
    const next = { ...g, favorite: !g.favorite };
    replaceGen(next); // optimistic: the star should not wait on a round trip
    try {
      replaceGen(await updateGeneration(g.id, { favorite: next.favorite }));
    } catch (e) {
      replaceGen(g);
      setError(e instanceof Error ? e.message : "Could not update the favorite.");
    }
  };

  const commitGenName = async (g: Generation) => {
    const name = renameValue.trim();
    if (!name || name === g.name) {
      setRenamingId(null);
      return;
    }
    try {
      replaceGen(await updateGeneration(g.id, { name }));
      setRenamingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not rename the clip.");
    }
  };

  // Generation language follows the chosen voice's language by default.
  const pickVoice = (id: string) => {
    setVoiceId(id);
    const v = voices.find((x) => x.id === id);
    if (v) setLanguage(v.language);
  };

  const run = async () => {
    setBusy(true);
    setError("");
    setElapsed(0);
    timerRef.current = setInterval(() => setElapsed((e) => e + 0.1), 100);
    try {
      const gen = await generate({
        text,
        voice_id: voiceId || null,
        language,
        engine: engine || null,
        format,
        normalize: format === "mp3", // distribution format ships normalized
        project: project.trim(),
      });
      setHistory((h) => [gen, ...h]);
      setText("");
      if (project.trim() && !projects.includes(project.trim())) {
        setProjects((p) => [...p, project.trim()].sort());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed.");
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      setBusy(false);
    }
  };

  return (
    <>
      <header className="screen-head">
        <div className="screen-eyebrow">Text to speech</div>
        <h1 className="screen-title">Generate</h1>
        <p className="screen-sub">
          Type anything, pick a voice, and it comes back spoken, without leaving
          this machine.
        </p>
      </header>

      <HelpPanel>
        <ul>
          <li>Write your text, pick a voice and language, and press Generate.</li>
          <li>
            The voice list shows each voice with its language, engine and age,
            grouped by favourite and collection, so two voices with similar
            names are still easy to tell apart. Set those on the Voices screen.
          </li>
          <li>
            Engine set to Auto routes by language: Portuguese uses Qwen, English
            and everything else uses Chatterbox. Pick one manually to compare
            the same text on both.
          </li>
          <li>
            Every result lands in the history below, named from its own opening
            words. Generate the same line twice and the second is numbered, so
            takes never collide. The pencil renames one.
          </li>
          <li>
            Takes vary. Generate again if one does not sound right, then star
            the one you want to keep: starred takes gather at the top of the
            history. Deletes are permanent.
          </li>
          <li>
            Download uses the take's name, so files arrive readable rather than
            as a string of letters and numbers. Click anywhere on a wave to jump
            to that part of the take.
          </li>
          <li>A project tag groups related takes so you can filter them later.</li>
        </ul>
      </HelpPanel>

      <section className="panel">
        <div className="field">
          <label htmlFor="gen-text">Text</label>
          <textarea
            id="gen-text"
            className="textarea"
            placeholder="Write what you want to hear…"
            value={text}
            maxLength={2000}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="row">
          <div className="field">
            <label htmlFor="gen-voice">Voice</label>
            <select
              id="gen-voice"
              className="select"
              value={voiceId}
              onChange={(e) => pickVoice(e.target.value)}
            >
              <option value="">Default voice</option>
              {groupVoices(voices).map(([group, list]) => (
                <optgroup key={group} label={group}>
                  {list.map((v) => (
                    <option key={v.id} value={v.id}>
                      {voiceLabel(v)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="gen-lang">Language</label>
            <select
              id="gen-lang"
              className="select"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              {langOptions.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="gen-engine">Engine</label>
            <select
              id="gen-engine"
              className="select"
              value={engine}
              onChange={(e) => setEngine(e.target.value)}
            >
              <option value="">Auto (recommended)</option>
              <option value="chatterbox">Chatterbox</option>
              <option value="qwen3tts">Qwen3-TTS</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="gen-format">Format</label>
            <select
              id="gen-format"
              className="select"
              value={format}
              onChange={(e) => setFormat(e.target.value as "wav" | "mp3")}
            >
              <option value="wav">WAV (studio)</option>
              <option value="mp3">MP3 (share, normalized)</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="gen-project">Project (optional)</label>
            <input
              id="gen-project"
              className="input"
              list="project-names"
              placeholder="e.g. Client X launch"
              value={project}
              onChange={(e) => setProject(e.target.value)}
            />
            <datalist id="project-names">
              {projects.map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
          </div>
          <button
            type="button"
            className="btn primary"
            disabled={busy || text.trim().length === 0}
            onClick={run}
          >
            {busy ? `Generating… ${elapsed.toFixed(1)}s` : "Generate speech"}
          </button>
        </div>
        {error && <p className="error-note">{error}</p>}
        {voices.length === 0 && (
          <p className="empty">
            No cloned voices yet. <Link href="/voices">Record one in Voices</Link>,
            or use the default voice.
          </p>
        )}
      </section>

      <section className="panel">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 14,
          }}
        >
          <div className="panel-title" style={{ marginBottom: 0 }}>
            History
          </div>
          {projects.length > 0 && (
            <select
              className="select"
              style={{ width: "auto" }}
              value={projectFilter}
              onChange={(e) => setProjectFilter(e.target.value)}
              aria-label="Filter history by project"
            >
              <option value="">All projects</option>
              {projects.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          )}
        </div>
        {history.length === 0 ? (
          <p className="empty">
            Nothing generated yet. Your first generation will appear here.
          </p>
        ) : (
          sectionHistory(history).map(([groupLabel, items]) => (
            <div key={groupLabel}>
              <div className="panel-title" style={{ marginTop: 18 }}>
                {groupLabel}
              </div>
              {items.map((g) => (
                <article className="gen-item" key={g.id}>
                  {renamingId === g.id ? (
                    <div className="row">
                      <input
                        className="input"
                        value={renameValue}
                        autoFocus
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitGenName(g);
                          if (e.key === "Escape") setRenamingId(null);
                        }}
                      />
                      <button
                        type="button"
                        className="btn primary"
                        disabled={renameValue.trim().length === 0}
                        onClick={() => commitGenName(g)}
                      >
                        Save
                      </button>
                      <button type="button" className="btn" onClick={() => setRenamingId(null)}>
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div className="voice-name-row">
                      <div className="voice-name">{g.name || "Untitled"}</div>
                      <span style={{ display: "flex", gap: 2 }}>
                        <button
                          type="button"
                          className={`icon-btn${g.favorite ? " on" : ""}`}
                          aria-label={g.favorite ? "Remove from favorites" : "Add to favorites"}
                          aria-pressed={g.favorite}
                          title={g.favorite ? "Remove from favorites" : "Add to favorites"}
                          onClick={() => toggleGenFavorite(g)}
                        >
                          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
                            <path
                              d="M8 1.6l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.4l-3.8 2 .7-4.3-3.1-3 4.3-.6L8 1.6Z"
                              fill={g.favorite ? "currentColor" : "none"}
                              stroke="currentColor"
                              strokeWidth="1.3"
                              strokeLinejoin="round"
                            />
                          </svg>
                        </button>
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label="Rename clip"
                          title="Rename"
                          onClick={() => {
                            setRenamingId(g.id);
                            setRenameValue(g.name);
                          }}
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
                  <div className="gen-meta">
                    <span className="chip accent">
                      {voices.find((v) => v.id === g.voice_id)?.name ?? "Default"}
                    </span>
                    <span className="chip">{languageName(g.language)}</span>
                    <span className="chip">{g.engine === "qwen3tts" ? "Qwen" : "Chatterbox"}</span>
                    {g.project && <span className="chip">{g.project}</span>}
                    <span className="timecode">
                      {formatTimecode(g.duration_s)} · rendered in {g.elapsed_s.toFixed(1)}s
                    </span>
                    <a className="chip" href={audioUrl(g)} download style={{ marginLeft: "auto" }}>
                      Download
                    </a>
                    <button
                      type="button"
                      className="chip"
                      style={{ cursor: "pointer", color: "var(--red)" }}
                      onClick={() => removeGeneration(g)}
                    >
                      Delete
                    </button>
                  </div>
                  <p className="gen-text">{g.text}</p>
                  <Waveform src={audioUrl(g)} />
                </article>
              ))}
            </div>
          ))
        )}
      </section>
    </>
  );
}
