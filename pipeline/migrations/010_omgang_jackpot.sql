-- 010: Jackpot per omgång (ATG:s pools.<spelform>.jackpotAmount, i kr): extra pengar i potten för högsta vinstgruppen,
-- t.ex. från klasser som gav 0 kr i tidigare omgångar. Visas i kupongens rubrik när beloppet är över 0.
ALTER TABLE omgangar ADD COLUMN jackpot REAL;
