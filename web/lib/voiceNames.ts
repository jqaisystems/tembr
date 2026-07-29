// Naming voices so they can be told apart later.
//
// The old scheme derived a base from whatever name occurred most often, then
// filtered out anything that already existed. With one or two voices that
// returned an empty list, leaving the field blank. These build the index into
// the name instead, so a suggestion is unique by construction and says what
// the voice was made from.

import { relativeTime } from "@/lib/dates";
import { languageName } from "@/lib/languages";
import type { Voice } from "@/lib/api";

const ENGINE_LABELS: Record<string, string> = {
  chatterbox: "Chatterbox",
  qwen3tts: "Qwen",
};

export function engineLabel(engine: string): string {
  return ENGINE_LABELS[engine] ?? engine;
}

/** `base` plus the next free two-digit index, e.g. "Ana EN Reference 03". */
export function nextIndexedName(base: string, taken: Iterable<string>): string {
  const clean = base.trim().replace(/\s+\d+$/, "");
  const seen = new Set(Array.from(taken, (t) => t.trim().toLowerCase()));
  const re = new RegExp(`^${clean.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s+(\\d+)$`, "i");
  let highest = 0;
  for (const name of seen) {
    const m = name.match(re);
    if (m) highest = Math.max(highest, parseInt(m[1], 10));
  }
  let n = highest + 1;
  while (seen.has(`${clean} ${String(n).padStart(2, "0")}`.toLowerCase())) n++;
  return `${clean} ${String(n).padStart(2, "0")}`;
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** The speaker's name, if the library already agrees on one. */
function speakerFrom(voices: Voice[]): string | null {
  const counts = new Map<string, number>();
  for (const v of voices) {
    const first = v.name.trim().split(/\s+/)[0];
    if (first && first.length > 1 && !/^\d+$/.test(first)) {
      counts.set(first, (counts.get(first) ?? 0) + 1);
    }
  }
  const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  return best && best[1] >= 2 ? best[0] : null;
}

export function suggestVoiceNames(
  voices: Voice[],
  opts: { language: string; situation: string | null }
): string[] {
  const lang = opts.language.toUpperCase();
  const speaker = speakerFrom(voices) ?? "My voice";
  const situation = titleCase(opts.situation ?? "upload");
  const taken = voices.map((v) => v.name);
  const day = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short" });

  const bases = [
    `${speaker} ${lang} ${situation}`,
    `${speaker} ${lang}`,
    `${situation} ${lang} ${day}`,
  ];
  return [...new Set(bases.map((b) => nextIndexedName(b, taken)))].slice(0, 3);
}

/** Favourites first, then each collection, then everything else.
 *  Shared by every voice picker so they cannot drift apart. */
export function groupVoices(voices: Voice[]): [string, Voice[]][] {
  const favorites = voices.filter((v) => v.favorite);
  const rest = voices.filter((v) => !v.favorite);
  const collections = new Map<string, Voice[]>();
  const loose: Voice[] = [];
  for (const v of rest) {
    if (!v.collection) loose.push(v);
    else collections.set(v.collection, [...(collections.get(v.collection) ?? []), v]);
  }
  const groups: [string, Voice[]][] = [];
  if (favorites.length) groups.push(["Favorites", favorites]);
  for (const key of [...collections.keys()].sort()) {
    groups.push([key, collections.get(key)!]);
  }
  if (loose.length) groups.push([groups.length ? "Everything else" : "Voices", loose]);
  return groups;
}

/** Dropdown label that survives duplicate names. */
export function voiceLabel(v: Voice): string {
  const parts = [
    languageName(v.language),
    engineLabel(v.engine),
    relativeTime(v.created_at * 1000),
  ];
  return `${v.favorite ? "★ " : ""}${v.name} · ${parts.join(" · ")}`;
}
