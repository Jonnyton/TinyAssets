// Primitives — Button, StatusPill, DaemonTile, RitualLabel.
// Small and purely cosmetic.

function Button({ children, variant = "primary", size = "md", onClick, style = {}, disabled, ...rest }) {
  const base = {
    fontFamily: "var(--font-sans)",
    fontWeight: 600,
    borderRadius: 8,
    border: "1px solid transparent",
    cursor: disabled ? "not-allowed" : "pointer",
    transition: "all 200ms var(--ease-summon)",
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    lineHeight: 1,
    whiteSpace: "nowrap",
  };
  const sizes = {
    sm: { fontSize: 12, padding: "7px 12px" },
    md: { fontSize: 14, padding: "11px 18px" },
    lg: { fontSize: 15, padding: "14px 22px" },
  };
  const variants = {
    primary: {
      background: "var(--ember-600)",
      color: "var(--fg-on-ember)",
    },
    secondary: {
      background: "rgba(138, 99, 206, 0.14)",
      color: "var(--violet-100)",
      borderColor: "rgba(138, 99, 206, 0.42)",
    },
    ghost: {
      background: "transparent",
      color: "var(--fg-1)",
      borderColor: "var(--border-2)",
    },
    link: {
      background: "transparent",
      color: "var(--ember-600)",
      padding: 0,
      border: "none",
    },
  };
  const disabledStyle = disabled
    ? { background: "rgba(255,255,255,0.05)", color: "var(--fg-4)", borderColor: "transparent" }
    : {};
  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={{ ...base, ...sizes[size], ...variants[variant], ...disabledStyle, ...style }}
      onMouseEnter={(e) => {
        if (disabled) return;
        if (variant === "primary") {
          e.currentTarget.style.background = "var(--ember-500)";
          e.currentTarget.style.boxShadow = "var(--glow-ember)";
        } else if (variant === "secondary") {
          e.currentTarget.style.background = "rgba(138, 99, 206, 0.22)";
          e.currentTarget.style.borderColor = "rgba(138, 99, 206, 0.7)";
        } else if (variant === "ghost") {
          e.currentTarget.style.background = "rgba(255,255,255,0.04)";
          e.currentTarget.style.borderColor = "rgba(255,255,255,0.2)";
        }
      }}
      onMouseLeave={(e) => {
        if (disabled) return;
        if (variant === "primary") {
          e.currentTarget.style.background = "var(--ember-600)";
          e.currentTarget.style.boxShadow = "none";
        } else if (variant === "secondary") {
          e.currentTarget.style.background = "rgba(138, 99, 206, 0.14)";
          e.currentTarget.style.borderColor = "rgba(138, 99, 206, 0.42)";
        } else if (variant === "ghost") {
          e.currentTarget.style.background = "transparent";
          e.currentTarget.style.borderColor = "var(--border-2)";
        }
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

function StatusPill({ kind = "live", children, pulse = false }) {
  const palettes = {
    live: { bg: "rgba(109,211,166,0.1)", fg: "#8de6bf", border: "rgba(109,211,166,0.3)", dot: "#6dd3a6" },
    idle: { bg: "rgba(217,168,74,0.1)", fg: "#e6bc6c", border: "rgba(217,168,74,0.3)", dot: "#d9a84a" },
    paid: { bg: "rgba(138,99,206,0.12)", fg: "#c1aae3", border: "rgba(138,99,206,0.3)", dot: "#8a63ce" },
    self: { bg: "rgba(255,255,255,0.04)", fg: "var(--fg-2)", border: "var(--border-1)", dot: "var(--fg-3)" },
    error: { bg: "rgba(233,69,96,0.12)", fg: "#f48ba1", border: "rgba(233,69,96,0.35)", dot: "#e94560" },
  };
  const p = palettes[kind];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 11px 4px 9px",
        borderRadius: 999,
        fontFamily: "var(--font-mono)",
        fontSize: 10,
        fontWeight: 500,
        letterSpacing: "0.1em",
        textTransform: "uppercase",
        background: p.bg,
        color: p.fg,
        border: `1px solid ${p.border}`,
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: p.dot,
          boxShadow: pulse ? `0 0 8px ${p.dot}` : "none",
          animation: pulse ? "pulse 1.8s infinite ease-in-out" : "none",
        }}
      />
      {children}
    </span>
  );
}

function RitualLabel({ children, color, style = {} }) {
  return (
    <span
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        textTransform: "uppercase",
        letterSpacing: "0.14em",
        color: color || "var(--fg-3)",
        fontWeight: 500,
        ...style,
      }}
    >
      {children}
    </span>
  );
}

function SigilAvatar({ size = 40, live = false }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
        border: `1.5px solid ${live ? "var(--violet-400)" : "var(--violet-600)"}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        boxShadow: live ? "0 0 20px rgba(138,99,206,0.4)" : "none",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: size * 0.12,
          borderRadius: "50%",
          border: "1px solid var(--ember-600)",
          opacity: 0.5,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: size * 0.12,
          height: size * 0.12,
          background: "var(--ember-600)",
          borderRadius: "50%",
          boxShadow: "0 0 8px rgba(233,69,96,0.7)",
        }}
      />
    </div>
  );
}

function DaemonTile({ name, id, meta, status = "live", earnings }) {
  return (
    <div
      style={{
        background: "var(--bg-2)",
        border: "1px solid var(--border-1)",
        borderRadius: 12,
        padding: "14px 18px",
        display: "grid",
        gridTemplateColumns: "40px 1fr auto",
        gap: 16,
        alignItems: "center",
      }}
    >
      <SigilAvatar live={status === "live"} />
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg-1)" }}>{name}</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", marginTop: 3 }}>
          {id} · {meta}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <StatusPill kind={status} pulse={status === "live"}>
          {status === "live" ? "Live" : status === "idle" ? "Idle" : status}
        </StatusPill>
        {earnings && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-2)" }}>
            <strong style={{ color: "var(--fg-1)" }}>{earnings}</strong>
          </span>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { Button, StatusPill, RitualLabel, SigilAvatar, DaemonTile });
