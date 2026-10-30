# Färdplan för Travguiden

*Skriven 25 oktober 2026. Uppdatera den när något i tidslinjen är gjort eller ett beslut har fattats.*

Grunden är byggd och går automatiskt. Det närmaste halvåret handlar om att få bytet till V75 att gå smidigt, samla
avgjorda omgångar med expertsystem, vinnarodds och Hästkoll, och fatta beslut när underlaget räcker. Inga nya
modeller vägs in innan data visar att de är bättre än strecken (se Beslutsregler).

## Läget i dag

| Del | Status |
|---|---|
| Spelform | V85 (8 avd, 50 öre). **V75 kommer tillbaka 28 november 2026** (7 avd, 60 öre); appen byter av sig själv. |
| Förslag | Oddsen, Experterna, Skrällchansen och Hästkoll · test. Insats 25–500 kr. |
| Oddsen (`kalibrerad-v1`) | Strecken kalibrerade per spelform (V85 a ≈ 0,84, V75 a ≈ 0,94) plus vinnarodds före spelstopp. |
| Experterna (`experter-v1`) | ATG:s tipsartiklar: Fem tippar, TR Media, Fernlund m.fl., cirka 9 system per omgång. Vikt 0,15 tills den kan skattas. |
| Skrällchansen | Experternas chans och 1–2 skrällar (högst 15 % streck, minst 5 % chans, kvot ≥ 1,15). |
| Hästkoll | Steg 1: utrustning, kuskbyte och form (visas). Steg 2: AI läser TR Medias loppkommentarer, version `hastkoll-3`, med faktorer per tidigare start. Eget förslag under test. |
| Kandidater | Barfota runt och Hästkoll följs walk-forward efter varje avgjord omgång (om-sidan, "Under test"). |
| Drift | cron-job.org startar pipelinen var 15:e minut; `pipeline/schema.py` avgör när något körs. Driftstatus på om-sidan. |
| AI | Gemini från ett eget Google-projekt (egen kvot), högst 4 anrop per minut och modell, Flash-Lite som reserv. |
| Data som inte går att hämta i efterhand | Experternas kuponger, TR Medias loppkommentarer och vinnarodds före spelstopp – sparas när de finns. |

## Tidslinje

### Vecka 44 (26 oktober – 1 november): vintertid
- [ ] Lördag 31 oktober (vintertid sedan 25 oktober): kontrollera i Actions att körningarna 14:30 och 14:45 kom
  före spelstopp och att driftstatusen visar vinnarodds. Tiderna i `schema.py` är svensk tid och följer med
  automatiskt.
- [ ] Måndag–torsdag: Hästkoll version 3 bedömer veckans omgång före loppen. Läs några motiveringar och
  faktorer (hästens detaljer i appen, eller tabellen `hastkoll_faktorer`) och kontrollera att kortspråket tolkas rätt.

### November: bytet till V75 (28 november)
- [ ] Veckan före: kontrollera att `/products/V75` har en kommande omgång och att appen visar den med 7
  avdelningar, 60 öre per rad och utdelning för 7–5 rätt.
- [ ] Kontrollera att experternas V75-kuponger hittas (Fem tippar V75 m.fl.) och att namnen blir rätt.
- [ ] Lördag 28 november: följ driftstatusen. Första V75 utan V85-historik i Hästkoll och Experterna.
- [x] **Beslut om kandidatregeln (25 oktober 2026):** kravet gäller alla lopp sammantaget (V75 och V85), med
  spärren att kandidaten inte får vara tydligt sämre i någon spelform. Tidigare krävdes 200 testlopp i *båda*,
  vilket Hästkoll aldrig hade kunnat nå när V85 pausas.

### December–januari (efter 8–12 omgångar): första avstämningen
- [ ] Vinnaroddsen: sedan 24 oktober finns ögonblicksbilder före spelstopp i alla avdelningar (tidigare bara
  slutodds i avdelning 1). Skatta oddsvikten b på riktiga förhandsodds och jämför med dagens 0,17–0,19.
- [ ] Hästkoll: första titt på kandidatraden (om-sidan) och på faktorerna – vilka faktorer i senaste starten
  hänger ihop med att hästen presterar bättre än strecken nästa gång?
- [ ] Förslagen "Sedan premiären" i backtestet: rimligt jämfört med backtestet, eller avviker något?

### Januari 2027: skrällanalys med experter och Hästkoll
- [ ] `python -m pipeline skrallanalys --fran 2026-10-17`: vinner experternas skrällval, hästar med Hästkoll
  "bättre" eller med faktorer som instängd/stark avslutning senast oftare än Oddsen säger? Mönster som ser starka ut
  blir kandidater med startdatum (`statistik.KANDIDATER`, fältet `fran`) och avgörs bara på nya lopp.
- [ ] Formfällan (kandidat sedan 25 oktober 2026): historiken 0,80 ± 0,05 i skrällanalysen och +0,0043 ± 0,0019
  walk-forward – håller den på nya lopp? Kan den också användas för att sortera bort skrällar i Skrällchansen?

### Februari–mars 2027 (cirka 19 omgångar med expertsystem)
- [ ] Experternas vikt skattas automatiskt när 150 avgjorda lopp med expertsystem finns (`statistik.MIN_EXPERTLOPP`).
  Kontrollera att vikten är rimlig och att Experterna klarar sig mot Oddsen i backtestet "Sedan premiären".

### Januari 2027 (cirka 13 omgångar med Hästkoll): kandidatutvärderingen börjar
- [ ] När 100 lopp med Hästkoll är avgjorda skattas dess vikt (ovanpå Oddsens) och walk-forward-jämförelsen börjar
  synas på om-sidan. Förslaget Hästkoll använder då den skattade vikten i stället för 0,25.

### Våren 2027 (cirka 25 omgångar): faktorerna
- [ ] Hästkoll: titta på kandidatraden. Ett besked kräver 200 testlopp efter de första 100, alltså cirka 40 omgångar
  (hösten 2027) – men en tydlig trend åt något håll syns tidigare.
- [ ] Faktoranalysen (15–20 omgångar med faktorer): vikta Hästkoll per faktor i stället för en samlad bedömning, om
  vissa faktorer tydligt bär och andra inte.
- [ ] Barfota runt: har kandidaten klarat kravet med de nya omgångarna?

### Hösten 2027 (ett år med V75): beslut om Hästkoll
- [ ] Hästkoll som kandidat (cirka 40 omgångar): klarar den kravet → in som en ny version av Oddsen. Klarar den det
  inte → behåll som förslag under test, ändra instruktionen (ny version) eller ta bort förslaget.
- [ ] Ompröva risknivån λ och skrällreglerna med ett års riktiga utdelningar för nya V75 (60 öre, ny poolfördelning
  40/20/40 %).
- [ ] Odds- och streckrörelser under lördagen: ögonblicksbilderna sparas sedan oktober 2026.

## Beslutsregler

- **När något får vägas in i Oddsen:** walk-forward mot nuvarande modell på alla lopp sammantaget, mer än två
  standardfel bättre, med minst 200 testlopp, och inte mer än två standardfel sämre i V75 eller V85. Oddsens vikter
  för varje månad skattas på alla tidigare lopp; bara kandidatens vikt skattas på kandidatens egna lopp (minst 100). Läggs in som en ny modellversion – en befintlig ändras aldrig.
- **När en idé testas:** på hela historiken och med flera tidsdelningar (före/efter, och omvänt). Införs bara om den
  håller i alla, och i riktiga utdelningar – inte bara i träffprocent.
- **Många samtidiga test:** testas tio signaler blir någon "signifikant" av en slump. Kräv att den håller i fler
  delningar innan den tas på allvar (barfota runt, oktober 2026).
- **Data:** inga källor som spärrar insamling i robots.txt. ATG:s öppna data och tipsartiklar används med
  måttlig belastning (pauser vid backfill).
- **AI:** bara från pipelinen, aldrig från appen. Höj `hastkoll.VERSION` när instruktionen ändras, så att versioner
  kan hållas isär i analysen.

## Testat och inte infört

Detaljerna finns i README.

| Idé | Resultat |
|---|---|
| Spår, tillägg, kuskens och hästens segerprocent som egenskaper | Ingen förbättring utöver strecken. |
| Kuskbyte, vagnbyte, vila, tät start, vann/galopp senast, form, odds senast | Ingen förbättring eller sämre. |
| Barfota för första gången | +0,0029 ± 0,0013, men försvann i omvänd delning. Följs som kandidat (från 17 okt 2026). |
| Formfällan (skrällanalysen, okt 2026) | Lågt streckade hästar som vann senast eller vinner ofta i år vann 0,80 gånger så ofta som Oddsen räknade med. Hittad i historiken, så den avgörs på lopp från 25 okt 2026. |
| Gemensam kalibrering för V75 och V85 | V75-strecken var redan välkalibrerade; separat exponent per spelform infördes. |
| Fartindex (km-tid mot bana, distans, startmetod, underlag) | Walk-forward +0,0001 ± 0,0009, ingen trend. Inprisat. |
| Klassbyte (förstapris i senaste loppen mot dagens) | Walk-forward +0,0005 ± 0,0006, ingen trend. Inprisat. |
| Skrällar bara i 3–10 % streck | Kandidaterna vann inte oftare än strecken sa; nuvarande regel behölls. |
| Risknivå λ 0,7 | Jagar outsiders, 5–17 % återbetalning. λ 0,3 behölls. |
| Vinnarodds i avdelning 1 (slutodds) | Pekar åt samma håll som strecken redan gör för lågt streckade hästar. Utvärderas om på förhandsodds. |

## Större idéer att besluta om

### Radval och filinlämning (utrett 30 oktober 2026, vilande)
- **Tekniskt möjligt:** ATG tar emot system från externa program som XML-fil under *Spela reducerat →
  Filinlämning* (kräver inloggning). Schemat `atg_filebetting.xsd` ver 1.8
  (static-content.prod.c1.atg.cloud/filebet-schema/latest/) har `v85Coupon` och `v75Coupon`: åtta respektive sju
  `leg` med `marks` (startnummer 1–20 som ettor och nollor), valfria reserver `r1`/`r2`, `trackcode` (ATG:s ban-id,
  finns i spel-id:t) och upp till 9 999 kuponger per fil – vilken samling rader som helst kan alltså lämnas in. Filen
  kan skapas i webbläsaren. Första riktiga uppladdningen bör vara en liten testfil.
- **Nyttan inte visad:** de N bästa enskilda raderna (51–58 % återbetalning mot systemets 45–64 %) och reducering av
  ett 2–3 gånger större system (51–70 %) skiljer sig inte från slumpen över 262 omgångar.
- **Om det tas upp igen:** en modell för hur många andra spelare som har varje rad (utdelningen per rad, även för
  5–7 rätt, ur strecken och omsättningen), och ett mått med mindre brus än återbetalning (förväntad utdelning mot
  de verkliga poolerna i stället för de få storvinsterna).

### Spelvärde per omgång (utrett 30 oktober 2026, låg prioritet)
- Återbetalningen är fast (cirka 65 %) utom när föregående omgång saknade vinnare i högsta klassen (jackpot). Det
  hände i 8 av 78 V85-omgångar och 4 av 213 V75-omgångar. Ett mått på "veckans spelvärde" skulle bara slå ut några
  gånger per år.

## Idéer i reserven

| Idé | Varför den väntar |
|---|---|
| Inloggning och Mina spel som i Stryktipsguiden | Inte prioriterat. |
| ATG:s tipskommentar per häst i startlistan | Fritext som kräver AI-tolkning; publiceras sent i veckan. |
| Fler expertkällor (tipssajter) | Kräver AI-tolkning och mer Gemini-kvot. |
| Tillägget V7 och Boost i rättning och backtest | Ingår inte i utdelningen appen räknar på. |
| Reservhästar i rättningen | Om det efterfrågas. |
| Backtest per systemstorlek, sida vid sida (som i Stryktipsguiden) | Kan byggas när det finns fler omgångar sedan premiären. |
