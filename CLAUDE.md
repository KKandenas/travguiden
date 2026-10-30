# Travguiden – instruktioner för Claude

Statisk app (`docs/`, GitHub Pages: https://kkandenas.github.io/travguiden/) och en Python-pipeline (`pipeline/`) som
körs i GitHub Actions och ger systemförslag till lördagens V-spel: V85, och V75 från 28 november 2026. Systerprojekt
till Stryktipsguiden (`../Stryktipsguiden`), med samma upplägg. Detaljer finns i README.md, FARDPLAN.md (läget,
tidslinje med kontrollpunkter, beslutsregler, testat och inte infört) och DATAKALLOR.md.

## Arbetssätt

- Skriv på svenska, i chatten och i commit-meddelanden.
- Mobilen kommer först. Kontrollera layouten i mobilbredd (375 px, ingen sidledsscroll) och på dator.
- Bygg stegvis och stanna efter varje steg. Vid större byggen: beskriv upplägget först och låt användaren välja.
- Testa idéer innan de införs och redovisa resultatet ärligt även när det inte hjälper. Jämför alltid mot
  **Oddsens chans**, inte bara mot strecken – annars syns snedvridningen för lågt streckade hästar som en falsk
  effekt. Återbetalning i backtestet är brusig (ett fåtal storvinster avgör); använd logloss walk-forward och
  vinstandel mot förväntan som huvudmått.
- **Testat och inte infört** (gör inte om utan ny anledning): spår, tillägg, kusk- och hästform, kuskbyte,
  vagnbyte, vila, fartindex, klassbyte, skrällar i 3–10 % streck, λ ≥ 0,45, radval av de bästa enskilda raderna och
  reducering av större system. Se FARDPLAN.md.
- Föreslå gärna nästa steg, men gör inget större utan att användaren valt.

## Fasta beslut

- **Modellversioner ändras aldrig** (`pipeline/model/modeller.py`); en förbättring blir en ny version.
- Oddsen = `kalibrerad-v1`: strecken med separat exponent för V85 och V75 plus vinnarodds före spelstopp.
- Fyra förslag: Oddsen, Experterna (`experter-v1`, vikt 0,15 tills den skattats), Skrällchansen (Experternas chans,
  1 skräll upp till 200 kr, annars 2) och Hästkoll · test (`hastkoll-v1`, vikt 0,25 tills den skattats).
- Risknivån λ = 0,3 för både V85 och V75, utan reglage. Insatser: 25, 50, 100, 120, 150, 200, 300, 500 kr.
- **Kandidater** (`statistik.KANDIDATER`) vägs in först när de walk-forward är mer än två standardfel bättre än
  Oddsen på alla lopp sammantaget (minst 200 testlopp) och inte tydligt sämre i V75 eller V85. Kandidater som
  hittats genom att leta i historiken får ett startdatum (`fran`) och avgörs bara på nya lopp.
- Hästkoll: höj `hastkoll.VERSION` när instruktionen till AI:n ändras. TR Medias kortspråk: "x-utv"/"x-inv" är
  placering i ledet, inte spår ("1-utv" = dödens); tredjespår skrivs "3-spår".
- Spelformen följer omgången (`config.SPELFORMER`, `config.radpris`); inget får hårdkodas till 8 avdelningar eller
  50 öre.

## Drift och kostnader

- **AI: Geminis gratisnivå** från ett eget Google-projekt (skild kvot från Stryktipsguiden). Klienten
  `pipeline/ai/klient.py` är samma fil som i Stryktipsguiden – håll dem lika. Undvik onödiga manuella körningar
  med AI (`kommentarer`, `hastkoll`, `auto`).
- Schemat: `pipeline/schema.py` (svensk tid, lördagstider på kvartar). GitHub-cron är opålitlig, så pipelinen
  startas med `planerad` både av GitHubs cron och var 15:e minut av cron-job.org (README, "Extern start"). Nyckeln
  där sköter användaren själv. Kommer inga körningar alls: kontrollera först om nyckeln har gått ut eller jobbet är
  avaktiverat i cron-job.org.
- Data som bara finns en kort tid sparas när den hittas: experternas kuponger (404 efter loppet), TR Medias
  loppkommentarer (borta inom en vecka) och vinnarodds före spelstopp.
- Analyskommandon (ingen AI): `statistik`, `skrallanalys [--fran D]`, `oddsanalys [--fran D]`. Starta på GitHub
  med `gh workflow run pipeline.yml -f kommando=<namn>`; utan parametrar blir kommandot `planerad`.

## Säkerhet och källor

- Be aldrig om nycklar i chatten och lägg aldrig in dem själv. Användaren lägger in GitHub Secrets
  (GEMINI_API_KEY) och nyckeln i cron-job.org.
- ATG:s öppna data och tipsartiklar (Contentful-nyckeln läses ur atg.se:s HTML vid varje körning och sparas aldrig).
  Måttlig belastning, pauser vid backfill. Respektera robots.txt.
- Inga privatpersoners andelsspel (ATG Tillsammans) samlas in. Appen får inte efterlikna ATG.

## Utveckling

- Python: `python3 -m venv .venv` och `.venv/bin/pip install -r requirements-dev.txt`. Tester:
  `.venv/bin/python -m pytest -q`. Lokalt är det Python 3.9 utan AI-paket; AI-stegen hoppas då över.
- JS-tester: `node --test tests/js/*.test.mjs` (GitHub Actions). Utan Node lokalt: `tests/js/kor_lokalt.sh`
  (macOS JavaScriptCore).
- Förhandsvisning: `.claude/launch.json` ("travguiden", port 8766). Webbläsaren cachar `index.html`; ladda om med
  en ny `?t=` i adressen.
- Cache-busting: varje ändring i `docs/*.js` eller `app.css` kräver ny `?v=`-version, samma överallt (ett test
  kontrollerar det).
- Databasen ligger på grenen `databas` (bara senaste versionen, skrivs över av pipelinen) och veckovis som
  release-fil (`databas-kopior`); `data/` är inte med i main. Hämta den lokalt med
  `git fetch origin databas && git show origin/databas:trav.db > data/trav.db`. Pusha aldrig till `databas` lokalt.
- Pipelinen committar `docs/*.json` till main flera gånger om dagen. Kör `git pull --rebase` före push, och återställ
  lokala `docs/*.json` (`git checkout -- docs/omgang.json docs/senaste.json docs/historik.json`) innan commit – de
  skrivs av boten.
- Analyser mot den riktiga databasen görs på en kopia (`TRAV_DB=<kopia>`), så att inget lokalt krockar med botens data.
- Git-identiteten använder GitHubs noreply-adress.
