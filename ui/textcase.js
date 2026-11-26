'use strict';
// Text case conversions of the island's "case" section. Pure: tests/test_textcase.py runs them under Node.
const TextCase = (() => {
  const lower = s => s.toLocaleLowerCase(), upper = s => s.toLocaleUpperCase();
  const MODES = {
    upper,
    lower,
    // first letter of the text and of each sentence (after . ! ? or a new line) upper case, the rest lower case
    sentence: s => lower(s).replace(/(^\s*|[.!?]\s+|\n\s*)(\p{L})/gu, (m, p, c) => p + upper(c)),
    // first letter of every word ("l'isola" stays one word)
    capital: s => lower(s).replace(/(^|[^\p{L}\p{N}'’])(\p{L})/gu, (m, p, c) => p + upper(c)),
    // letters only alternate, starting lower case: "aLtErNaTe"
    alternate: s => { let i = 0; return [...s].map(c => /\p{L}/u.test(c) ? (i++ % 2 ? upper(c) : lower(c)) : c).join(''); },
    inverse: s => [...s].map(c => { const u = upper(c); return c === u ? lower(c) : u; }).join(''),
  };
  const convert = (mode, s) => MODES[mode] ? MODES[mode](String(s ?? '')) : String(s ?? '');
  const counts = s => ({chars: [...String(s ?? '')].length, words: (String(s ?? '').match(/[\p{L}\p{N}][\p{L}\p{N}'’-]*/gu) || []).length});
  return {MODES: Object.keys(MODES), convert, counts};
})();

if (typeof module !== 'undefined') module.exports = TextCase;
