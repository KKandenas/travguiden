# Travguiden

Föreslår ett V85-system utifrån hur mycket du vill spela för, med streck, chans och värde för varje häst.
Bakom appen samlar en automatisk pipeline på GitHub historik från ATG, så att bedömningen kan förbättras över tid.
Systerprojekt till [Stryktipsguiden](../Stryktipsguiden), med samma upplägg.

```
GitHub Actions (schema)                          GitHub Pages
┌──────────────────────────────┐   committar    ┌──────────────────────────┐
│ python -m pipeline auto      │ ─────────────▶ │ docs/  (statisk webbapp) │
│  ATG: hästar, streck, odds,  │  data/trav.db  │  läser omgang.json m.fl. │
│  resultat, utdelning         │  docs/*.json   └──────────────────────────┘
└──────────────────────────────┘
```

- **Pipeline** (`pipeline/`): Python. Hämtar data från ATG, sparar i SQLite (`data/trav.db`, committas
  till repot), räknar chans per häst och exporterar JSON till appen.
- **App** (`docs/`): HTML, CSS och JS utan byggsteg. Ingen backend och inga nycklar.
- Ingen inloggning och ingen AI än (se [Idéer](#idéer-som-väntar)).

## Kom igång lokalt

Kräver Python 3.9 eller senare. Inga API-nycklar behövs.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest              # testerna kräver inget nätverk
.venv/bin/python -m pipeline auto       # hämtar det som är aktuellt just nu
python3 -m http.server 8766 -d docs     # öppna http://localhost:8766
```

| Kommando | Gör |
|---|---|
| `python -m pipeline auto` | Det schemat kör: kommande omgång, resultat, träning när en ny omgång avgjorts, export |
| `python -m pipeline atg` | Kommande V85: hästar, streck och vinnarodds |
| `python -m pipeline resultat` | Resultat och utdelning för omgångar efter spelstopp |
| `python -m pipeline backfill 2025-10-25 2026-10-13` | Hämta alla V85 mellan två datum (pausar mellan anropen) |
| `python -m pipeline backfill 2023-01-01 2025-10-24 --spelform V75` | Äldre V75 som extra träningsdata (används inte i backtestet) |
| `python -m pipeline statistik` | Skatta vikterna (walk-forward), utvärdera mot strecken, räkna om prognoserna |
| `python -m pipeline prognos [--alla]` | Räkna chans per häst |
| `python -m pipeline export` | Skriv `docs/omgang.json`, `senaste.json` och `historik.json` |
| `python -m pipeline export --omgang V85_2026-10-10_5_6 --till docs/exempel-omgang.json --dolj-resultat` | Skapa exempelfilen |

Lägg till `-v` för mer loggning. Miljövariabeln `TRAV_DB` styr vilken databasfil som används.

## GitHub

1. Skapa ett publikt repo och pusha. Inga secrets behövs.
2. **Settings → Pages**: Deploy from branch, `main` och `/docs`.
3. Om workflowet får "permission denied" vid push: **Settings → Actions → General → Workflow permissions → Read and write**.

`.github/workflows/pipeline.yml` kör `python -m pipeline auto` varje dag 08, 18:30 och 22:30 (svensk sommartid)
och extra på lördagar fram till spelstopp, eftersom vinnaroddsen bara sparas när vinnarpoolen har pengar.
Alla steg är idempotenta. Under **Actions → Pipeline → Run workflow** går det att köra manuellt, även backfill.

## Databasen

`data/trav.db` (SQLite). Alla tider i UTC. Migreringar i `pipeline/migrations/NNN_namn.sql` körs automatiskt
i nummerordning. Ändra aldrig en fil som redan körts – lägg till en ny.

| Tabell | Innehåll |
|---|---|
| `omgangar` | En per spel (`V85_2026-10-17_16_5`): bana, datum, spelstopp (första start), omsättning, avgjord |
| `utdelning` | Kr per rad och antal vinnande rader för 5–8 rätt |
| `avdelningar` | 8 per omgång: lopp, distans, startmetod, starttid, vinnare (flera vid dött lopp) |
| `starter` | Häst, kusk, tränare, spår, distans, struken, statistik före loppet, placering, slutodds |
| `streck` | V85-strecken (andel), en rad per ögonblicksbild där värdet ändrats |
| `vinnarodds` | Vinnaroddsen per ögonblicksbild, bara när vinnarpoolen omsätter minst 100 000 kr |
| `prognoser` | Chans per häst och modellversion |
| `installningar` | Skattade vikter och utvärdering |

**Felhantering:** varje omgång valideras innan den sparas (8 avdelningar, unika startnummer, streck som
summerar till cirka 100 % per avdelning). En avdelning med trasiga streck sparas utan streck.

## Chansen per häst

`pipeline/model/`. Grunden är V85-strecken. Modellen `kalibrerad-v1` är en villkorad logit (softmax per lopp):

    chans ∝ streck^a · (oddschans / streck)^b

- **a** plattar ut strecken. Folket är för säkert på favoriterna, så a < 1.
- **b** väger in vinnaroddsen när vinnarpoolen har pengar (på tävlingsdagen). Skattas bara på avdelning 1,
  där slutoddsen sattes samtidigt som V85 stängde. I senare avdelningar är slutoddsen satta efter spelstopp och
  skulle läcka information.
- Vikterna skattas med Newtons metod på alla avgjorda lopp, V85 och V75 sedan 2023 (cirka 2 100 lopp), med ett
  L2-straff mot "strecken har rätt" (a = 1, b = 0).
- **Walk-forward:** varje månad skattas vikter på bara tidigare lopp. Backtestet och utvärderingen använder dem.

Utvärdering i oktober 2026, logloss för vinnaren (lägre är bättre):

| Test | Lopp | Strecken | Modellen | Förbättring |
|---|---|---|---|---|
| Tränad på V75 2023–2025, testad på all V85 | 608 | 1,8091 | 1,8001 | 0,0090 ± 0,0028 |
| Walk-forward på V85 | 608 | 1,8095 | 1,7990 | 0,0105 ± 0,0035 |

Testat och inte infört (ingen förbättring utöver strecken i testet på V85): startspår i andra ledet (autostart),
tillägg, kuskens segerprocent i år, hästens segerandel i karriären. Folket har redan prisat in dem.

## Systemet (`docs/optimizer.js`)

Antalet rader är produkten av antalet hästar per avdelning, och en rad kostar 50 öre. Poäng per avdelning med hästarna S:

    (1 − λ) · log(Σ chans) + λ · log(Σ chans / streck)

Första delen är chansen att avdelningen sitter. Den andra är förväntad utdelning: understreckade hästar betalar
mer. Inom en avdelning prövas alla delmängder av hästar (högst 2^16), och dynamisk programmering över antalet
rader väljer den bästa kombinationen inom budgeten. Låsta hästar måste vara med.

**λ = 0,3.** Backtest på 76 V85-omgångar (oktober 2025 – oktober 2026), återbetalning:

| λ | 50 kr | 100 kr | 200 kr | 500 kr | 1000 kr |
|---|---|---|---|---|---|
| 0 | 34 % | 24 % | 24 % | 37 % | 44 % |
| 0,3 | 34 % | 24 % | 23 % | 39 % | 47 % |
| 0,5 | 34 % | 26 % | 25 % | 43 % | 42 % |
| 0,7 | 17 % | 10 % | 8 % | 6 % | 5 % |

Upp till λ ≈ 0,5 spelar risknivån liten roll. Vid 0,7 jagar systemet outsiders och träffar sällan. Travguiden och
"bara strecken" ger nästan samma system i historiken: kalibreringen ändrar inte vilka hästar som är favoriter.
Det som kan ge ett riktigt försprång är skillnaden mellan vinnarpoolen och V85-strecken på tävlingsdagen. Den
kan inte backtestas förrän pipelinen har sparat odds före spelstopp i några månader. V85 delar ut ungefär
65 % av omsättningen, och små system når sällan de stora 8-rättsvinsterna, så låg återbetalning är väntat.

Orange prick: chansen är minst 2 procentenheter över strecken (`VARDE_GRANS`). En vald häst som stryks
ersätts i rättningen av avdelningens mest streckade häst.

## Appen

Vyer (`#` i adressen så att bakåtknappen fungerar):

| Vy | Innehåll |
|---|---|
| `#kupong` | Veckans V85 med systemförslag, låsningar och hästdetaljer |
| `#rattning` | Förra omgången: vinnare, antal rätt, rader per antal rätt och vinst för vald insats |
| `#backtest` | Om du spelat varje omgång: saldo över tid, Travguiden mot strecken |
| `#om` | Så funkar Travguiden, med aktuell utvärdering |

Vald insats och låsningar sparas i webbläsarens localStorage. Lägg till `?exempel` i adressen för exempelomgången.

**Cache:** filerna laddas med versionsnummer (`app.js?v=…`). **Byt versionen överallt när appen ändras**
(`index.html`, `app.js`, `backtest.js`). `tests/test_appfiler.py` kontrollerar att de är lika.

## Tester

```bash
.venv/bin/python -m pytest
node --test tests/js/*.test.mjs     # kräver Node 18+, körs annars i GitHub Actions
```

## Idéer som väntar

| Idé | När |
|---|---|
| Utvärdera vinnaroddsen (b) på riktiga ögonblicksbilder före spelstopp | När ett par månaders odds från lördagarna finns sparade |
| Ompröva λ med fler omgångar | Våren 2027 |
| Inloggning och Mina spel som i Stryktipsguiden | Senare |
| AI-kommentarer per avdelning (travtips från tidningar) | Senare, så att Geminis gratiskvot räcker till Stryktipsguiden |
| Reservhästar i rättningen | Om det efterfrågas |
