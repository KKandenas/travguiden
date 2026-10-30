-- 008: Underlag för klassbyte och fartindex: förstapriset i hästens tidigare lopp och i dagens lopp, banans
-- underlag och land för tidigare starter.

ALTER TABLE tidigare_starter ADD COLUMN forstapris REAL;     -- kr
ALTER TABLE tidigare_starter ADD COLUMN underlag TEXT;       -- ATG: light, good, dead, heavy, winter …
ALTER TABLE tidigare_starter ADD COLUMN land TEXT;           -- SE, NO, FR …
ALTER TABLE avdelningar ADD COLUMN forstapris REAL;          -- kr, ur loppets prissträng
