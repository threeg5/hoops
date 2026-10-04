import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  claimHandedSession,
  ctClock,
  fetchMe,
  fetchMinutes,
  fetchSlate,
  login,
  points,
  record,
  TIER_LABEL,
  tpeAccountUrl,
  tpeHomeUrl,
  type FormLine,
  type Minutes,
  type Slate,
  type SlateGame,
  type TpeUser,
} from "./api";
import AdminDesk from "./Admin";
import PlayerDesk from "./PlayerDesk";
import TenPage from "./TenPage";

function dayLabel(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function nickname(name: string) {
  const parts = name.trim().split(/\s+/);
  return parts[parts.length - 1] || name;
}

function marginLabel(game: SlateGame, margin: number) {
  const leader = margin >= 0 ? game.home : game.away;
  if (margin === 0) return "Even";
  return `${leader.team} by ${Math.abs(margin).toFixed(1)}`;
}

function seasonChip(game: SlateGame) {
  if (game.season_type === "PRE") return "Preseason";
  if (game.season_type === "POST") return "Playoffs";
  return "Regular season";
}

function whenLine(game: SlateGame) {
  if (game.status === "in") return game.status_detail || `Q${game.period} ${game.clock}`;
  if (game.status === "post") return "Final";
  return [game.tip_ct, game.tip_et].filter(Boolean).join(" · ");
}

function GameCard({ game, onOpen }: { game: SlateGame; onOpen: (id: string) => void }) {
  const showScore = (game.status === "in" || game.status === "post") && game.score.away != null && game.score.home != null;
  const tags = [seasonChip(game)];
  if (game.neutral) tags.push("Neutral");
  if (game.note) tags.push(game.note);
  return (
    <button type="button" className="game-card" onClick={() => onOpen(game.game_id)}>
      <p className="kicker">{whenLine(game)}</p>
      <p className="matchup-line">
        <span>{game.away.team}</span>
        <small>@</small>
        <span>{game.home.team}</span>
      </p>
      <p className="sub">
        {nickname(game.away.name)} at {nickname(game.home.name)}
      </p>
      <p className="spot-line">
        {game.venue}
        {game.location ? ` · ${game.location}` : ""}
      </p>
      <p className="spot-line">
        Rest {game.away.rest ?? "—"}d / {game.home.rest ?? "—"}d
      </p>
      {showScore && (
        <p className="played">
          Played {game.score.away}–{game.score.home}
        </p>
      )}
      <div className="card-tags">
        {tags.map((tag) => (
          <span className="chip" key={tag}>
            {tag}
          </span>
        ))}
      </div>
    </button>
  );
}

function StatRow({
  label,
  left,
  right,
}: {
  label: string;
  left: string;
  right: string;
}) {
  return (
    <div className="stat-row">
      <b>{left}</b>
      <span>{label}</span>
      <b>{right}</b>
    </div>
  );
}

function formBits(line: FormLine | null) {
  if (!line) return { record: "—", ppg: "—", papg: "—", margin: "—" };
  return {
    record: record(line),
    ppg: points(line.ppg),
    papg: points(line.papg),
    margin: line.margin == null ? "—" : line.margin.toFixed(1),
  };
}

function MinuteLog({ game }: { game: SlateGame }) {
  const [log, setLog] = useState<Minutes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scoringOnly, setScoringOnly] = useState(false);
  const [pulledAt, setPulledAt] = useState<Date | null>(null);

  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const next = await fetchMinutes(game.game_id);
        if (stop) return;
        setLog(next);
        setPulledAt(new Date());
        setError(next.error || null);
      } catch (err) {
        if (!stop) setError(err instanceof Error ? err.message : "Play log failed");
      }
    }
    load();
    const id = window.setInterval(load, 10000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [game.game_id]);

  const plays = useMemo(() => {
    const all = log?.plays || [];
    return scoringOnly ? all.filter((play) => play.scoring) : all;
  }, [log, scoringOnly]);

  return (
    <section className="log">
      <div className="log-tools">
        <p className="kicker">Minute log</p>
        <button type="button" className={scoringOnly ? "active" : ""} onClick={() => setScoringOnly((value) => !value)}>
          {scoringOnly ? "Scoring plays" : "Every play"}
        </button>
      </div>
      <p className="sub">
        {log?.status_detail || game.status_detail || game.tip_ct}
        {log?.updated_at ? ` · last play ${ctClock(log.updated_at)}` : ""}
        {pulledAt ? ` · pulled ${ctClock(pulledAt.toISOString())}` : ""}
      </p>
      {error && <p className="error">{error}</p>}
      {!plays.length && (
        <section className="empty">
          <p>The play log fills in once ESPN has the first whistle.</p>
        </section>
      )}
      <ol>
        {plays.map((play, index) => (
          <li key={`${play.wallclock}-${index}`} className={play.scoring ? "score-play" : ""}>
            <span className="when">
              {play.period_label || (play.period ? `Q${play.period}` : "")}
              <b>{play.clock}</b>
            </span>
            <span className="play-score">
              {play.away_score}-{play.home_score}
            </span>
            <span className="play-text">{play.text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Matchup({ game, onBack }: { game: SlateGame; onBack: () => void }) {
  const away = formBits(game.away.overall);
  const home = formBits(game.home.overall);
  const expected = game.expected;
  const showScore = (game.status === "in" || game.status === "post") && game.score.away != null && game.score.home != null;
  const outs = [game.away, game.home].flatMap((side) =>
    side.out.slice(0, 4).map((player) => ({ team: side.team, ...player })),
  );

  return (
    <div className="matchup-desk">
      <header className="matchup-head">
        <button type="button" className="back" onClick={onBack}>
          ← Slate
        </button>
        <div>
          <h2>
            {game.away.team} @ {game.home.team}
          </h2>
          <p className="sub">
            {whenLine(game)}
            {game.venue ? ` · ${game.venue}` : ""}
            {game.location ? ` · ${game.location}` : ""}
            {showScore ? ` · ${game.score.away}–${game.score.home}` : ""}
            {" · "}Rest {game.away.rest ?? "—"}d / {game.home.rest ?? "—"}d
          </p>
        </div>
      </header>

      {expected && (
        <section className="expected-board">
          <p className="kicker">Expected score</p>
          <div className="expected-scores">
            <div>
              <span>{game.away.team}</span>
              <b>{expected.away_pts.toFixed(1)}</b>
            </div>
            <div className="expected-mid">
              <strong>{marginLabel(game, expected.margin)}</strong>
              <span>Total {expected.total.toFixed(1)}</span>
            </div>
            <div>
              <span>{game.home.team}</span>
              <b>{expected.home_pts.toFixed(1)}</b>
            </div>
          </div>
          {expected.recent && (
            <p className="sub">
              Last 8 games: {game.away.team} {expected.recent.away_pts.toFixed(1)}, {game.home.team}{" "}
              {expected.recent.home_pts.toFixed(1)} ({marginLabel(game, expected.recent.margin)})
            </p>
          )}
          <p className="sub">{expected.method}</p>
        </section>
      )}

      <div className="compare">
        <StatRow label="Record" left={away.record} right={home.record} />
        <StatRow label="Points" left={away.ppg} right={home.ppg} />
        <StatRow label="Allowed" left={away.papg} right={home.papg} />
        <StatRow label="Margin" left={away.margin} right={home.margin} />
        <StatRow label="Days off" left={game.away.rest_label} right={game.home.rest_label} />
      </div>

      <div className="matchup-grid">
        {[game.away, game.home].map((side) => (
          <section className="team-card" key={side.team}>
            <p className="kicker">{side === game.home ? "Home" : "Away"}</p>
            <h2>{side.team}</h2>
            <p className="team-name">{side.name}</p>
            <p className="sub">
              {side.sample}
              {side.overall ? ` · ${side.overall.games} games` : ""}
            </p>
          </section>
        ))}
      </div>

      <section className="missing-block">
        <span className="kicker">Listed out</span>
        {outs.length
          ? outs.map((player) => (
              <p key={`${player.team}-${player.name}`}>
                {player.team} {player.name}
                {player.position ? ` · ${player.position}` : ""} · {player.status}
                {player.detail ? ` · ${player.detail}` : ""}
              </p>
            ))
          : "None listed"}
      </section>

      <MinuteLog game={game} />
    </div>
  );
}

function gameFromQuery() {
  return new URLSearchParams(window.location.search).get("game");
}

type Desk = "slate" | "players" | "tenpage" | "admin";

function DeskSignIn({ onSignedIn }: { onSignedIn: (user: TpeUser) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await login({ email, password }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="desk-signin" onSubmit={onSubmit}>
      <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" autoComplete="email" required />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        autoComplete="current-password"
        required
      />
      <button type="submit" disabled={busy}>
        {busy ? "…" : "Sign in"}
      </button>
      {error && <span className="error">{error}</span>}
    </form>
  );
}

export default function App() {
  const [slate, setSlate] = useState<Slate | null>(null);
  const [day, setDay] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [gameId, setGameId] = useState<string | null>(gameFromQuery);
  const [desk, setDesk] = useState<Desk>("slate");
  const [account, setAccount] = useState<TpeUser | null>(null);
  const [pullTick, setPullTick] = useState(0);

  useEffect(() => {
    claimHandedSession();
    fetchMe().then(setAccount);
  }, []);

  useEffect(() => {
    const onPop = () => setGameId(gameFromQuery());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const next = await fetchSlate(day);
        if (stop) return;
        setSlate(next);
        setError(null);
      } catch (err) {
        if (!stop) setError(err instanceof Error ? err.message : "Slate failed");
      }
    }
    load();
    const wait = slate?.ingesting ? 3000 : 15000;
    const id = window.setInterval(load, wait);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [day, pullTick, slate?.ingesting]);

  function openGame(id: string) {
    const url = new URL(window.location.href);
    url.searchParams.set("game", id);
    window.history.pushState({}, "", url);
    setGameId(id);
  }

  function closeGame() {
    const url = new URL(window.location.href);
    url.searchParams.delete("game");
    window.history.pushState({}, "", url);
    setGameId(null);
  }

  function showSlate() {
    setDesk("slate");
    closeGame();
  }

  const open = slate?.games.find((game) => game.game_id === gameId) || null;
  const env = slate?.environment;
  const current = slate?.slate;

  return (
    <div className="shell">
      <header className="masthead">
        <div className="brand">
          <img
            src={`${import.meta.env.BASE_URL}hoops-mark.jpg`}
            alt="HOOPS logo"
            width={44}
            height={44}
          />
          <div>
            <p className="kicker">Team research desk</p>
            <h1>HOOPS</h1>
          </div>
        </div>
        <nav className="desks" aria-label="Desks">
          <a href={tpeHomeUrl()}>TPE</a>
          <button type="button" className={desk === "slate" ? "active" : ""} onClick={showSlate}>
            Tonight’s Games
          </button>
          <button type="button" className={desk === "players" ? "active" : ""} onClick={() => setDesk("players")}>
            Player Stats
          </button>
          <button type="button" className={desk === "tenpage" ? "active" : ""} onClick={() => setDesk("tenpage")}>
            TENPAGE
          </button>
          {account?.tier === "owner" && (
            <button type="button" className={desk === "admin" ? "active" : ""} onClick={() => setDesk("admin")}>
              Admin
            </button>
          )}
        </nav>
        <div className="meta">
          <p>
            {env?.league_ppg != null
              ? `League ${env.league_ppg.toFixed(1)} PPG · home court ${env.hca?.toFixed(1) ?? "—"} · ${env.games.toLocaleString()} regular-season games`
              : "Team numbers load with the first ingest."}
            {slate?.live?.pulled_at ? ` · scoreboard ${ctClock(slate.live.pulled_at)}` : ""}
          </p>
          {account ? (
            <div className="account-chip">
              <a className="account-link" href={tpeAccountUrl(account.tier === "owner" ? "admin" : "account")}>
                {account.display_name} · {TIER_LABEL[account.tier]}
              </a>
            </div>
          ) : (
            <>
              <DeskSignIn onSignedIn={setAccount} />
              <a className="account-link" href={tpeAccountUrl("signin")}>
                or create a TPE account
              </a>
            </>
          )}
        </div>
      </header>

      {error && <p className="error">{error}</p>}
      {slate?.ingesting && (
        <section className="empty">
          <h2>Loading the slate</h2>
          <p>Pulling NBA schedules and the injury report.</p>
        </section>
      )}

      {desk === "players" ? (
        <PlayerDesk />
      ) : desk === "tenpage" ? (
        <TenPage />
      ) : desk === "admin" && account ? (
        <AdminDesk viewer={account} onUser={setAccount} />
      ) : open ? (
        <Matchup game={open} onBack={closeGame} />
      ) : (
        <>
          <div className="slate-bar">
            <div>
              <p className="kicker">Tonight’s slate</p>
              <h2>{current?.label ?? "No games loaded"}</h2>
              <p className="sub">
                NBA teams. Click a game for each side’s numbers, an expected score, and the minute log.
              </p>
            </div>
            <div className="slate-tools">
              {(slate?.days.length ?? 0) > 0 && (
                <label>
                  Date
                  <select
                    value={current?.gameday ?? ""}
                    onChange={(event) => setDay(event.target.value)}
                  >
                    {slate?.days.map((item) => (
                      <option key={item.gameday} value={item.gameday}>
                        {dayLabel(item.gameday)} · {item.games} games
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <button type="button" className="text-btn" onClick={() => setPullTick((n) => n + 1)}>
                Pull results
              </button>
            </div>
          </div>
          {slate && !slate.ingesting && slate.games.length === 0 && (
            <section className="empty">
              <h2>No slate yet</h2>
              <p>No NBA games on this date.</p>
            </section>
          )}
          <div className="slate-grid">
            {(slate?.games || []).map((game) => (
              <GameCard key={game.game_id} game={game} onOpen={openGame} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
