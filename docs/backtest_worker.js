// Räknar backtestet för alla förslag och insatser i en egen tråd, så att sidan inte fryser (app.js → perInsatsRuta).
import { backtestaAlla } from "./backtest.js?v=20261030e";
import { BUDGETAR } from "./optimizer.js?v=20261030e";

self.onmessage = (e) => {
  let senast = 0;
  const res = backtestaAlla(e.data.historik, BUDGETAR, undefined, (f) => {
    if (f - senast >= 0.02 || f === 1) { senast = f; self.postMessage({ framsteg: f }); }
  });
  self.postMessage({ klar: res });
};
