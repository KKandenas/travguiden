#!/bin/sh
# Kör JS-testerna utan Node, med macOS inbyggda JavaScriptCore (jsc). I GitHub Actions körs de med
# `node --test tests/js/*.test.mjs`. Testfilerna kopieras till en tillfällig katalog där node:test och
# node:assert/strict byts mot enkla ersättare, och ../../docs/ pekar på projektets docs/.
set -e
JSC=/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc
ROT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/shim_test.mjs" <<'JS'
export const resultat = [];
export function test(namn, fn) {
  resultat.push(Promise.resolve().then(fn).then(() => "ok   " + namn, (e) => "FEL  " + namn + " :: " + (e && e.message)));
}
JS
cat > "$TMP/shim_assert.mjs" <<'JS'
const s = (x) => JSON.stringify(x);
function assert(v, m) { if (!v) throw new Error(m || "assert"); }
assert.ok = assert;
assert.equal = (a, b, m) => { if (a !== b) throw new Error(m || `${s(a)} !== ${s(b)}`); };
assert.deepEqual = (a, b, m) => { if (s(a) !== s(b)) throw new Error(m || `${s(a)} != ${s(b)}`); };
assert.match = (a, r, m) => { if (!r.test(a)) throw new Error(m || `${a} matchar inte ${r}`); };
export default assert;
JS
IMPORTER=""
for f in "$ROT"/tests/js/*.test.mjs; do
  namn=$(basename "$f")
  sed -e "s#\"node:test\"#\"./shim_test.mjs\"#" -e "s#\"node:assert/strict\"#\"./shim_assert.mjs\"#" \
      -e "s#\"\.\./\.\./docs/#\"$ROT/docs/#g" "$f" > "$TMP/$namn"
  IMPORTER="$IMPORTER import \"./$namn\";"
done
cat > "$TMP/kor.mjs" <<JS
$IMPORTER
import { resultat } from "./shim_test.mjs";
const r = await Promise.all(resultat);
r.forEach((x) => print(x));
const fel = r.filter((x) => x.startsWith("FEL")).length;
print(\`\n\${r.length - fel} ok, \${fel} fel\`);
if (fel) throw new Error(fel + " test misslyckades");
JS
cd "$TMP" && "$JSC" -m kor.mjs
