"use client";

import { useEffect, useRef, useState } from "react";
import HelpPanel from "@/components/HelpPanel";
import {
  getDraftingUsage,
  getHealth,
  getMaintenance,
  getProfile,
  putDraftingSettings,
  putProfile,
  uploadCv,
  type BusinessProfile,
  type DraftingSettings,
  type DraftingUsageRow,
  type Health,
  type MaintenanceStatus,
} from "@/lib/api";
import { LANGUAGES, languageName } from "@/lib/languages";

const PROVIDER_LABELS: Record<string, string> = {
  "codex-cli": "Codex (ChatGPT subscription)",
  "claude-cli": "Claude Code (Claude subscription)",
};

// Empty value = the CLI's own configured default.
const MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
  "codex-cli": [
    { value: "", label: "CLI default (your terminal setup)" },
    { value: "gpt-5.6-sol", label: "gpt-5.6-sol" },
    { value: "gpt-5.2-codex", label: "gpt-5.2-codex" },
    { value: "gpt-5.2", label: "gpt-5.2" },
  ],
  "claude-cli": [
    { value: "", label: "CLI default (your terminal setup)" },
    { value: "sonnet", label: "Sonnet (fast, recommended for drafting)" },
    { value: "opus", label: "Opus (strongest)" },
    { value: "haiku", label: "Haiku (cheapest)" },
  ],
};

const EFFORT_OPTIONS = [
  { value: "", label: "CLI default" },
  { value: "minimal", label: "Minimal" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium (recommended for drafting)" },
  { value: "high", label: "High" },
  { value: "xhigh", label: "Extra high" },
];

const PROFILE_FIELDS: { key: keyof BusinessProfile; label: string; long?: boolean }[] = [
  { key: "business_name", label: "Business name" },
  { key: "one_liner", label: "One-line description" },
  { key: "what_we_do", label: "What we do", long: true },
  { key: "tone_of_voice", label: "Tone of voice", long: true },
  { key: "target_customer", label: "Target customer" },
  { key: "website", label: "Website" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "other_links", label: "Other links" },
  { key: "email", label: "Email (reply button on player pages)" },
  { key: "cta_label", label: "Player page button label (optional)" },
  { key: "phone", label: "Phone (shown on player pages)" },
  { key: "website2", label: "Second website (optional)" },
];

export default function SettingsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);

  const [profile, setProfile] = useState<BusinessProfile | null>(null);
  const [profileSaved, setProfileSaved] = useState(false);
  const cvFileRef = useRef<HTMLInputElement>(null);
  const [drafting, setDrafting] = useState<DraftingSettings | null>(null);
  const [usage, setUsage] = useState<{
    week: Record<string, DraftingUsageRow>;
    month: Record<string, DraftingUsageRow>;
  } | null>(null);
  const [error, setError] = useState("");
  const [maintenance, setMaintenance] = useState<MaintenanceStatus | null>(null);

  useEffect(() => {
    getMaintenance().then(setMaintenance).catch(() => {});
    getHealth().then(setHealth).catch(() => setOffline(true));
    getProfile().then(setProfile).catch(() => {});
    getDraftingUsage()
      .then((d) => {
        setUsage(d.usage);
        setDrafting(d.settings);
      })
      .catch(() => {});
  }, []);

  const saveProfile = async () => {
    if (!profile) return;
    setError("");
    try {
      await putProfile(profile);
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the profile.");
    }
  };

  const saveDrafting = async (next: DraftingSettings) => {
    setDrafting(next);
    setError("");
    try {
      await putDraftingSettings(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save drafting settings.");
    }
  };

  const setBudget = (provider: string, period: "weekly" | "monthly", raw: string) => {
    if (!drafting) return;
    const value = raw.trim() === "" ? null : Math.max(0, parseInt(raw, 10) || 0);
    saveDrafting({
      ...drafting,
      budgets: {
        ...drafting.budgets,
        [provider]: { ...drafting.budgets[provider], [period]: value },
      },
    });
  };

  const setModel = (provider: string, key: "model" | "effort", value: string) => {
    if (!drafting) return;
    saveDrafting({
      ...drafting,
      models: {
        ...drafting.models,
        [provider]: { ...(drafting.models?.[provider] ?? {}), [key]: value },
      },
    });
  };

  return (
    <>
      <header className="screen-head">
        <div className="screen-eyebrow">System</div>
        <h1 className="screen-title">Settings</h1>
        <p className="screen-sub">
          Your business profile, AI drafting controls, and the engine details of
          this machine.
        </p>
      </header>

      <HelpPanel>
        <ul>
          <li>
            The business profile feeds two things: AI-drafted outreach messages,
            and the public voice card pages (email, phone, and websites appear
            there).
          </li>
          <li>
            AI drafting runs on your CLI subscriptions. Set the provider order,
            models, and weekly or monthly budgets here; usage is tracked below
            them.
          </li>
          <li>
            Monthly maintenance checks models, engines, and disk space. Run it
            from its panel when asked.
          </li>
          <li>Each panel saves with its own button.</li>
        </ul>
      </HelpPanel>

      {error && <p className="error-note">{error}</p>}

      {profile && (
        <section className="panel">
          <div className="panel-title">Business profile</div>
          <p className="hint" style={{ marginBottom: 14 }}>
            AI drafting uses this to write outreach messages in your tone, about
            your actual business. The fuller it is, the better the drafts.
          </p>
          {PROFILE_FIELDS.map((f) => (
            <div className="field" key={f.key}>
              <label htmlFor={`pf-${f.key}`}>{f.label}</label>
              {f.long ? (
                <textarea
                  id={`pf-${f.key}`}
                  className="textarea"
                  style={{ minHeight: 70 }}
                  value={profile[f.key]}
                  onChange={(e) => setProfile({ ...profile, [f.key]: e.target.value })}
                />
              ) : (
                <input
                  id={`pf-${f.key}`}
                  className="input"
                  value={profile[f.key]}
                  onChange={(e) => setProfile({ ...profile, [f.key]: e.target.value })}
                />
              )}
            </div>
          ))}
          <div className="row" style={{ marginTop: 6 }}>
            <div className="field">
              <label htmlFor="pf-primary-lang">Primary language (default everywhere)</label>
              <select
                id="pf-primary-lang"
                className="select"
                value={profile.primary_language || "en"}
                onChange={(e) => setProfile({ ...profile, primary_language: e.target.value })}
              >
                {LANGUAGES.map(([id, n]) => (
                  <option key={id} value={id}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="pf-secondary-lang">Secondary languages (listed right after it)</label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                {(profile.secondary_languages ?? []).map((id) => (
                  <button
                    key={id}
                    type="button"
                    className="chip"
                    style={{ cursor: "pointer" }}
                    title="Remove"
                    onClick={() =>
                      setProfile({
                        ...profile,
                        secondary_languages: profile.secondary_languages.filter((x) => x !== id),
                      })
                    }
                  >
                    {languageName(id)} ✕
                  </button>
                ))}
                <select
                  id="pf-secondary-lang"
                  className="select"
                  value=""
                  onChange={(e) => {
                    const id = e.target.value;
                    if (!id) return;
                    setProfile({
                      ...profile,
                      secondary_languages: [
                        ...(profile.secondary_languages ?? []).filter((x) => x !== id),
                        id,
                      ],
                    });
                  }}
                >
                  <option value="">Add a language…</option>
                  {LANGUAGES.filter(
                    ([id]) =>
                      id !== profile.primary_language &&
                      !(profile.secondary_languages ?? []).includes(id)
                  ).map(([id, n]) => (
                    <option key={id} value={id}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          <div className="field" style={{ marginTop: 6 }}>
            <label htmlFor="pf-cv-text">CV or company background (AI drafting uses it)</label>
            <textarea
              id="pf-cv-text"
              className="textarea"
              style={{ minHeight: 90 }}
              placeholder="Paste your CV or a short company background here…"
              value={profile.cv_text}
              onChange={(e) => setProfile({ ...profile, cv_text: e.target.value })}
            />
            <div className="row" style={{ marginTop: 8, alignItems: "center" }}>
              <button type="button" className="btn" onClick={() => cvFileRef.current?.click()}>
                Upload .txt or .md
              </button>
              <input
                ref={cvFileRef}
                type="file"
                accept=".txt,.md"
                hidden
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (!f) return;
                  try {
                    const updated = await uploadCv(f);
                    setProfile(updated);
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "Could not read the file.");
                  }
                }}
              />
              <input
                className="input"
                placeholder="Or a link to it (shown to AI, not to leads)"
                value={profile.cv_link}
                onChange={(e) => setProfile({ ...profile, cv_link: e.target.value })}
              />
            </div>
          </div>
          <button type="button" className="btn primary" onClick={saveProfile}>
            Save profile
          </button>
          {profileSaved && <span className="ok-note" style={{ marginLeft: 12 }}>Saved.</span>}
        </section>
      )}

      {drafting && (
        <section className="panel">
          <div className="panel-title">AI drafting</div>
          <p className="hint" style={{ marginBottom: 14 }}>
            Drafting runs on your existing subscriptions through their CLIs, in
            this order. Voice rendering never leaves this machine. Usage below
            counts what this app consumed, not your whole subscription.
          </p>
          {drafting.order.map((provider) => {
            const week = usage?.week[provider];
            const month = usage?.month[provider];
            return (
              <div
                key={provider}
                style={{
                  borderTop: "1px solid var(--line-soft)",
                  padding: "12px 0",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <label style={{ display: "flex", gap: 10, alignItems: "center", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={drafting.enabled[provider] ?? false}
                    onChange={(e) =>
                      saveDrafting({
                        ...drafting,
                        enabled: { ...drafting.enabled, [provider]: e.target.checked },
                      })
                    }
                  />
                  <b>{PROVIDER_LABELS[provider] ?? provider}</b>
                  {drafting.order[0] === provider && <span className="chip accent">primary</span>}
                </label>
                <div className="timecode">
                  This week: {week ? `${week.calls} calls · ${((week.input_tokens ?? 0) + (week.output_tokens ?? 0)).toLocaleString()} tokens · ${week.leads} leads` : "no usage"}
                  {" · "}This month: {month ? `${month.calls} calls · ${((month.input_tokens ?? 0) + (month.output_tokens ?? 0)).toLocaleString()} tokens` : "no usage"}
                  {(week?.any_estimated || month?.any_estimated) ? " (some counts estimated)" : ""}
                </div>
                <div className="row">
                  <div className="field">
                    <label>Model</label>
                    <select
                      className="select"
                      value={drafting.models?.[provider]?.model ?? ""}
                      onChange={(e) => setModel(provider, "model", e.target.value)}
                    >
                      {(MODEL_OPTIONS[provider] ?? []).map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  {provider === "codex-cli" && (
                    <div className="field">
                      <label>Reasoning effort</label>
                      <select
                        className="select"
                        value={drafting.models?.[provider]?.effort ?? ""}
                        onChange={(e) => setModel(provider, "effort", e.target.value)}
                      >
                        {EFFORT_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
                <div className="row">
                  <div className="field">
                    <label>Weekly token budget (empty = no cap)</label>
                    <input
                      className="input"
                      inputMode="numeric"
                      value={drafting.budgets[provider]?.weekly ?? ""}
                      onChange={(e) => setBudget(provider, "weekly", e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label>Monthly token budget</label>
                    <input
                      className="input"
                      inputMode="numeric"
                      value={drafting.budgets[provider]?.monthly ?? ""}
                      onChange={(e) => setBudget(provider, "monthly", e.target.value)}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </section>
      )}

      <section className="panel">
        <div className="panel-title">
          Monthly maintenance
          {maintenance?.due && <span className="chip accent" style={{ marginLeft: 10 }}>due</span>}
        </div>
        <p className="hint" style={{ marginBottom: 10 }}>
          {maintenance?.last_run
            ? `Last run: ${new Date(maintenance.last_run * 1000).toLocaleDateString()}.`
            : "Never run yet."}{" "}
          Recommended every {maintenance?.interval_days ?? 30} days.
        </p>
        <p style={{ fontSize: 14, lineHeight: 1.6 }}>
          Tell Claude: <b>&quot;run the studio monthly maintenance&quot;</b>. It will:
        </p>
        <ul style={{ fontSize: 14, lineHeight: 1.8, paddingLeft: 20, color: "var(--muted)" }}>
          <li>Refresh the drafting model lists above (new Codex and Claude models)</li>
          <li>Report available Codex and Claude CLI updates</li>
          <li>Check for new voice engine releases and new European Portuguese models</li>
          <li>Confirm all caches and models still live on E:, with sizes</li>
          <li>Verify everything still works: one English and one Portuguese generation, one draft</li>
        </ul>
        <p className="hint" style={{ marginTop: 8 }}>
          Safe changes are applied directly. Anything touching the voice engines
          is proposed to you first, never upgraded automatically.
        </p>
      </section>

      {offline && (
        <section className="panel">
          <p className="error-note">
            The engine is not responding. Start it with server\start.ps1 and
            reload this page.
          </p>
        </section>
      )}

      {health && (
        <>
          <section className="panel">
            <div className="panel-title">Engine</div>
            <table className="spec-table">
              <tbody>
                <tr>
                  <td>Engines</td>
                  <td>{health.engines.join(", ")}</td>
                </tr>
                <tr>
                  <td>PyTorch</td>
                  <td>{health.torch ?? "not loaded"}</td>
                </tr>
                <tr>
                  <td>CUDA</td>
                  <td>{health.cuda_available ? "available" : "unavailable, using CPU"}</td>
                </tr>
                {health.gpu && (
                  <>
                    <tr>
                      <td>GPU</td>
                      <td>{health.gpu.name}</td>
                    </tr>
                    <tr>
                      <td>VRAM in use</td>
                      <td>
                        {(health.gpu.vram_total_gb - health.gpu.vram_free_gb).toFixed(1)} GB
                        of {health.gpu.vram_total_gb.toFixed(1)} GB
                      </td>
                    </tr>
                  </>
                )}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <div className="panel-title">Storage</div>
            <table className="spec-table">
              <tbody>
                <tr>
                  <td>Project drive</td>
                  <td>{health.disk.drive} (everything stays here, nothing on C:)</td>
                </tr>
                <tr>
                  <td>Models on disk</td>
                  <td>{health.disk.models_gb.toFixed(1)} GB</td>
                </tr>
                <tr>
                  <td>Free space</td>
                  <td>{health.disk.free_gb.toFixed(0)} GB</td>
                </tr>
                <tr>
                  <td>Generated audio</td>
                  <td>data\output</td>
                </tr>
                <tr>
                  <td>Voice recordings</td>
                  <td>data\voices</td>
                </tr>
              </tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}
