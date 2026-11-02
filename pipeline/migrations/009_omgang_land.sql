-- 009: Banans land per omgång (ATG:s countryCode: SE, NO, DK, FI …). På utländska banor saknas ofta vinnarodds och
-- TR Medias loppkommentarer (Hästkoll); appen säger det. Befintliga omgångar fylls i från hästarnas senare starter.
ALTER TABLE omgangar ADD COLUMN land TEXT;
UPDATE omgangar SET land = (
    SELECT t.land FROM tidigare_starter t
    WHERE substr(t.datum, 1, 10) = omgangar.datum AND t.bana = omgangar.bana AND t.land IS NOT NULL
    GROUP BY t.land ORDER BY COUNT(*) DESC LIMIT 1);
