-- 001: Grundschema. Alla tidpunkter lagras som UTC i ISO 8601 ("2026-10-17T13:00:00Z").

CREATE TABLE omgangar (
    id              TEXT PRIMARY KEY,             -- ATG:s spel-id, t.ex. "V85_2026-10-17_16_5"
    spelform        TEXT NOT NULL,                -- V85 (eller V75 för äldre träningsdata)
    datum           TEXT NOT NULL,                -- tävlingsdagen (YYYY-MM-DD)
    bana            TEXT NOT NULL,
    spelstopp       TEXT NOT NULL,                -- första avdelningens starttid
    status          TEXT,                         -- ATG: bettable, ongoing, results …
    omsattning      REAL,                         -- kr
    avgjord         INTEGER NOT NULL DEFAULT 0    -- 1 = alla avdelningar och utdelningen klara
);

-- Utdelning per antal rätt (kr per rad à ordinarie radpris).
CREATE TABLE utdelning (
    omgang_id       TEXT NOT NULL REFERENCES omgangar(id),
    ratt            INTEGER NOT NULL,
    kr              REAL NOT NULL,
    antal           INTEGER,                      -- vinnande rader
    PRIMARY KEY (omgang_id, ratt)
);

CREATE TABLE avdelningar (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    omgang_id       TEXT NOT NULL REFERENCES omgangar(id),
    avd             INTEGER NOT NULL,             -- 1–8
    lopp_id         TEXT NOT NULL,                -- ATG:s lopp-id, t.ex. "2026-10-17_16_5"
    loppnr          INTEGER,
    namn            TEXT,
    distans         INTEGER,
    startmetod      TEXT,                         -- auto / volte
    starttid        TEXT,
    vinnare         TEXT,                         -- startnummer, kommaseparerat vid dött lopp
    UNIQUE (omgang_id, avd)
);

CREATE TABLE starter (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    avdelning_id    INTEGER NOT NULL REFERENCES avdelningar(id),
    nr              INTEGER NOT NULL,             -- startnummer
    hast_id         INTEGER,
    hast            TEXT NOT NULL,
    alder           INTEGER,
    kon             TEXT,
    kusk            TEXT,
    tranare         TEXT,
    spar            INTEGER,                      -- startspår (postPosition)
    distans         INTEGER,                      -- egen distans (tillägg om längre än loppets)
    struken         INTEGER NOT NULL DEFAULT 0,
    -- Statistik som den såg ut före loppet (ATG:s ögonblicksbild)
    livs_starter    INTEGER,
    livs_segrar     INTEGER,
    livs_platser    INTEGER,                      -- 1:a–3:e
    ar_starter      INTEGER,                      -- innevarande år
    ar_segrar       INTEGER,
    intjant         REAL,                         -- kr totalt
    rekord          TEXT,                         -- t.ex. "1.10,7aK"
    snittodds_5     REAL,                         -- snittodds senaste fem starterna
    kusk_segerproc  REAL,                         -- kuskens segerprocent i år (0–1)
    tranare_segerproc REAL,
    -- Resultat
    placering       INTEGER,                      -- 0 = oplacerad / galopp, NULL = ej avgjort
    slutodds        REAL,
    km_tid          TEXT,
    UNIQUE (avdelning_id, nr)
);

-- V85-strecken (andel 0–1), en rad per ögonblicksbild där värdet ändrats.
CREATE TABLE streck (
    start_id        INTEGER NOT NULL REFERENCES starter(id),
    tidpunkt        TEXT NOT NULL,
    andel           REAL NOT NULL CHECK (andel BETWEEN 0 AND 1),
    PRIMARY KEY (start_id, tidpunkt)
);

-- Vinnaroddsen, en rad per ögonblicksbild där värdet ändrats.
CREATE TABLE vinnarodds (
    start_id        INTEGER NOT NULL REFERENCES starter(id),
    tidpunkt        TEXT NOT NULL,
    odds            REAL NOT NULL CHECK (odds > 1),
    PRIMARY KEY (start_id, tidpunkt)
);

CREATE TABLE prognoser (
    start_id        INTEGER NOT NULL REFERENCES starter(id),
    modellversion   TEXT NOT NULL,
    chans           REAL NOT NULL,
    skapad          TEXT,
    PRIMARY KEY (start_id, modellversion)
);

CREATE TABLE installningar (
    nyckel          TEXT PRIMARY KEY,
    varde           TEXT,
    uppdaterad      TEXT
);

CREATE INDEX idx_avdelningar_omgang ON avdelningar(omgang_id);
CREATE INDEX idx_starter_avdelning ON starter(avdelning_id);
