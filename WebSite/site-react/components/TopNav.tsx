"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { WorkflowMark } from "./WorkflowMark";
import styles from "./TopNav.module.css";

const items = [
  { href: "/start", label: "start" },
  { href: "/goals", label: "goals" },
  { href: "/loop", label: "loop" },
  { href: "/commons", label: "commons" },
  { href: "/graph", label: "graph" },
  { href: "/soul", label: "soul" },
  { href: "/build", label: "build" },
];

function isActive(path: string, href: string): boolean {
  if (href === "/") return path === "/";
  return path === href || path.startsWith(href + "/");
}

export function TopNav() {
  const pathname = usePathname() ?? "/";
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const close = () => setDrawerOpen(false);

  return (
    <>
      <header className={styles.top}>
        <div className={`container ${styles.row}`}>
          <Link className={styles.brand} href="/" aria-label="Tiny — home" onClick={close}>
            <WorkflowMark size={26} />
            <span className={styles.brandName}>Tiny</span>
            <span className={`${styles.brandSub} ev`}>tinyassets.io</span>
          </Link>
          <nav className={styles.nav} aria-label="Primary">
            {items.map((it) => (
              <Link
                key={it.href}
                href={it.href}
                className={`${styles.item}${isActive(pathname, it.href) ? " " + styles.active : ""}`}
              >
                <span className={styles.label}>{it.label}</span>
              </Link>
            ))}
          </nav>
          <button
            className={`${styles.hamburger}${drawerOpen ? " " + styles.open : ""}`}
            aria-label={drawerOpen ? "Close menu" : "Open menu"}
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen((v) => !v)}
          >
            <span /><span /><span />
          </button>
        </div>
      </header>

      {drawerOpen && (
        <div className={styles.drawer} role="dialog" aria-label="Site navigation">
          <nav aria-label="Mobile primary">
            <Link href="/" className={`${styles.drawerItem}${isActive(pathname, "/") ? " " + styles.active : ""}`} onClick={close}>
              <strong>home</strong>
            </Link>
            {items.map((it) => (
              <Link
                key={it.href}
                href={it.href}
                className={`${styles.drawerItem}${isActive(pathname, it.href) ? " " + styles.active : ""}`}
                onClick={close}
              >
                <strong>{it.label}</strong>
              </Link>
            ))}
          </nav>
        </div>
      )}
    </>
  );
}

export default TopNav;
