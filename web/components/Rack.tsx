"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getHealth, type Health } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Generate" },
  { href: "/voices", label: "Voices" },
  { href: "/outreach", label: "Outreach" },
  { href: "/settings", label: "Settings" },
];

const SEGMENTS = 14;

function Meter({
  label,
  value,
  max,
  display,
}: {
  label: string;
  value: number;
  max: number;
  display: string;
}) {
  const lit = max > 0 ? Math.round((value / max) * SEGMENTS) : 0;
  return (
    <div className="meter-row">
      <div className="meter-label">
        <span>{label}</span>
        <b>{display}</b>
      </div>
      <div className="meter-track" role="img" aria-label={`${label} ${display}`}>
        {Array.from({ length: SEGMENTS }, (_, i) => (
          <span
            key={i}
            className={`meter-seg${i < lit ? " on" : ""}${
              i >= SEGMENTS - 4 && i < lit ? " hot" : ""
            }`}
          />
        ))}
      </div>
    </div>
  );
}

export default function Rack() {
  const pathname = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      getHealth()
        .then((h) => alive && (setHealth(h), setOffline(false)))
        .catch(() => alive && setOffline(true));
    poll();
    const t = setInterval(poll, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const vramUsed = health?.gpu
    ? health.gpu.vram_total_gb - health.gpu.vram_free_gb
    : 0;

  return (
    <aside className="rack">
      <div className="rack-brand">
        <div className="rack-eyebrow">local · private</div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="rack-logo" src="/brand/tembr-lockup-dark.svg" alt="Tembr" />
      </div>
      <nav className="rack-nav" aria-label="Main">
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`rack-link${pathname === l.href ? " active" : ""}`}
          >
            <span className="rack-dot" />
            {l.label}
          </Link>
        ))}
      </nav>
      <div className="rack-meters">
        {health?.gpu && (
          <Meter
            label="VRAM"
            value={vramUsed}
            max={health.gpu.vram_total_gb}
            display={`${vramUsed.toFixed(1)}/${health.gpu.vram_total_gb.toFixed(0)}G`}
          />
        )}
        {health && (
          <Meter
            label={`Disk ${health.disk.drive}`}
            value={health.disk.models_gb}
            max={Math.max(health.disk.models_gb + health.disk.free_gb, 1)}
            display={`${health.disk.models_gb.toFixed(1)}G models`}
          />
        )}
        <div className={`rack-status${offline ? " offline" : ""}`}>
          <span className="rack-dot" />
          {offline ? "ENGINE OFFLINE" : `ENGINE READY${health?.cuda_available ? " · CUDA" : ""}`}
        </div>
      </div>
    </aside>
  );
}
