/** Pure suggestion matching for the hospital search box. */
export type HospitalOption = { id: string; name: string; note?: string };

/** Lower-case words, ignoring punctuation, so "ace medical" finds "ALLIED CARE EXPERTS (ACE) MEDICAL CENTER". */
const words = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(' ').filter(Boolean);

/** Hospitals whose name contains every typed word (as a word prefix), best matches first. */
export function matchHospitals(options: HospitalOption[], query: string) {
  const typed = words(query);
  if (!typed.length) return options;
  return options
    .map(option => {
      const name = words(option.name);
      const hits = typed.map(word => name.findIndex(part => part.startsWith(word)));
      return { option, hits };
    })
    .filter(({ hits }) => hits.every(index => index >= 0))
    .sort((a, b) => Math.min(...a.hits) - Math.min(...b.hits) || a.option.name.localeCompare(b.option.name))
    .map(({ option }) => option);
}
