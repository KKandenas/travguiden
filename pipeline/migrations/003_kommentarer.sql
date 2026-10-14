-- 003: AI-kommentarer per avdelning.

CREATE TABLE kommentarer (
    omgang_id       TEXT NOT NULL REFERENCES omgangar(id),
    avd             INTEGER NOT NULL,
    text            TEXT NOT NULL,
    grund_hash      TEXT NOT NULL,                -- startande hästar och antal expertsystem
    underlag_hash   TEXT NOT NULL,                -- allt AI:n fick se
    modell          TEXT,
    skapad          TEXT NOT NULL,
    PRIMARY KEY (omgang_id, avd)
);
