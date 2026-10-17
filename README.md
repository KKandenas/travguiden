# Travguiden

Föreslår ett system till lördagens V-spel (V85, och V75 från 28 november 2026) utifrån hur mycket du vill spela för, med streck, chans och värde för varje häst.
Tre förslag: **Oddsen** (streck och vinnarodds), **Experterna** (Oddsen plus experternas system från ATG) och
**Skrällchansen** (Oddsen med 1–2 understreckade hästar).
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
- **AI** (Gemini) skriver en kort kommentar per avdelning, bara från pipelinen. Experternas tips är strukturerade
  ATG-kuponger och behöver ingen AI. Ingen inloggning än.

## V85 och V75

V85 ersatte V75 den 25 oktober 2025. **Den 28 november 2026 kommer V75 tillbaka** och V85 pausas (sista V85-datum
är inte bestämt). Allt i Travguiden utgår från spelformen per omgång:

| | V85 | Nya V75 (från 28 nov 2026) | Gamla V75 (2023–2025) |
|---|---|---|---|
| Avdelningar | 8 | 7 | 7 |
| Utdelning | 8, 7, 6, 5 rätt | 7, 6, 5 rätt | 7, 6, 5 rätt |
| Radpris | 50 öre | 60 öre | 50 öre |

- Pipelinen följer `config.SPELFORMER = ["V85", "V75"]` och tar den närmaste kommande omgången av dem, så bytet
  sker av sig självt när ATG lägger ut den första nya V75:an. Radpriset kommer från `config.radpris()`.
- `omgang.json` har `"spel": {spelform, antal_avd, radpris, vinstgrupper}`, och appen läser allt därifrån.
- Experternas kuponger känns igen för båda spelformerna (`V85_…` och `V75_…`).
- **Inte med:** tillägget V7 (man avstår 6 och 5 rätt och får 2,5 gånger utdelningen för 7 rätt) och Boost.

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
| `python -m pipeline planerad` | Det schemat startar: kör `auto` bara när en planerad tid har passerats |
| `python -m pipeline auto` | En uppdatering nu: kommande omgång, resultat, träning när en ny omgång avgjorts, export |
| `python -m pipeline atg` | Kommande V85/V75: hästar, streck och vinnarodds |
| `python -m pipeline experter` | Experternas system ur ATG:s tipsartiklar för kommande V85 |
| `python -m pipeline resultat` | Resultat och utdelning för omgångar efter spelstopp |
| `python -m pipeline backfill 2025-10-25 2026-10-13` | Hämta alla V85 mellan två datum (pausar mellan anropen) |
| `python -m pipeline backfill 2023-01-01 2025-10-24 --spelform V75` | Äldre V75 som extra träningsdata (används inte i backtestet) |
| `python -m pipeline statistik` | Skatta vikterna (walk-forward), utvärdera mot strecken, räkna om prognoserna |
| `python -m pipeline prognos [--alla]` | Räkna chans per häst |
| `python -m pipeline export` | Skriv `docs/omgang.json`, `senaste.json` och `historik.json` |
| `python -m pipeline export --omgang V85_2026-10-10_5_6 --till docs/exempel-omgang.json --dolj-resultat` | Skapa exempelfilen |

| `python -m pipeline kommentarer` | AI-kommentarer per avdelning för kommande V85 (kräver `GEMINI_API_KEY`) |

Lägg till `-v` för mer loggning. Miljövariabeln `TRAV_DB` styr vilken databasfil som används.

## GitHub

1. Skapa ett publikt repo och pusha. Secret `GEMINI_API_KEY` behövs bara för AI-kommentarerna.
2. **Settings → Pages**: Deploy from branch, `main` och `/docs`.
3. Om workflowet får "permission denied" vid push: **Settings → Actions → General → Workflow permissions → Read and write**.

`.github/workflows/pipeline.yml` startar pipelinen varje timme (var 20:e minut på lördagar 10–17) med
`python -m pipeline planerad`. GitHubs schemaläggning kan bli flera timmar sen, så schemat i `pipeline/schema.py`
(svensk tid) avgör när något körs: varje dag 08:00, 18:30 och 22:30, och på lördagar dessutom 11:00, 13:00, 14:00,
14:30, 14:50, 15:40 och 16:10. En start kör bara när en planerad tid har passerats och inte körts än; en missad tid
tas igen vid nästa start. Övriga starter avslutas direkt utan API-anrop. Samma upplägg som i Stryktipsguiden.
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
| `expertsystem`, `expertval` | Experternas system (en rad per kupong) och valda hästar per avdelning |
| `installningar` | Skattade vikter och utvärdering |

**Felhantering:** varje omgång valideras innan den sparas (8 avdelningar, unika startnummer, streck som
summerar till cirka 100 % per avdelning). En avdelning med trasiga streck sparas utan streck.

## Chansen per häst

`pipeline/model/`. Grunden är V85-strecken. Modellen `kalibrerad-v1` är en villkorad logit (softmax per lopp):

    chans ∝ streck^a · (oddschans / streck)^b

- **a** plattar ut strecken och skattas **separat för V85 och V75** (egenskapen `log_streck_v85`). V85-spelarna
  är för säkra på favoriterna (a ≈ 0,84), medan V75-strecken 2023–2025 redan var välkalibrerade (a ≈ 0,94, i
  praktiken som strecken).
- **b** väger in vinnaroddsen när vinnarpoolen har pengar (på tävlingsdagen). Skattas bara på avdelning 1,
  där slutoddsen sattes samtidigt som V85 stängde. I senare avdelningar är slutoddsen satta efter spelstopp och
  skulle läcka information.
- Vikterna skattas med Newtons metod på alla avgjorda lopp, V85 och V75 sedan 2023 (cirka 2 100 lopp), med ett
  L2-straff mot "strecken har rätt" (a = 1, b = 0).
- **Walk-forward:** varje månad (från juni 2023, när det finns 150 tidigare lopp) skattas vikter på bara tidigare
  lopp. Backtestet och utvärderingen använder dem; omgångar utan sådana vikter tas inte med i backtestet.

Walk-forward-utvärdering i oktober 2026, logloss för vinnaren (lägre är bättre):

| | Lopp | Strecken | Oddsen | Förbättring |
|---|---|---|---|---|
| V85 | 608 | 1,8095 | 1,7995 | 0,0100 ± 0,0063 |
| V75 2023–2025 | 1 302 | 1,7843 | 1,7848 | −0,0005 ± 0,0027 |
| Alla | 1 910 | 1,7923 | 1,7895 | 0,0028 ± 0,0027 |

(Med en gemensam exponent för båda spelformerna blev V85 0,0105 ± 0,0035 och V75 −0,0005.)

Testat och inte infört (ingen förbättring utöver strecken i testet på V85): startspår i andra ledet (autostart),
tillägg, kuskens segerprocent i år, hästens segerandel i karriären. Folket har redan prisat in dem.

## Experterna

`pipeline/sources/atgtips.py` hämtar experternas system ur ATG:s tipsartiklar, främst *Fem tippar V85* (fem kuskar,
tränare och gäster, 240 rader var) och artiklar med Fernlund, Olsson med flera. Se DATAKALLOR.md för hur.
Harry Boy-kuponger (ATG:s slumpsystem) räknas inte. **ATG raderar kupongerna efter loppet**, så de sparas när de
hittas, och historik finns bara från och med oktober 2026. Därför går Experterna inte att backtesta bakåt.

Modellen `experter-v1` lägger till en egenskap i Oddsens logit:

    chans ∝ … · (expertandel + 0,05)^c

där *expertandel* är snittet över systemen av 1/(antal valda hästar i avdelningen) om hästen är med (en spik hos
alla ger 1, en av fyra hos en av fem tippare 0,05). Hästar i lopp utan expertsystem påverkas inte. **c = 0,15**
tills det finns 150 avgjorda lopp med expertsystem (cirka 19 omgångar); därefter skattas c walk-forward som Oddsens
vikter. Experterna publicerar tidigt i veckan och strecken tar in mycket av deras bedömning, därav den försiktiga
startvikten.

## Skrällchansen

Experternas chans (Oddsens när expertsystemen inte kommit än), men systemet måste innehålla omgångens bästa
skrällar (`SKRALL` i `docs/optimizer.js`). En häst som experterna tar med trots lågt streck rankas alltså högre:
en häst som inte är favorit, har högst 15 % av strecken, minst 5 % chans och chans/streck minst 1,15. Bästa kandidaten
per avdelning, högst tre per omgång. En skräll upp till 200 kr, två över det.

Backtest, återbetalning vid 25/50/100/120/150/200/300/500 kr:

| | Alla 262 omgångar (V75 och V85 sedan juni 2023) | Bara V85 (76 omgångar) |
|---|---|---|
| Oddsen | 85/65/59/47/52/57/56/45 % | 34/34/24/27/24/23/35/39 % |
| Skrällchansen | 84/62/52/46/43/43/41/38 % | 47/37/34/34/31/34/36/28 % |
| Strecken | 87/67/59/47/45/54/59/43 % | 34/34/24/27/24/23/27/37 % |

På bara V85 såg Skrällchansen bättre ut, men över hela perioden är den sämre än Oddsen.

**Analys av skrällarna (oktober 2026).** Hur ofta hästar som inte är favorit vinner, delat med vad strecken säger:

| Streck | V75 2023–2025 | V85 |
|---|---|---|
| under 3 % | 1,29 | 1,53 |
| 3–6 % | 1,19 | 1,33 |
| 6–10 % | 0,92 | 1,28 |
| 10–15 % | 0,86 | 0,86 |
| 15–25 % | 1,02 | 0,94 |

Regelns kandidater vann 6,0 % mot strecken 5,0 % över alla 262 omgångar (V85: 7,5 % mot 5,0 %), alltså något
oftare än strecken säger. Ett smalare intervall (3–10 % streck) prövades: kandidaterna vann 3,7–3,9 % mot strecken
3,8 % (ingen fördel), trots att återbetalningen råkade bli högre på vissa insatser. Regeln behölls. Att
Skrällchansen ändå ger lägre återbetalning än Oddsen beror på att skrällarna tar rader från resten av systemet,
och på slumpen i storvinsterna. Vinnaroddsen i avdelning 1 (slutodds vid stängning) pekade åt samma håll som
strecken redan gör för lågt streckade hästar och tillförde lite. Experternas skrällar går inte att utvärdera
förrän omgångar med sparade expertsystem är avgjorda. Trösklarna är valda i förväg och inte efter backtestet: närliggande trösklar gav allt från 21 till
83 %, eftersom ett fåtal storvinster avgör. I historiken finns bara kalibrerade streck (inga vinnarodds före
spelstopp), så kandidaterna blir få (0,45 per omgång). Skrällchansen blir meningsfull på tävlingsdagen, när
vinnaroddsen säger emot strecken.

## Hästkoll (steg 1: utrustning och form)

`atg.hamta_hastinfo` läser `/races/{id}/extended` per lopp: skor fram/bak och vagn (med ATG:s markering om något
ändrats sedan förra starten) och de fem senaste starterna (datum, bana, placering, galopp, diskvalificering, odds,
km-tid, spår, kusk, utrustning och TR Medias loppkommentar). För gamla lopp visar ATG starterna före loppet, så
historiken kan testas utan läckage. Sparas i `starter` (skor, vagn) och `tidigare_starter`.

Appen visar formen (t.ex. `1-1-2-1g-1`, senaste först, g = galopp, d = diskad), markeringar för barfota/skobyte,
vagnbyte och kuskbyte, och de senaste starterna i hästens detaljer. AI-kommentarerna får samma uppgifter.
Kommande omgångar hämtas vid varje körning; historiken fylls på med 16 lopp per körning eller
`python -m pipeline hastinfo --max 600`. Steg 2 (AI som tolkar loppkommentarerna) väntar på analysen av steg 1.

## AI-kommentarer

`pipeline/ai/klient.py` är samma klient som i Stryktipsguiden: Gemini med reservkedjan gemini-3.8-flash →
3.5-flash-lite → 3.1-flash-lite → 3.7-flash → 3.6-flash (repo-variabel `GEMINI_RESERVMODELLER`), högst 4 anrop per
minut och modell (gratisnivån tillåter 5; repo-variabel `GEMINI_RPM`), en minuts vila för en modell som svarar 429,
tidsgränser och Claude som alternativ. Håll filen lika i båda repona. `pipeline/ai/kommentarer.py` skriver 1–2 meningar per avdelning från streck, chans, experternas val och
hästarnas statistik. AI:n får inga artikeltexter. En kommentar skrivs om när en häst stryks eller nya expertsystem
kommer, eller när underlaget ändrats och kommentaren är äldre än 20 timmar. Alla avdelningar som behöver en ny
kommentar tas i ett anrop, så det blir ett par anrop om dagen.

**Egen kvot:** Geminis gratisgränser gäller per Google-projekt, inte per nyckel. Travguidens nyckel ska därför
komma från ett **eget projekt** i Google AI Studio, så att Stryktipsguidens kvot inte påverkas.
Utan nyckel (eller på Python < 3.10) hoppas steget över med en loggrad.

## Systemet (`docs/optimizer.js`)

Antalet rader är produkten av antalet hästar per avdelning, och en rad kostar 50 öre. Poäng per avdelning med hästarna S:

    (1 − λ) · log(Σ chans) + λ · log(Σ chans / streck)

Första delen är chansen att avdelningen sitter. Den andra är förväntad utdelning: understreckade hästar betalar
mer. Inom en avdelning prövas alla delmängder av hästar (högst 2^16), och dynamisk programmering över antalet
rader väljer den bästa kombinationen inom budgeten. Låsta hästar måste vara med.

**λ = 0,3.** Backtest på 76 V85-omgångar (oktober 2025 – oktober 2026, budgetarna som fanns då), återbetalning:

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
| `#kupong` | Veckans V85: välj förslag (Oddsen, Experterna, Skrällchansen) och insats (25–500 kr; bland annat 120 kr = 240 rader och 150 kr i V85). En rad per avdelning med de spelade hästarna; fäll ut för alla hästar, AI-kommentar, låsningar och detaljer |
| `#rattning` | Förra omgången: vinnare, antal rätt, rader per antal rätt och vinst för valt förslag och insats |
| `#backtest` | Om du spelat varje omgång: saldo över tid för förslagen och för bara strecken. Period: alla omgångar (V75 och V85 sedan 2023), sedan premiären (17 oktober 2026), bara V85 eller från ett visst år. Antal rätt visas som "alla rätt / 1 fel / 2 fel / 3 fel" eftersom V75 och V85 har olika många avdelningar |
| `#om` | Så funkar Travguiden: förslagen, chansen, systemet, aktuell utvärdering och källor |

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
| Skatta experternas vikt (c) och backtesta Experterna | Efter cirka 19 omgångar med sparade expertsystem (februari 2027) |
| Fler experter: ATG:s tipskommentarer per häst, tipssajter | Tipssajterna kräver AI-tolkning (Gemini) |
| Ompröva λ med fler omgångar | Våren 2027 |
| Inloggning och Mina spel som i Stryktipsguiden | Senare |
| AI-kommentarer per avdelning (travtips från tidningar) | Senare, så att Geminis gratiskvot räcker till Stryktipsguiden |
| Reservhästar i rättningen | Om det efterfrågas |
