export const API = "http://127.0.0.1:8100";

export type VoiceQc = {
  sample_rate: number;
  reach_hz: number;
  presence_db: number;
  snr_db: number;
  duration_s?: number;
};

export type CleanupReport = {
  chain: string;
  before: VoiceQc | null;
  after: VoiceQc | null;
  gain_db: number;
  reach_kept: boolean;
  worthwhile: boolean;
};

export type VoiceCleanup = CleanupReport & {
  applied: boolean;
  mode: "derive" | "replace";
  from?: string;
  original?: string[];
};

export type VoiceWindow = {
  path?: string;
  start_s: number;
  end_s: number;
  score: number;
  default_score?: number;
  from?: string;
};

export type Voice = {
  id: string;
  name: string;
  description: string;
  language: string;
  engine: string;
  samples: string[];
  consent: boolean;
  created_at: number;
  favorite: boolean;
  collection: string;
  source: string;
  qc: VoiceQc | null;
  cleanup: VoiceCleanup | null;
  window: VoiceWindow | null;
  updated_at: number;
};

export type Generation = {
  id: string;
  voice_id: string | null;
  engine: string;
  language: string;
  text: string;
  output_path: string;
  duration_s: number;
  elapsed_s: number;
  created_at: number;
  project?: string;
  name: string;
  favorite: boolean;
  audio_url?: string;
};

export type RecordingScript = {
  situation: string;
  label: string;
  language: string;
  title: string;
  direction: string;
  lines: string[];
};

export type Health = {
  status: string;
  engines: string[];
  torch: string | null;
  cuda_available?: boolean;
  gpu?: { name: string; vram_total_gb: number; vram_free_gb: number };
  disk: { drive: string; free_gb: number; models_gb: number };
};

export type QcThresholds = {
  good_reach_hz: number;
  poor_reach_hz: number;
  good_presence_db: number;
  poor_presence_db: number;
  good_snr_db: number;
  good_sample_rate: number;
};

export type Transcription = {
  text: string;
  language: string;
  language_probability: number;
  duration_s: number;
  speech_s: number;
  sample_rate: number | null;
  reach_hz: number | null;
  presence_db: number | null;
  snr_db: number | null;
  thresholds: QcThresholds;
  warnings: string[];
};

export type ScriptGuide = {
  language: string;
  title: string;
  checklist: string[];
  prompt: string;
};

export type CleanupResult = CleanupReport & { id: string; audio_url: string };

async function ok<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const getHealth = () => fetch(`${API}/health`).then((r) => ok<Health>(r));
export const getVoices = () => fetch(`${API}/voices`).then((r) => ok<Voice[]>(r));
export const getScripts = (language?: string) =>
  fetch(`${API}/scripts${language ? `?language=${language}` : ""}`).then((r) =>
    ok<RecordingScript[]>(r)
  );
export const getGenerations = (limit = 50, project?: string) =>
  fetch(
    `${API}/generations?limit=${limit}${project ? `&project=${encodeURIComponent(project)}` : ""}`
  ).then((r) => ok<Generation[]>(r));

export const getGenerationProjects = () =>
  fetch(`${API}/generations/projects`).then((r) => ok<string[]>(r));

export const updateGeneration = (
  id: string,
  fields: Partial<Pick<Generation, "name" | "favorite">>
) =>
  fetch(`${API}/generations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  }).then((r) => ok<Generation>(r));

export const deleteGeneration = (id: string) =>
  fetch(`${API}/generations/${id}`, { method: "DELETE" }).then((r) =>
    ok<{ deleted: string }>(r)
  );

export const deleteVoice = (id: string) =>
  fetch(`${API}/voices/${id}`, { method: "DELETE" }).then((r) => ok<{ deleted: string }>(r));

export function createVoice(form: FormData) {
  return fetch(`${API}/voices`, { method: "POST", body: form }).then((r) => ok<Voice>(r));
}

export function generate(body: {
  text: string;
  voice_id: string | null;
  language: string;
  engine?: string | null; // null/undefined → backend routes by language (pt → qwen3tts)
  format?: "wav" | "mp3";
  normalize?: boolean;
  project?: string;
}) {
  return fetch(`${API}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => ok<Generation>(r));
}

export const exportVoiceUrl = (id: string) => `${API}/voices/${id}/export`;

export const voiceSampleUrl = (id: string) => `${API}/voices/${id}/audio`;

export const updateVoice = (
  id: string,
  fields: Partial<Pick<Voice, "name" | "description" | "collection" | "favorite">>
) =>
  fetch(`${API}/voices/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  }).then((r) => ok<Voice>(r));

export const getVoiceCollections = () =>
  fetch(`${API}/voices/collections`).then((r) => ok<string[]>(r));

export const getScriptGuide = (language?: string) =>
  fetch(`${API}/scripts/guide${language ? `?language=${language}` : ""}`).then((r) =>
    ok<ScriptGuide>(r)
  );

/** Denoise a take that is not a voice yet, so it can be compared before saving. */
export function cleanupTake(blob: Blob, filename: string) {
  const form = new FormData();
  form.append("file", blob, filename);
  return fetch(`${API}/cleanup`, { method: "POST", body: form }).then((r) =>
    ok<CleanupResult>(r)
  );
}

export const cleanupAudioUrl = (id: string) => `${API}/cleanup/${id}/audio`;

/** Fallback for files the browser cannot decode: let ffmpeg turn it into wav. */
export async function convertAudio(blob: Blob, filename: string): Promise<Blob> {
  const form = new FormData();
  form.append("file", blob, filename);
  const res = await fetch(`${API}/convert`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = "Could not read any audio in that file.";
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return res.blob();
}

export const cleanupVoice = (id: string, mode: "derive" | "replace" = "derive") =>
  fetch(`${API}/voices/${id}/cleanup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  }).then((r) => ok<Voice>(r));

export const revertVoiceCleanup = (id: string) =>
  fetch(`${API}/voices/${id}/cleanup/revert`, { method: "POST" }).then((r) => ok<Voice>(r));

export const windowVoice = (id: string) =>
  fetch(`${API}/voices/${id}/window`, { method: "POST" }).then((r) => ok<Voice>(r));

export function importVoice(file: File) {
  const form = new FormData();
  form.append("file", file);
  form.append("consent", "true");
  return fetch(`${API}/voices/import`, { method: "POST", body: form }).then((r) =>
    ok<Voice>(r)
  );
}

export function transcribe(blob: Blob, filename: string) {
  const form = new FormData();
  form.append("file", blob, filename);
  return fetch(`${API}/transcribe`, { method: "POST", body: form }).then((r) =>
    ok<Transcription>(r)
  );
}

export const audioUrl = (gen: Generation) => `${API}/generations/${gen.id}/audio`;

export type OutreachItem = {
  id: string;
  job_id: string;
  lead: Record<string, string>;
  text: string;
  output_path: string | null;
  status: "pending" | "done" | "failed";
  error: string | null;
  slug?: string | null;
  qc?: { warnings: string[]; checked_at: number } | null;
};

export type OutreachJob = {
  id: string;
  name: string;
  template: string;
  voice_id: string;
  language: string;
  format: string;
  status: "queued" | "running" | "stopping" | "stopped" | "done" | "failed";
  total: number;
  done: number;
  failed: number;
  created_at: number;
  site_built_at?: number | null;
  items?: OutreachItem[];
};

export function createOutreachJob(form: FormData) {
  return fetch(`${API}/outreach/jobs`, { method: "POST", body: form }).then((r) =>
    ok<OutreachJob>(r)
  );
}

export const getOutreachJobs = () =>
  fetch(`${API}/outreach/jobs`).then((r) => ok<OutreachJob[]>(r));
export const getOutreachJob = (id: string) =>
  fetch(`${API}/outreach/jobs/${id}`).then((r) => ok<OutreachJob>(r));
export const outreachItemAudioUrl = (id: string) => `${API}/outreach/items/${id}/audio`;
export const outreachZipUrl = (id: string) => `${API}/outreach/jobs/${id}/download`;

export type SiteBuildResult = {
  job_id: string;
  pages: number;
  skipped: number;
  warnings: string[];
  preview_url: string;
};

export const buildOutreachSite = (id: string) =>
  fetch(`${API}/outreach/jobs/${id}/site`, { method: "POST" }).then((r) =>
    ok<SiteBuildResult>(r)
  );
export const outreachSiteZipUrl = (id: string) => `${API}/outreach/jobs/${id}/site/download`;
export const outreachSiteIndexUrl = (id: string) => `${API}/sites/${id}/`;
export const outreachPageUrl = (jobId: string, slug: string) => `${API}/sites/${jobId}/${slug}/`;

export const deleteOutreachJob = (id: string) =>
  fetch(`${API}/outreach/jobs/${id}`, { method: "DELETE" }).then((r) =>
    ok<{ deleted: string }>(r)
  );

export const stopOutreachJob = (id: string) =>
  fetch(`${API}/outreach/jobs/${id}/stop`, { method: "POST" }).then((r) =>
    ok<OutreachJob>(r)
  );

export const rerenderOutreachItem = (id: string) =>
  fetch(`${API}/outreach/items/${id}/rerender`, { method: "POST" }).then((r) =>
    ok<{ item_id: string; job_id: string; status: string }>(r)
  );

export type OutreachPreview = {
  note?: string | null;
  columns: string[];
  total_rows: number;
  auto_skipped: number;
  filtered_out: number;
  will_render: number;
  template_variables: string[];
  missing_variables: string[];
  example: string | null;
  example_error: string | null;
  rendered?: { lead: Record<string, string>; text?: string; error?: string }[];
  rows: Record<string, string>[];
};

export function previewOutreach(form: FormData) {
  return fetch(`${API}/outreach/preview`, { method: "POST", body: form }).then((r) =>
    ok<OutreachPreview>(r)
  );
}

export type BusinessProfile = {
  business_name: string;
  one_liner: string;
  what_we_do: string;
  tone_of_voice: string;
  target_customer: string;
  website: string;
  linkedin: string;
  other_links: string;
  email: string;
  cta_label: string;
  phone: string;
  website2: string;
  primary_language: string;
  secondary_languages: string[];
  cv_text: string;
  cv_link: string;
};

export type ExtractedLead = {
  name: string;
  business: string;
  email: string;
  phone: string;
  website: string;
  context: string;
  notes: string;
};

export const extractLeads = (raw_text: string, override_budget = false, signal?: AbortSignal) =>
  fetch(`${API}/outreach/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text, override_budget }),
    signal,
  }).then((r) =>
    ok<{ provider: string; leads: ExtractedLead[]; budget_warning: string | null }>(r)
  );

export const suggestTemplates = (
  body: {
    columns: string[];
    sample_rows: Record<string, string>[];
    language: string;
    offer?: string;
    override_budget?: boolean;
  },
  signal?: AbortSignal
) =>
  fetch(`${API}/outreach/suggest-templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }).then((r) =>
    ok<{ provider: string; templates: string[]; budget_warning: string | null }>(r)
  );

export const uploadCv = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API}/profile/cv`, { method: "POST", body: form }).then((r) =>
    ok<BusinessProfile>(r)
  );
};

export const getProfile = () => fetch(`${API}/profile`).then((r) => ok<BusinessProfile>(r));
export const putProfile = (p: BusinessProfile) =>
  fetch(`${API}/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(p),
  }).then((r) => ok<BusinessProfile>(r));

export type DraftingSettings = {
  order: string[];
  enabled: Record<string, boolean>;
  budgets: Record<string, { weekly: number | null; monthly: number | null }>;
  models: Record<string, { model?: string; effort?: string }>;
};

export type DraftingUsageRow = {
  provider: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  leads: number;
  any_estimated: number;
};

export const getDraftingUsage = () =>
  fetch(`${API}/drafting/usage`).then((r) =>
    ok<{ usage: { week: Record<string, DraftingUsageRow>; month: Record<string, DraftingUsageRow> }; settings: DraftingSettings }>(r)
  );

export const putDraftingSettings = (s: DraftingSettings) =>
  fetch(`${API}/drafting/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(s),
  }).then((r) => ok<DraftingSettings>(r));

export type MaintenanceStatus = {
  last_run: number | null;
  due: boolean;
  interval_days: number;
};

export const getMaintenance = () =>
  fetch(`${API}/maintenance`).then((r) => ok<MaintenanceStatus>(r));

export type DraftResult = {
  provider: string;
  messages: string[];
  input_tokens: number;
  output_tokens: number;
  estimated: boolean;
  budget_warning: string | null;
};

export function draftMessages(body: {
  leads: Record<string, string>[];
  language: string;
  instructions?: string;
  override_budget?: boolean;
}) {
  return fetch(`${API}/outreach/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => ok<DraftResult>(r));
}
