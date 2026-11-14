// Small helpers for calling the engine's API and formatting numbers in plain language.

export async function api(path, body) {
  const res = await fetch(`/api${path}`, body === undefined ? undefined : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

const nf = new Intl.NumberFormat("en-GB");
export const num = (v, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "–"
    : new Intl.NumberFormat("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);
export const eur = (v) => (v === null || v === undefined ? "–" : `€${nf.format(Math.round(v))}`);
export const pct = (v, digits = 1) => (v === null || v === undefined ? "–" : `${num(v, digits)}%`);
export const words = (s) => (s ? String(s).replaceAll("_", " ") : "");
