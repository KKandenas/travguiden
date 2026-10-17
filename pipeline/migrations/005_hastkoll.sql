-- 005: Hästkoll – AI:ns bedömning av hästens senaste lopp utifrån TR Medias loppkommentarer.
-- ATG tar bort kommentarerna inom en vecka efter loppet, så bedömningarna görs medan de finns.

CREATE TABLE hastkoll (
    start_id        INTEGER PRIMARY KEY REFERENCES starter(id),
    bedomning       INTEGER NOT NULL CHECK (bedomning IN (-1, 0, 1)),   -- +1 bättre än resultaten, −1 sämre
    motivering      TEXT,
    modell          TEXT,
    skapad          TEXT NOT NULL
);
