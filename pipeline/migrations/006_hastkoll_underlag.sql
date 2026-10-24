-- 006: Vilka loppkommentarer en Hästkoll-bedömning byggde på (JSON-lista med korta hashar), så att hästen
-- bedöms om när en ny kommentar tillkommer. NULL = bedömd före migreringen; fylls i utan ny bedömning.

ALTER TABLE hastkoll ADD COLUMN kommentarer TEXT;
