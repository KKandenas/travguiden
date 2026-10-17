-- 004: Utrustning och de senaste starterna per häst (ATG /races/{id}/extended). Underlag för Hästkoll.

ALTER TABLE starter ADD COLUMN skor_fram INTEGER;        -- 1 = skor, 0 = barfota
ALTER TABLE starter ADD COLUMN skor_bak INTEGER;
ALTER TABLE starter ADD COLUMN skor_andrad INTEGER;      -- 1 = ändrat sedan förra starten
ALTER TABLE starter ADD COLUMN vagn TEXT;                -- t.ex. "Amerikansk"
ALTER TABLE starter ADD COLUMN vagn_andrad INTEGER;

ALTER TABLE avdelningar ADD COLUMN hastinfo_hamtad TEXT; -- UTC, när utrustning och tidigare starter hämtades

-- De senaste starterna före loppet (högst fem), nr 1 = den senaste.
CREATE TABLE tidigare_starter (
    start_id        INTEGER NOT NULL REFERENCES starter(id),
    nr              INTEGER NOT NULL,
    datum           TEXT NOT NULL,
    bana            TEXT,
    placering       INTEGER,                      -- 0 = oplacerad, NULL = diskad/okänd
    galopp          INTEGER NOT NULL DEFAULT 0,
    diskad          INTEGER NOT NULL DEFAULT 0,
    odds            REAL,
    km_tid          TEXT,
    distans         INTEGER,
    spar            INTEGER,
    startmetod      TEXT,
    kusk            TEXT,
    skor_fram       INTEGER,
    skor_bak        INTEGER,
    vagn            TEXT,
    kommentar       TEXT,                         -- TR Medias loppkommentar, om den finns
    PRIMARY KEY (start_id, nr)
);
