"use client";

// Phase 4: batch-personalized voice notes. Leads come from a CSV/JSON file or
// pasted text; messages come from a {variable} template or from AI drafting
// grounded in the saved business profile. Rendering is always local.

import { useCallback, useEffect, useRef, useState } from "react";
import HelpPanel from "@/components/HelpPanel";
import {
  buildOutreachSite,
  createOutreachJob,
  deleteOutreachJob,
  draftMessages,
  extractLeads,
  getOutreachJob,
  getOutreachJobs,
  getProfile,
  getVoices,
  outreachItemAudioUrl,
  outreachPageUrl,
  outreachSiteIndexUrl,
  outreachSiteZipUrl,
  outreachZipUrl,
  previewOutreach,
  rerenderOutreachItem,
  stopOutreachJob,
  suggestTemplates,
  type ExtractedLead,
  type OutreachJob,
  type OutreachPreview,
  type Voice,
} from "@/lib/api";
import { languageName, orderLanguages } from "@/lib/languages";
import { groupByDate } from "@/lib/dates";
import { groupVoices, voiceLabel } from "@/lib/voiceNames";

const DEFAULT_TEMPLATES: Record<string, string> = {
  en: "Hi {name}, I came across your work and I believe I can save you a good amount of hours every week. Would a quick fifteen minute chat this week make sense?",
  pt: "Olá {name}, estive a ver o vosso trabalho e acredito que vos posso poupar bastante tempo todas as semanas. Faz sentido falarmos quinze minutos esta semana?",
};

const defaultTemplate = (lang: string) => DEFAULT_TEMPLATES[lang] ?? DEFAULT_TEMPLATES.en;

const isDefaultTemplate = (t: string) => Object.values(DEFAULT_TEMPLATES).includes(t);

type Draft = { lead: Record<string, string>; text: string };

export default function OutreachPage() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [jobs, setJobs] = useState<OutreachJob[]>([]);
  const [active, setActive] = useState<OutreachJob | null>(null);

  const [name, setName] = useState("");
  const [template, setTemplate] = useState(defaultTemplate("en"));
  const [voiceId, setVoiceId] = useState("");
  const [language, setLanguage] = useState("en");
  const [leadsMode, setLeadsMode] = useState<"file" | "paste" | "raw">("file");
  const [leadsFile, setLeadsFile] = useState<File | null>(null);
  const [leadsText, setLeadsText] = useState("");
  const [filterColumn, setFilterColumn] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const [includeHandled, setIncludeHandled] = useState(false);
  const [rawText, setRawText] = useState("");
  const [extracted, setExtracted] = useState<ExtractedLead[] | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extractNote, setExtractNote] = useState("");
  const [templateOptions, setTemplateOptions] = useState<string[] | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [langOptions, setLangOptions] = useState<[string, string][]>(orderLanguages());

  const [preview, setPreview] = useState<OutreachPreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [draftProvider, setDraftProvider] = useState("");
  const [draftBusy, setDraftBusy] = useState(false);
  const [instructions, setInstructions] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [buildingSite, setBuildingSite] = useState(false);
  const [siteNote, setSiteNote] = useState("");
  const [siteWarning, setSiteWarning] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const templateRef = useRef<HTMLTextAreaElement>(null);
  const activePanelRef = useRef<HTMLElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    getVoices().then(setVoices).catch(() => {});
    getOutreachJobs().then(setJobs).catch(() => {});
    getProfile()
      .then((p) => {
        if (p.primary_language) {
          setLanguage(p.primary_language);
          // Follow the primary language while the template is still untouched.
          setTemplate((t) => (isDefaultTemplate(t) ? defaultTemplate(p.primary_language) : t));
        }
        setLangOptions(orderLanguages(p.primary_language, p.secondary_languages));
      })
      .catch(() => {});
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const buildLeadsForm = useCallback(() => {
    const form = new FormData();
    form.append("template", template);
    if (leadsMode === "file" && leadsFile) form.append("leads", leadsFile);
    if (leadsMode === "paste" && leadsText.trim()) form.append("leads_text", leadsText);
    if (leadsMode === "raw" && extracted) form.append("leads_text", JSON.stringify(extracted));
    if (filterColumn && filterValue) {
      form.append("filter_column", filterColumn);
      form.append("filter_value", filterValue);
    }
    if (includeHandled) form.append("include_handled", "true");
    return form;
  }, [template, leadsMode, leadsFile, leadsText, extracted, filterColumn, filterValue, includeHandled]);

  const hasLeads =
    (leadsMode === "file" && !!leadsFile) ||
    (leadsMode === "paste" && leadsText.trim().length > 0) ||
    (leadsMode === "raw" && !!extracted?.length);

  const cancelAiCall = () => {
    abortRef.current?.abort();
    abortRef.current = null;
  };

  const runExtract = async () => {
    if (rawText.trim().length < 10) return;
    setExtracting(true);
    setError("");
    setExtractNote("");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await extractLeads(rawText, false, controller.signal);
      setExtracted(result.leads);
      setExtractNote(
        `${result.leads.length} lead${result.leads.length === 1 ? "" : "s"} extracted via ${result.provider}.` +
          (result.budget_warning ? ` ${result.budget_warning}` : "")
      );
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        setExtractNote("Cancelled. The provider may still finish this call in the background.");
      } else {
        setError(e instanceof Error ? e.message : "Could not extract leads.");
      }
    } finally {
      setExtracting(false);
      abortRef.current = null;
    }
  };

  const runSuggest = async () => {
    if (!preview) return;
    setSuggesting(true);
    setError("");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await suggestTemplates(
        {
          columns: preview.columns,
          sample_rows: preview.rows.slice(0, 3),
          language,
          offer: instructions,
        },
        controller.signal
      );
      setTemplateOptions(result.templates);
      if (result.budget_warning) setError(result.budget_warning);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        setError("Cancelled. The provider may still finish this call in the background.");
      } else {
        setError(e instanceof Error ? e.message : "Could not suggest templates.");
      }
    } finally {
      setSuggesting(false);
      abortRef.current = null;
    }
  };

  const stopBatch = async () => {
    if (!active) return;
    if (!window.confirm("Stop this batch? Finished notes stay; the rest will not render.")) return;
    setStopping(true);
    try {
      await stopOutreachJob(active.id);
      watch(active.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not stop the batch.");
    } finally {
      setStopping(false);
    }
  };

  // Live preview whenever leads, template, or filters change.
  useEffect(() => {
    if (!hasLeads) {
      setPreview(null);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      previewOutreach(buildLeadsForm())
        .then((p) => {
          setPreview(p);
          setPreviewError("");
        })
        .catch((e) => {
          setPreview(null);
          setPreviewError(e instanceof Error ? e.message : "Could not read the leads.");
        });
    }, 500);
  }, [hasLeads, buildLeadsForm]);

  const insertVariable = (column: string) => {
    const el = templateRef.current;
    const token = `{${column}}`;
    if (!el) {
      setTemplate((t) => t + token);
      return;
    }
    const start = el.selectionStart ?? template.length;
    const end = el.selectionEnd ?? template.length;
    const next = template.slice(0, start) + token + template.slice(end);
    setTemplate(next);
    requestAnimationFrame(() => {
      el.focus();
      el.selectionStart = el.selectionEnd = start + token.length;
    });
  };

  const watch = (id: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    const tick = () =>
      getOutreachJob(id)
        .then((j) => {
          setActive(j);
          setJobs((list) => list.map((x) => (x.id === j.id ? { ...x, ...j, items: undefined } : x)));
          if (j.status === "done" || j.status === "failed") {
            if (pollRef.current) clearInterval(pollRef.current);
          }
        })
        .catch(() => {});
    tick();
    pollRef.current = setInterval(tick, 3000);
  };

  const runDraft = async (override = false) => {
    if (!preview || preview.rows.length === 0) return;
    setDraftBusy(true);
    setError("");
    try {
      const result = await draftMessages({
        leads: preview.rows,
        language,
        instructions,
        override_budget: override,
      });
      setDrafts(preview.rows.map((lead, i) => ({ lead, text: result.messages[i] })));
      setDraftProvider(result.provider);
      if (result.budget_warning) setError(result.budget_warning);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Drafting failed.");
    } finally {
      setDraftBusy(false);
    }
  };

  const buildSite = async (id: string) => {
    setBuildingSite(true);
    setError("");
    setSiteNote("");
    setSiteWarning("");
    try {
      const result = await buildOutreachSite(id);
      setSiteNote(`Built ${result.pages} page${result.pages === 1 ? "" : "s"}.`);
      if (result.warnings.length) setSiteWarning(result.warnings.join(" "));
      watch(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not build the pages.");
    } finally {
      setBuildingSite(false);
    }
  };

  const removeJob = async (j: OutreachJob) => {
    const sure = window.confirm(
      `Are you sure you want to delete the batch "${j.name}" permanently? Every audio file it created is removed from disk too. This cannot be undone.`
    );
    if (!sure) return;
    setError("");
    try {
      await deleteOutreachJob(j.id);
      setJobs((list) => list.filter((x) => x.id !== j.id));
      if (active?.id === j.id) setActive(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete the batch.");
    }
  };

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      const form = buildLeadsForm();
      form.append("name", name.trim() || "Outreach batch");
      form.append("voice_id", voiceId);
      form.append("language", language);
      form.append("format", "mp3");
      if (drafts) {
        form.append("drafted_json", JSON.stringify(drafts));
        form.set("template", `[AI drafted via ${draftProvider}]`);
      }
      const job = await createOutreachJob(form);
      setJobs((list) => [job, ...list]);
      setDrafts(null);
      watch(job.id);
      requestAnimationFrame(() =>
        activePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the batch.");
    } finally {
      setBusy(false);
    }
  };

  // Everything Start batch needs, phrased as what is still missing. The button
  // explains itself instead of silently staying disabled.
  const missing: string[] = [];
  if (!hasLeads || !preview) {
    missing.push("Add leads in step 1: upload a file, paste them, or extract from raw text.");
  } else if (preview.will_render === 0) {
    missing.push(
      preview.auto_skipped > 0
        ? "All leads are marked sent or skip. Turn on the include switch in step 1."
        : "No leads left to render. Check your filter in step 1."
    );
  }
  if (!drafts) {
    if (template.trim() === "") {
      missing.push("Write a message template in step 2, or draft with AI.");
    } else if (preview && preview.missing_variables.length > 0) {
      missing.push("Fix the template variables flagged in step 2.");
    }
  }
  if (!voiceId) missing.push("Pick a voice in step 3.");

  // Items render one at a time in order, so the first pending item is the one
  // on the GPU right now.
  const renderingItemId =
    active && ["queued", "running", "stopping"].includes(active.status)
      ? active.items?.find((i) => i.status === "pending")?.id
      : undefined;

  const leadsOk = !!preview && preview.will_render > 0;
  const messageOk =
    (!!drafts && drafts.length > 0) ||
    (leadsOk && template.trim() !== "" && preview!.missing_variables.length === 0);
  const canStart = !busy && missing.length === 0;

  return (
    <>
      <header className="screen-head">
        <div className="screen-eyebrow">Voice notes at scale</div>
        <h1 className="screen-title">Outreach</h1>
        <p className="screen-sub">
          Leads in, one personal voice note per lead out, rendered locally in
          your voice.
        </p>
      </header>

      <HelpPanel>
        <ul>
          <li>
            Step 1: upload a CSV or JSON file, paste a lead table, or paste raw
            notes and let AI extract a clean lead list from them.
          </li>
          <li>
            Rows with status sent or skip are left out automatically. Turn on
            the include switch when the batch is a deliberate follow-up to an
            earlier campaign.
          </li>
          <li>
            Step 2: write one message with variables like {"{name}"} from the
            column chips, or let AI draft a personal message per lead and edit
            any of them.
          </li>
          <li>
            The template writes itself into a finished message for every lead.
            The list under the editor shows each one; use Edit messages
            individually to tweak a single lead.
          </li>
          <li>
            Tell the AI what this batch offers in the offer box; it writes the
            pitch around it, including a light P.S. for a secondary service.
          </li>
          <li>
            A running batch can be stopped: finished notes stay, the rest do
            not render.
          </li>
          <li>
            Step 3: name the batch, pick a voice, and render. One audio file per
            lead, ready while you watch the progress.
          </li>
          <li>
            When a batch finishes, Build pages creates a branded voice card page
            per lead. Download site gives you the folder to host; the zip has
            the plain audio files.
          </li>
          <li>
            Extract the downloaded site zip before opening it; pages opened from
            inside the zip lose their audio and links.
          </li>
          <li>
            Every note is quality checked automatically after rendering: long
            pauses, repeated words, and mangled endings get flagged on the lead.
          </li>
          <li>
            A flagged note gets fixed with its Re-render button; only that lead
            renders again, and its page updates by itself.
          </li>
          <li>
            Start batch activates when the three steps are complete. Anything
            still missing is listed next to the button.
          </li>
          <li>
            Batches stay in the list below. Deleting one removes its audio and
            pages permanently.
          </li>
        </ul>
      </HelpPanel>

      <section className="panel">
        <div className="panel-title">1 · Leads{leadsOk ? " ✓" : ""}</div>
        <div className="row" style={{ marginBottom: 12 }}>
          <button
            type="button"
            className={`btn${leadsMode === "file" ? " primary" : ""}`}
            onClick={() => setLeadsMode("file")}
          >
            Upload file
          </button>
          <button
            type="button"
            className={`btn${leadsMode === "paste" ? " primary" : ""}`}
            onClick={() => setLeadsMode("paste")}
          >
            Paste leads
          </button>
          <button
            type="button"
            className={`btn${leadsMode === "raw" ? " primary" : ""}`}
            onClick={() => setLeadsMode("raw")}
          >
            Paste raw info
          </button>
        </div>
        {leadsMode === "file" && (
          <div className="field">
            <label htmlFor="job-leads">CSV or JSON file (OutreachIQ exports work as-is)</label>
            <input
              id="job-leads"
              type="file"
              accept=".csv,.json"
              onChange={(e) => setLeadsFile(e.target.files?.[0] ?? null)}
            />
          </div>
        )}
        {leadsMode === "paste" && (
          <div className="field">
            <label htmlFor="job-paste">Paste CSV text (first line = column names) or JSON</label>
            <textarea
              id="job-paste"
              className="textarea"
              placeholder={"name,company,context\nMarta,Padaria Central,o novo site"}
              value={leadsText}
              onChange={(e) => setLeadsText(e.target.value)}
            />
          </div>
        )}
        {leadsMode === "raw" && (
          <>
            <div className="field">
              <label htmlFor="job-raw">
                Drop everything you know about the leads: emails, notes, page copy, anything
              </label>
              <textarea
                id="job-raw"
                className="textarea"
                style={{ minHeight: 120 }}
                placeholder={
                  "Mike runs Riverside Auto Repair in Ohio, mike@riversideauto.com, still books by phone.\nSarah from Bloom Dental (bloomdental.com) has weak online presence..."
                }
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
              />
            </div>
            <div className="row" style={{ alignItems: "center" }}>
              <button
                type="button"
                className={`btn primary${extracting ? " pulsing" : ""}`}
                disabled={extracting || rawText.trim().length < 10}
                onClick={runExtract}
              >
                {extracting ? "Extracting…" : extracted ? "Extract again" : "Extract leads with AI"}
              </button>
              {extracting && (
                <button type="button" className="btn danger" onClick={cancelAiCall}>
                  Cancel
                </button>
              )}
              {extractNote && <span className="ok-note" style={{ margin: 0 }}>{extractNote}</span>}
            </div>
          </>
        )}

        {previewError && <p className="error-note">{previewError}</p>}
        {preview && (
          <>
            {preview.note && <p className="ok-note">{preview.note}</p>}
            <p className="hint">
              {preview.will_render} of {preview.total_rows} leads will render
              {preview.auto_skipped > 0 && `, ${preview.auto_skipped} auto-skipped (status sent/skip)`}
              {preview.filtered_out > 0 && `, ${preview.filtered_out} removed by your filter`}.
            </p>
            {preview.will_render === 0 && preview.auto_skipped > 0 && !includeHandled && (
              <p className="error-note">
                All {preview.auto_skipped} leads are marked sent or skip from an earlier
                campaign. Turn on the switch below if this batch is a deliberate follow-up.
              </p>
            )}
            <label
              style={{
                display: "flex",
                gap: 10,
                alignItems: "center",
                margin: "10px 0",
                fontSize: 13.5,
                color: "var(--muted)",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={includeHandled}
                onChange={(e) => setIncludeHandled(e.target.checked)}
              />
              Include leads already marked sent or skip
            </label>
            <div className="row" style={{ marginTop: 10 }}>
              <div className="field">
                <label htmlFor="filter-col">Filter column (optional)</label>
                <select
                  id="filter-col"
                  className="select"
                  value={filterColumn}
                  onChange={(e) => setFilterColumn(e.target.value)}
                >
                  <option value="">No filter</option>
                  {preview.columns.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="filter-val">Keep only rows where it equals</label>
                <input
                  id="filter-val"
                  className="input"
                  placeholder="e.g. warm"
                  value={filterValue}
                  onChange={(e) => setFilterValue(e.target.value)}
                />
              </div>
            </div>
          </>
        )}
      </section>

      <section className="panel">
        <div className="panel-title">2 · Message{messageOk ? " ✓" : ""}</div>
        {preview && (
          <div className="field">
            <label>Your lead columns (click to insert into the template)</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {preview.columns.map((c) => (
                <button type="button" key={c} className="chip" style={{ cursor: "pointer" }} onClick={() => insertVariable(c)}>
                  {`{${c}}`}
                </button>
              ))}
            </div>
          </div>
        )}
        {templateOptions && (
          <div className="field">
            <label>Template suggestions (click one to use it, then edit freely)</label>
            <div className="script-grid">
              {templateOptions.map((t, i) => (
                <button
                  key={i}
                  type="button"
                  className={`script-card${template === t ? " selected" : ""}`}
                  onClick={() => setTemplate(t)}
                >
                  <span className="script-card-dir">{t}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="field">
          <label htmlFor="job-template">Template ({"{variables}"} are filled per lead)</label>
          <textarea
            id="job-template"
            ref={templateRef}
            className="textarea"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
          />
        </div>
        {preview && preview.missing_variables.length > 0 && (
          <p className="error-note">
            The template uses {preview.missing_variables.map((v) => `{${v}}`).join(", ")} but your
            leads have no such column. Click a column chip above instead.
          </p>
        )}
        {!drafts && preview?.rendered && preview.rendered.length > 0 ? (
          <div className="field" style={{ marginTop: 14 }}>
            <label>
              Messages that will render ({preview.rendered.length}), written from your
              leads automatically
            </label>
            {preview.rendered.slice(0, 8).map((r, i) => (
              <article className="gen-item" key={i}>
                <div className="gen-meta">
                  <span className="chip accent">
                    {r.lead.name || r.lead.email || `Lead ${i + 1}`}
                  </span>
                  {r.error && <span className="warn">▲ {r.error}</span>}
                </div>
                {r.text && <p className="gen-text">{r.text}</p>}
              </article>
            ))}
            {preview.rendered.length > 8 && (
              <p className="hint">
                And {preview.rendered.length - 8} more render the same way.
              </p>
            )}
            <button
              type="button"
              className="btn"
              style={{ marginTop: 8 }}
              onClick={() => {
                const items = preview.rendered!
                  .filter((r) => r.text)
                  .map((r) => ({ lead: r.lead, text: r.text! }));
                setDrafts(items);
                setDraftProvider("template");
              }}
            >
              Edit messages individually
            </button>
          </div>
        ) : (
          !drafts &&
          preview?.example && <p className="hint">First lead preview: “{preview.example}”</p>
        )}

        <div className="field" style={{ marginTop: 14 }}>
          <label htmlFor="draft-notes">
            What you are offering in this batch (drives templates and AI drafts)
          </label>
          <textarea
            id="draft-notes"
            className="textarea"
            style={{ minHeight: 60 }}
            placeholder="e.g. Brand identity design as the main offer. As a P.S., mention I also help businesses get real value from AI."
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </div>
        <div className="row">
          <button
            type="button"
            className="btn"
            disabled={draftBusy || !preview || preview.will_render === 0}
            onClick={() => runDraft(false)}
          >
            {draftBusy ? "Drafting…" : drafts ? "Draft again" : "Draft with AI"}
          </button>
          <button
            type="button"
            className={`btn${suggesting ? " pulsing" : ""}`}
            disabled={suggesting || !preview || preview.columns.length === 0}
            onClick={runSuggest}
          >
            {suggesting ? "Suggesting…" : "Suggest templates"}
          </button>
          {(suggesting || extracting) && (
            <button type="button" className="btn danger" onClick={cancelAiCall}>
              Cancel
            </button>
          )}
          {drafts && (
            <span className="hint">
              Drafted via {draftProvider}. Edit any message below, then start the batch.
            </span>
          )}
        </div>

        {drafts && (
          <div style={{ marginTop: 14 }}>
            {drafts.map((d, i) => (
              <div className="field" key={i}>
                <label>{d.lead.name || d.lead.email || `Lead ${i + 1}`}</label>
                <textarea
                  className="textarea"
                  style={{ minHeight: 70 }}
                  value={d.text}
                  onChange={(e) =>
                    setDrafts(drafts.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))
                  }
                />
              </div>
            ))}
            <button type="button" className="btn" onClick={() => setDrafts(null)}>
              Discard drafts, use the template instead
            </button>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-title">3 · Render{voiceId ? " ✓" : ""}</div>
        <div className="row">
          <div className="field">
            <label htmlFor="job-name">Batch name</label>
            <input
              id="job-name"
              className="input"
              placeholder="e.g. July prospects"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="job-voice">Voice</label>
            <select id="job-voice" className="select" value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
              <option value="">Choose a voice…</option>
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
            <label htmlFor="job-lang">Language</label>
            <select
              id="job-lang"
              className="select"
              value={language}
              onChange={(e) => {
                const id = e.target.value;
                setLanguage(id);
                setTemplate((t) => (isDefaultTemplate(t) ? defaultTemplate(id) : t));
              }}
            >
              {langOptions.map(([id, n]) => (
                <option key={id} value={id}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <button type="button" className="btn primary" disabled={!canStart} onClick={start}>
            {busy ? "Starting…" : "Start batch"}
          </button>
        </div>
        {missing.length > 0 ? (
          <div className="warn-list" style={{ marginTop: 10 }}>
            {missing.map((m) => (
              <span className="warn" key={m}>
                ▲ {m}
              </span>
            ))}
          </div>
        ) : (
          !busy && (
            <p className="ok-note">
              Ready: {drafts ? drafts.length : preview?.will_render ?? 0} lead
              {(drafts ? drafts.length : preview?.will_render) === 1 ? "" : "s"} will render
              in {voices.find((v) => v.id === voiceId)?.name ?? "the chosen voice"}.
            </p>
          )
        )}
        <p className="hint">
          Files render as normalized MP3, named after each lead. A 10-lead
          Portuguese batch takes roughly 7 to 8 minutes on this machine.
        </p>
        {error && <p className="error-note">{error}</p>}
      </section>

      {active && (
        <section className="panel" ref={activePanelRef}>
          <div className="panel-title">
            {active.name} · {active.status.toUpperCase()} · {active.done + active.failed}/{active.total}
          </div>
          {["queued", "running", "stopping"].includes(active.status) && (
            <>
              <div className="progress-row">
                <div className="progress-rail">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${active.total ? ((active.done + active.failed) / active.total) * 100 : 0}%`,
                    }}
                  />
                </div>
                <span className="timecode">
                  {active.done + active.failed}/{active.total}
                </span>
              </div>
              <p className="hint" style={{ marginTop: 0 }}>
                The first note takes the longest while the voice engine warms up.
              </p>
              <p style={{ marginBottom: 14 }}>
                <button
                  type="button"
                  className="btn danger"
                  disabled={stopping || active.status === "stopping"}
                  onClick={stopBatch}
                >
                  {active.status === "stopping" ? "Stopping…" : "Stop batch"}
                </button>
              </p>
            </>
          )}
          {(active.items ?? []).map((item) => (
            <article className="gen-item" key={item.id}>
              <div className="gen-meta">
                <span className="chip accent">{item.lead.name || item.lead.email || item.id}</span>
                {item.id === renderingItemId ? (
                  <span className="chip accent pulsing">rendering</span>
                ) : (
                  <span className="chip">{item.status}</span>
                )}
                {item.status === "done" && (
                  <>
                    <audio
                      controls
                      preload="none"
                      src={outreachItemAudioUrl(item.id)}
                      style={{ height: 30, marginLeft: "auto" }}
                    />
                    <a className="chip" href={outreachItemAudioUrl(item.id)} download>
                      Download
                    </a>
                    {active.site_built_at && item.slug && (
                      <a
                        className="chip"
                        href={outreachPageUrl(active.id, item.slug)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Page
                      </a>
                    )}
                    {["done", "failed", "stopped"].includes(active.status) && (
                      <button
                        type="button"
                        className="chip"
                        style={{ cursor: "pointer" }}
                        onClick={async () => {
                          if (
                            !window.confirm(
                              "Re-render this note? The current take is replaced with a fresh one, and its page updates too."
                            )
                          )
                            return;
                          try {
                            await rerenderOutreachItem(item.id);
                            watch(active.id);
                          } catch (e) {
                            setError(e instanceof Error ? e.message : "Could not re-render.");
                          }
                        }}
                      >
                        Re-render
                      </button>
                    )}
                  </>
                )}
                {item.status === "failed" && (
                  <span className="error-note" style={{ margin: 0 }}>
                    {item.error}
                  </span>
                )}
              </div>
              {item.status === "done" && (item.qc?.warnings?.length ?? 0) > 0 && (
                <div className="warn-list" style={{ marginTop: 6 }}>
                  {item.qc!.warnings.map((w) => (
                    <span className="warn" key={w}>
                      ▲ {w} Listen and re-render if it sounds wrong.
                    </span>
                  ))}
                </div>
              )}
              <p className="gen-text">{item.text}</p>
            </article>
          ))}
          {active.status === "done" &&
            (() => {
              const doneItems = (active.items ?? []).filter((i) => i.status === "done");
              const flagged = doneItems.filter((i) => (i.qc?.warnings?.length ?? 0) > 0).length;
              const allChecked = doneItems.length > 0 && doneItems.every((i) => i.qc);
              if (flagged > 0)
                return (
                  <p className="error-note">
                    Quality check flagged {flagged} note{flagged === 1 ? "" : "s"} above.
                    Listen to {flagged === 1 ? "it" : "them"} and use Re-render before
                    sending.
                  </p>
                );
              if (allChecked)
                return (
                  <p className="ok-note">
                    Quality check passed on every note: no long pauses, no mangled
                    endings.
                  </p>
                );
              return null;
            })()}
          {active.status === "done" && (
            <>
              <div
                style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}
              >
                <a className="btn primary" href={outreachZipUrl(active.id)} download>
                  Download all ({active.done} files)
                </a>
                <button
                  type="button"
                  className={`btn${buildingSite ? " pulsing" : ""}`}
                  onClick={() => buildSite(active.id)}
                  disabled={buildingSite}
                >
                  {buildingSite
                    ? "Building pages..."
                    : active.site_built_at
                      ? "Rebuild pages"
                      : "Build pages"}
                </button>
                {active.site_built_at && (
                  <>
                    <a
                      className="chip"
                      href={outreachSiteIndexUrl(active.id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      All pages
                    </a>
                    <a className="chip" href={outreachSiteZipUrl(active.id)} download>
                      Download site
                    </a>
                  </>
                )}
              </div>
              {siteNote && <p className="ok-note">{siteNote}</p>}
              {siteWarning && <p className="error-note">{siteWarning}</p>}
            </>
          )}
        </section>
      )}

      <section className="panel">
        <div className="panel-title">Past batches</div>
        {jobs.length === 0 ? (
          <p className="empty">No batches yet. Your first one will appear here.</p>
        ) : (
          groupByDate(jobs).map(([groupLabel, groupJobs]) => (
            <div key={groupLabel}>
              <div className="panel-title" style={{ marginTop: 18 }}>
                {groupLabel}
              </div>
              {groupJobs.map((j) => (
                <article className="gen-item" key={j.id}>
                  <div className="gen-meta">
                    <span className="chip accent">{j.name}</span>
                    <span className="chip">{languageName(j.language)}</span>
                    <span className="chip">{j.status}</span>
                    <span className="timecode">
                      {j.done}/{j.total} done{j.failed ? ` · ${j.failed} failed` : ""}
                    </span>
                    {j.site_built_at ? (
                      <a
                        className="chip"
                        style={{ marginLeft: "auto" }}
                        href={outreachSiteIndexUrl(j.id)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Pages
                      </a>
                    ) : null}
                    <button
                      type="button"
                      className="chip"
                      style={j.site_built_at ? { cursor: "pointer" } : { marginLeft: "auto", cursor: "pointer" }}
                      onClick={() => watch(j.id)}
                    >
                      Open
                    </button>
                    <button
                      type="button"
                      className="chip"
                      style={{ cursor: "pointer", color: "var(--red)" }}
                      onClick={() => removeJob(j)}
                    >
                      Delete
                    </button>
                  </div>
                </article>
              ))}
            </div>
          ))
        )}
      </section>
    </>
  );
}
