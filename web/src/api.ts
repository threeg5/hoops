const API = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8003").replace(/\/$/, "");

export type FormLine = {
  games: number;
  wins: number;
  losses: number;
  ppg: number | null;
  papg: number | null;
  margin: number | null;
};

export type OutPlayer = {
  name: string;
  position: string;
  status: string;
  detail: string;
};

export type Side = {
  team: string;
  name: string;
  color: string | null;
  rest: number | null;
  rest_label: string;
  overall: FormLine | null;
  recent: FormLine | null;
  sample: string;
  out: OutPlayer[];
};

export type Expected = {
  away_pts: number;
  home_pts: number;
  total: number;
  margin: number;
  hca: number;
  league_ppg: number | null;
  recent: {
    away_pts: number;
    home_pts: number;
    total: number;
    margin: number;
  } | null;
  method: string;
};

export type SlateGame = {
  game_id: string;
  gameday: string;
  start_utc: string | null;
  tip_ct: string;
  tip_et: string;
  season_label: string;
  season_type: string;
  status: "pre" | "in" | "post" | string;
  status_detail: string;
  period: number;
  clock: string;
  neutral: boolean;
  venue: string;
  location: string;
  note: string;
  away: Side;
  home: Side;
  score: { away: number | null; home: number | null };
  expected: Expected | null;
};

export type Slate = {
  slate: { gameday: string; label: string; games: number; is_today: boolean } | null;
  days: { gameday: string; games: number; finals: number }[];
  environment: { league_ppg: number | null; hca: number | null; games: number };
  live: { source?: string; pulled_at?: string | null; error?: string; cached?: boolean };
  games: SlateGame[];
  ingesting?: boolean;
};

export type Play = {
  period: number | null;
  period_label: string;
  clock: string;
  text: string;
  away_score: number | null;
  home_score: number | null;
  scoring: boolean;
  wallclock: string | null;
};

export type Minutes = {
  game_id: string;
  source?: string;
  updated_at?: string | null;
  state?: string | null;
  status_detail?: string;
  plays: Play[];
  error?: string;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export type League = "nba" | "wnba";

function leagueQuery(league: League = "nba", extra?: Record<string, string>) {
  const params = new URLSearchParams(extra);
  if (league !== "nba") params.set("league", league);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function fetchSlate(date?: string, league: League = "nba") {
  const extra: Record<string, string> = {};
  if (date) extra.date = date;
  return getJson<Slate>(`/api/slate${leagueQuery(league, extra)}`);
}

export function fetchMinutes(gameId: string, league: League = "nba") {
  return getJson<Minutes>(`/api/games/${gameId}/minutes${leagueQuery(league)}`);
}

export function ctClock(iso?: string | null) {
  if (!iso) return "";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Chicago",
    timeZoneName: "short",
  }).format(dt);
}

export function record(line: FormLine | null) {
  if (!line) return "—";
  return `${line.wins}-${line.losses}`;
}

export function points(value: number | null | undefined) {
  if (value == null) return "—";
  return value.toFixed(1);
}

export type ListedPlayer = {
  player_name: string;
  position: string | null;
  status: string | null;
  detail: string | null;
  comment: string | null;
  abbr: string;
  team_name: string;
};

export function fetchPlayers(q = "", league: League = "nba") {
  const extra: Record<string, string> = {};
  if (q.trim()) extra.q = q.trim();
  return getJson<{ players: ListedPlayer[] }>(`/api/players${leagueQuery(league, extra)}`);
}

const TPE_API = (
  import.meta.env.DEV
    ? "/tpe-api"
    : (import.meta.env.VITE_TPE_API_URL ?? "https://wagechecker-api.onrender.com")
).replace(/\/$/, "");

export type Tier = "amateur" | "player" | "owner";

export const TIER_LABEL: Record<Tier, string> = {
  amateur: "Amateur",
  player: "Player",
  owner: "Owner",
};

export type TpeUser = {
  id: string;
  email: string;
  display_name: string;
  tier: Tier;
  last_desk: string | null;
  created_at: string;
};

export type AdminUser = TpeUser & { updated_at?: string | null };

export type AdminRoster = {
  users: AdminUser[];
  counts: Record<string, number>;
  total: number;
};

const SESSION_KEY = "tpe_session";
const SESSION_MAX_AGE = 30 * 24 * 60 * 60;
const TPE_HOME = import.meta.env.DEV ? "http://127.0.0.1:5175" : "https://theprofitengineer.com";

export function tpeHomeUrl() {
  return TPE_HOME;
}

export function tpeAccountUrl(hash: "signin" | "account" | "book" | "admin" = "account") {
  return `${TPE_HOME}/#${hash}`;
}

function readCookie(name: string) {
  const prefix = `${name}=`;
  for (const part of document.cookie.split("; ")) {
    if (part.startsWith(prefix)) return decodeURIComponent(part.slice(prefix.length));
  }
  return null;
}

export function readSessionToken() {
  return localStorage.getItem(SESSION_KEY) || readCookie(SESSION_KEY);
}

export function writeSessionToken(token: string | null) {
  if (token) {
    localStorage.setItem(SESSION_KEY, token);
    document.cookie = `${SESSION_KEY}=${encodeURIComponent(token)}; Path=/; Max-Age=${SESSION_MAX_AGE}; SameSite=Lax`;
  } else {
    localStorage.removeItem(SESSION_KEY);
    document.cookie = `${SESSION_KEY}=; Path=/; Max-Age=0; SameSite=Lax`;
  }
}

async function authError(res: Response) {
  const text = await res.text();
  try {
    const data = JSON.parse(text) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* use the raw text */
  }
  return text || res.statusText;
}

async function authJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = readSessionToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${TPE_API}${path}`, { ...init, headers });
  if (!res.ok) {
    if (res.status === 401) writeSessionToken(null);
    throw new Error(await authError(res));
  }
  return res.json() as Promise<T>;
}

export function claimHandedSession() {
  const params = new URLSearchParams(window.location.search);
  const handed = params.get("tpe");
  if (!handed) return;
  writeSessionToken(handed);
  params.delete("tpe");
  const search = params.toString();
  history.replaceState(null, "", `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`);
}

export async function login(input: { email: string; password: string }) {
  const data = await authJson<{ token: string; user: TpeUser }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
  writeSessionToken(data.token);
  return data.user;
}

export async function fetchMe() {
  if (!readSessionToken()) return null;
  try {
    return await authJson<TpeUser>("/api/auth/me");
  } catch {
    return null;
  }
}

export function fetchAdminUsers() {
  return authJson<AdminRoster>("/api/admin/users");
}

export function patchAdminUser(userId: string, input: { displayName?: string; tier?: Tier }) {
  return authJson<AdminUser>(`/api/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

