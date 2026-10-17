// fold(): the one text normalisation search uses, here and in the pipeline (pipeline/textfold.py, the same rules and
// the same test vectors, web/test/fixtures/fold.json). Lower case; accents off; "S:ta " before a name becomes
// "sankta ", and "S:t", "St." and "St" before a name "sankt"; runs of characters that are neither letters nor digits
// become one space; a trailing "Stockholm" and a postcode after a house number go. A name starts with a letter or a
// number that is not a plain digit ("½"), as Python's [^\W\d_] reads it.
const SANKTA = /(?<![\p{L}\p{N}])s:ta\s+(?=[\p{L}\p{Nl}\p{No}])/gu;
const SANKT = /(?<![\p{L}\p{N}])(?:s:t\s*|st\.\s*|st\s+)(?=[\p{L}\p{Nl}\p{No}])/gu;
const NOT_ALNUM = /[^\p{L}\p{N}]+/gu;
const CITY_TAIL = /^(.+) stockholm$/u;
const POSTCODE = /( \d+(?: ?[a-z])?) \d{3} ?\d{2}$/u;

export function fold(text) {
  let s = String(text ?? '').toLowerCase().normalize('NFD').replace(/\p{M}/gu, '');
  s = s.replace(SANKTA, 'sankta ').replace(SANKT, 'sankt ').replace(NOT_ALNUM, ' ').trim();
  return s.replace(CITY_TAIL, '$1').replace(POSTCODE, '$1');
}
