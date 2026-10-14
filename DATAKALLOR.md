# Datakällor

Undersökt 2026-10-14. ATG:s endpoints är **inofficiella**: det är samma JSON-API som atg.se själv anropar.
De kan ändras utan förvarning. Testerna mot sparade svar i `tests/fixtures/` visar vilka fält vi är beroende av.

## ATG

Bas-URL: `https://www.atg.se/services/racinginfo/v1/api`. Ingen nyckel krävs. `atg.se/robots.txt` spärrar inte
`/services/`. Pipelinen skickar en egen User-Agent och pausar mellan anropen vid backfill.

| Endpoint | Innehåll |
|---|---|
| `GET /products/V85` | `upcoming` (kommande omgångar) och `results` (de senaste avgjorda) |
| `GET /games/{id}` | En omgång med alla lopp och hästar, t.ex. `V85_2026-10-17_16_5`. Fungerar även för gamla. |
| `GET /calendar/day/{YYYY-MM-DD}` | Dagens spel per spelform, `games.V85[].id` |

V85 ersatte V75 den 25 oktober 2025. V75-omgångar (7 avdelningar) finns kvar i API:t bakåt i tiden.

### Spelet (`/games/{id}`)

| Fält | Exempel | Används till |
|---|---|---|
| `id` | `"V85_2026-10-17_16_5"` | `omgangar.id` (spelform, datum, bana-id, första loppnummer) |
| `status` | `bettable` / `results` | |
| `pools.V85.turnover` | `24822600` (öre) | omsättning |
| `pools.V85.timestamp` | `"2026-10-14 10:15:45"` (svensk tid) | tidpunkt för streck och odds |
| `pools.V85.result.payouts["8"]` | `{"systems": 244, "payout": 6403500}` | utdelning per rad i öre och antal vinnande rader, 5–8 rätt |
| `pools.V85.result.boostInfo.resultComplete` | `true` | omgången helt avgjord |
| `races[]` | 8 st | avdelningarna, i starttidsordning |

Per lopp (`races[i]`): `id`, `number`, `name`, `distance`, `startMethod` (`auto`/`volte`), `startTime`
(svensk tid utan tidszon), `status`, `pools.vinnare.turnover` (öre).

Per häst (`races[i].starts[j]`):

| Fält | Not |
|---|---|
| `number`, `postPosition`, `distance` | startnummer, spår, egen distans (tillägg om längre än loppets) |
| `scratched` | `true` om struken |
| `horse.name`, `.age`, `.sex`, `.money`, `.record` | `money` i kr, rekord som `{code: "aK", time: {minutes, seconds, tenths}}` |
| `horse.statistics.life` / `.years["2026"]` | starter, placeringar, intjänat. Ögonblicksbild från loppdagen, också för gamla lopp (ingen läcka). |
| `horse.statistics.lastFiveStarts.averageOdds` | snittodds × 100 |
| `driver`, `horse.trainer` | namn och `statistics.years[år].winPercentage` (× 100) |
| `pools.V85.betDistribution` | streck i hundradels procent (`914` = 9,14 %) |
| `pools.vinnare.odds` / `.finalOdds` | vinnarodds × 100. `9999` = inga odds än, `0` = struken. Högre odds anges som de är (t.ex. `30188`). |
| `result.place`, `.finalOdds`, `.kmTime` | placering (`0` = oplacerad), slutodds, km-tid |

Tidigt i veckan omsätter vinnarpoolen bara några hundra kronor per lopp, och oddsen säger ingenting. Vid start
brukar en V85-avdelning omsätta runt en miljon kronor. Pipelinen sparar därför vinnarodds först när poolen
har minst 100 000 kr (`atg.MIN_VINNARPOOL`).

## Experternas system (ATG:s tipsartiklar)

ATG:s tipsartiklar (atg.se/V85/tips) ligger i deras CMS, Contentful. Systemen i artiklarna är vanliga ATG-kuponger.

1. **Nyckel:** atg.se skickar `clientConfig.contentful = {apiUrl, deliveryToken}` i sidans HTML till alla besökare.
   Pipelinen läser den från `https://www.atg.se/V85/tips` vid varje körning och sparar den aldrig.
2. **Kupongposter:** GraphQL mot `apiUrl` (`couponCollection`, senaste 60) ger titel, `url`
   (`https://www.atg.se/spel/V85_…?couponId=<uuid>`) och vilken artikel kupongen sitter i.
3. **Namn:** artikelns `body.json` (rich text). Tipparens namn står på första raden i stycket före kupongen.
4. **Kupongen:** `GET https://api.atg.se/horse-coupons/api-public/v1/coupons/{uuid}` (ingen nyckel) ger
   `game.id`, `rows` och `races[].bets[].number` per lopp-id.

Viktigt:
- *Fem tippar V85* är en och samma artikel och samma fem kupongposter som skrivs över varje vecka. Kupongernas
  uuid är nya varje vecka.
- Kupongerna svarar **404 efter loppet**. Gamla system går alltså inte att hämta i efterhand.
- Det här är inofficiellt. Byter ATG upplägg loggas ett fel och Experterna blir samma som Oddsen tills källan anpassats.

## Spelregler som appen bygger på

- 8 avdelningar, vinnaren i varje avdelning. Utdelning för 8, 7, 6 och 5 rätt.
- Radpris 50 öre (ordinarie; ATG erbjuder också sänkt radpris på 30–70 % för små egna system, med vinsten
  sänkt i samma andel). Boost ingår inte i appens beräkningar.
- Struken häst utan angiven reserv ersätts av avdelningens mest spelade häst.
