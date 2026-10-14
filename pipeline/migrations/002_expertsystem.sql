-- 002: Experternas system (ATG-kuponger från tipsartiklarna). Kupongerna raderas hos ATG efter loppet,
-- så de sparas här när de hittas.

CREATE TABLE expertsystem (
    id              TEXT PRIMARY KEY,             -- ATG:s kupong-id (uuid)
    omgang_id       TEXT NOT NULL REFERENCES omgangar(id),
    kalla           TEXT NOT NULL,                -- "Fem tippar" eller "ATG:s experter"
    namn            TEXT NOT NULL,                -- tipparen, t.ex. "Mats E Djuse"
    artikel         TEXT,                         -- artikelns titel
    rader           INTEGER,
    hamtad          TEXT NOT NULL                 -- UTC, senast hämtad
);

CREATE TABLE expertval (
    system_id       TEXT NOT NULL REFERENCES expertsystem(id),
    avd             INTEGER NOT NULL,
    nr              INTEGER NOT NULL,             -- startnummer
    PRIMARY KEY (system_id, avd, nr)
);

CREATE INDEX idx_expertsystem_omgang ON expertsystem(omgang_id);
