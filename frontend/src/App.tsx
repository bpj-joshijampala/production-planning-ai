import { useEffect, useState } from "react";

import { fetchHealth, type HealthResponse } from "./api/health";

type ConnectionState =
  | { status: "checking" }
  | { status: "connected"; health: HealthResponse }
  | { status: "unavailable" };

const navItems = ["Upload", "Dashboard", "Machine Load", "Valves", "Recommendations", "Reports"];

function App() {
  const [connection, setConnection] = useState<ConnectionState>({ status: "checking" });

  useEffect(() => {
    let active = true;

    fetchHealth()
      .then((health) => {
        if (active) {
          setConnection({ status: "connected", health });
        }
      })
      .catch(() => {
        if (active) {
          setConnection({ status: "unavailable" });
        }
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Machine shop planning</p>
          <h1>Production Planning AI</h1>
        </div>
        <ConnectionBadge connection={connection} />
      </header>

      <nav className="primary-nav" aria-label="Primary navigation">
        {navItems.map((item) => (
          <a href="/" key={item}>
            {item}
          </a>
        ))}
      </nav>

      <section className="workspace" aria-labelledby="workspace-title">
        <div className="workspace-copy">
          <p className="eyebrow">Milestone 0</p>
          <h2 id="workspace-title">Planning cockpit foundation</h2>
          <p>
            Uploads, machine load, valve readiness, recommendations, and exports will land here as
            the backend planning spine comes online.
          </p>
        </div>

        <div className="status-strip" aria-label="Foundation status">
          <StatusItem label="Backend" value={connection.status === "connected" ? "Connected" : "Checking"} />
          <StatusItem label="Database" value="SQLite ready" />
          <StatusItem label="Planning" value="Formula tests next" />
        </div>
      </section>
    </main>
  );
}

function ConnectionBadge({ connection }: { connection: ConnectionState }) {
  if (connection.status === "connected") {
    return (
      <div className="connection connected" role="status">
        <span>Connected</span>
        <small>{connection.health.environment}</small>
      </div>
    );
  }

  if (connection.status === "unavailable") {
    return (
      <div className="connection unavailable" role="status">
        <span>Backend unavailable</span>
        <small>Start the API and refresh</small>
      </div>
    );
  }

  return (
    <div className="connection checking" role="status">
      <span>Checking backend</span>
      <small>Please wait</small>
    </div>
  );
}

function StatusItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default App;
