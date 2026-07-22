// TopNav.jsx — sticky-translucent nav. Active tab gets ember underline.

function TopNav({ current, onNavigate }) {
  const items = [
    { id: "landing", label: "Home" },
    { id: "connect", label: "Connect" },
    { id: "catalog", label: "Catalog" },
    { id: "host", label: "Host" },
    { id: "contribute", label: "Contribute" },
    { id: "teams", label: "Agent Teams" },
    { id: "showcase", label: "Novel" },
    { id: "coding", label: "Coding" },
    { id: "economy", label: "Economy" },
  ];

  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        background: "rgba(14,14,26,0.72)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--border-1)",
      }}
    >
      <div
        style={{
          maxWidth: 1240,
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 32px",
        }}
      >
        <button
          onClick={() => onNavigate("landing")}
          style={{ display: "flex", alignItems: "center", gap: 10, background: "none", border: "none", cursor: "pointer" }}
        >
          <SigilMark size={28} />
          <span style={{ fontFamily: "var(--font-display)", fontSize: 18, fontWeight: 600, letterSpacing: "-0.01em", color: "var(--fg-1)" }}>
            Workflow
          </span>
        </button>

        <nav style={{ display: "flex", gap: 2 }}>
          {items.map((it) => {
            const active = current === it.id;
            return (
              <button
                key={it.id}
                onClick={() => onNavigate(it.id)}
                style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: 13,
                  fontWeight: 500,
                  color: active ? "var(--ember-600)" : "var(--fg-2)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  padding: "8px 14px",
                  borderRadius: 6,
                  position: "relative",
                  transition: "color 160ms",
                }}
                onMouseEnter={(e) => { if (!active) e.currentTarget.style.color = "var(--fg-1)"; }}
                onMouseLeave={(e) => { if (!active) e.currentTarget.style.color = "var(--fg-2)"; }}
              >
                {it.label}
                {active && (
                  <span
                    style={{
                      position: "absolute",
                      left: 14,
                      right: 14,
                      bottom: 2,
                      height: 1,
                      background: "var(--ember-600)",
                    }}
                  />
                )}
              </button>
            );
          })}
        </nav>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Button variant="ghost" size="sm">Sign in</Button>
          <Button variant="primary" size="sm" onClick={() => onNavigate("host")}>
            Summon a daemon <span style={{ fontFamily: "var(--font-mono)", opacity: 0.7 }}>→</span>
          </Button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { TopNav });
