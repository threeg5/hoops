import { useEffect, useState } from "react";
import { fetchSlate, type SlateGame } from "./api";

function margin(game: SlateGame) {
  if (!game.expected) return "—";
  const leader = game.expected.margin >= 0 ? game.home.team : game.away.team;
  if (game.expected.margin === 0) return "Even";
  return `${leader} by ${Math.abs(game.expected.margin).toFixed(1)}`;
}

export default function TenPage() {
  const [games, setGames] = useState<SlateGame[]>([]);
  const [label, setLabel] = useState("Tonight");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSlate()
      .then((slate) => {
        setGames(slate.games);
        setLabel(slate.slate?.label ?? "Tonight");
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "TENPAGE failed"));
  }, []);

  return (
    <section className="admin-desk">
      <div className="admin-head">
        <p className="kicker">TENPAGE</p>
        <h2>{label}</h2>
        <p className="lede">
          Expected score for each NBA game on the slate. This is the HOOPS number. It is not a settled wager.
        </p>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Game</th>
              <th>When</th>
              <th>Away</th>
              <th>Home</th>
              <th>Total</th>
              <th>Margin</th>
            </tr>
          </thead>
          <tbody>
            {games.map((game) => (
              <tr key={game.game_id}>
                <td>
                  {game.away.team} @ {game.home.team}
                </td>
                <td>{game.status === "post" ? "Final" : game.tip_ct}</td>
                <td>{game.expected ? game.expected.away_pts.toFixed(1) : "—"}</td>
                <td>{game.expected ? game.expected.home_pts.toFixed(1) : "—"}</td>
                <td>{game.expected ? game.expected.total.toFixed(1) : "—"}</td>
                <td>{margin(game)}</td>
              </tr>
            ))}
            {!games.length && (
              <tr>
                <td colSpan={6}>No games on the slate.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
