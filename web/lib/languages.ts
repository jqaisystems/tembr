// Chatterbox Multilingual language ids with display names.
export const LANGUAGES: [string, string][] = [
  ["en", "English"],
  ["pt", "Português"],
  ["es", "Español"],
  ["fr", "Français"],
  ["de", "Deutsch"],
  ["it", "Italiano"],
  ["nl", "Nederlands"],
  ["pl", "Polski"],
  ["da", "Dansk"],
  ["sv", "Svenska"],
  ["no", "Norsk"],
  ["fi", "Suomi"],
  ["el", "Ελληνικά"],
  ["ru", "Русский"],
  ["tr", "Türkçe"],
];

export const languageName = (id: string) =>
  LANGUAGES.find(([code]) => code === id)?.[1] ?? id;

// Primary language first, then secondaries in their saved order, then the rest.
export function orderLanguages(
  primary?: string,
  secondaries?: string[]
): [string, string][] {
  const front = [primary, ...(secondaries ?? [])].filter(
    (id, i, arr): id is string => !!id && arr.indexOf(id) === i
  );
  const frontEntries = front
    .map((id) => LANGUAGES.find(([code]) => code === id))
    .filter((e): e is [string, string] => !!e);
  const rest = LANGUAGES.filter(([code]) => !front.includes(code));
  return [...frontEntries, ...rest];
}
