import { useEffect, useState } from "react";
import { fetchPlayers, type League, type ListedPlayer } from "./api";

export default function PlayerDesk({ league }: { league: League }) {
  const [query, setQuery] = useState("");
  const [players, setPlayers] = useState<ListedPlayer[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      fetchPlayers(query, league)
        .then((data) => {
          setPlayers(data.players);
          setError(null);
        })
        .catch((err) => setError(err instanceof Error ? err.message : "Player list failed"));
    }, 200);
    return () => window.clearTimeout(handle);
  }, [query, league]);

  return (
    <section className="admin-desk">
      <div className="admin-head">
        <p className="kicker">Player stats</p>
        <h2>{league === "wnba" ? "WNBA injury report" : "Injury report"}</h2>
        <p className="lede">
          The ESPN injury report for every {league === "wnba" ? "WNBA" : "NBA"} team. Search a name or a club. Season averages are not on this desk yet.
        </p>
      </div>
      <label className="admin-search">
        Search
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name or team" />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Team</th>
              <th>Pos</th>
              <th>Status</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {players.map((player) => (
              <tr key={`${player.abbr}-${player.player_name}`}>
                <td>{player.player_name}</td>
                <td>
                  {player.abbr}
                  <small>{player.team_name}</small>
                </td>
                <td>{player.position || "—"}</td>
                <td>{player.status || "—"}</td>
                <td>{player.detail || player.comment || "—"}</td>
              </tr>
            ))}
            {!players.length && (
              <tr>
                <td colSpan={5}>No players match.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
