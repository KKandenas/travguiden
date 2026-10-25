-- 007: Hästkoll sparar varje bedömning (historik) och faktorerna bakom den per tidigare start, så att det
-- senare går att räkna ut vilken information i loppkommentarerna som faktiskt förutsäger nästa lopp.

ALTER TABLE hastkoll ADD COLUMN version TEXT NOT NULL DEFAULT 'hastkoll-1';   -- instruktionen till AI:n

CREATE TABLE hastkoll_historik (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    start_id        INTEGER NOT NULL REFERENCES starter(id),
    bedomning       INTEGER NOT NULL CHECK (bedomning IN (-1, 0, 1)),
    motivering      TEXT,
    modell          TEXT,
    version         TEXT NOT NULL,
    skapad          TEXT NOT NULL,
    kommentarer     TEXT,                         -- avtryck av kommentarerna (som hastkoll.kommentarer)
    streck          REAL,                         -- strecken och Oddsens chans när bedömningen gjordes
    chans           REAL
);
CREATE INDEX idx_hastkoll_historik_start ON hastkoll_historik(start_id);

-- Faktorer per tidigare start (bara starter med kommentar). Värden: se pipeline/ai/hastkoll.py (FAKTORER).
CREATE TABLE hastkoll_faktorer (
    historik_id     INTEGER NOT NULL REFERENCES hastkoll_historik(id),
    start_datum     TEXT NOT NULL,                -- den tidigare startens datum
    lage            TEXT,
    storning        TEXT,
    avslutning      TEXT,
    tempo           TEXT,
    bedomning       INTEGER CHECK (bedomning IN (-1, 0, 1)),   -- just den starten: bättre/som/sämre än placeringen
    PRIMARY KEY (historik_id, start_datum)
);

-- Bedömningarna som redan finns blir den första posten i historiken (utan faktorer).
INSERT INTO hastkoll_historik (start_id, bedomning, motivering, modell, version, skapad, kommentarer)
    SELECT start_id, bedomning, motivering, modell, version, skapad, kommentarer FROM hastkoll;
