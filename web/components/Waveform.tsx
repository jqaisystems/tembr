"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { decodeBlob, formatTimecode, peaksFromBuffer } from "@/lib/audio";

const BARS = 96;

export default function Waveform({ src, blob }: { src?: string; blob?: Blob }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const rafRef = useRef(0);
  const [peaks, setPeaks] = useState<number[]>([]);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const urlRef = useRef<string>("");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const b = blob ?? (src ? await fetch(src).then((r) => r.blob()) : null);
      if (!b || !alive) return;
      try {
        const buf = await decodeBlob(b);
        if (!alive) return;
        setPeaks(peaksFromBuffer(buf, BARS));
        setDuration(buf.duration);
      } catch {
        setPeaks(Array(BARS).fill(0.05));
      }
      urlRef.current = blob ? URL.createObjectURL(blob) : src!;
    };
    load();
    return () => {
      alive = false;
      audioRef.current?.pause();
      cancelAnimationFrame(rafRef.current);
      if (blob && urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, [src, blob]);

  const draw = useCallback(
    (prog: number) => {
      const canvas = canvasRef.current;
      if (!canvas || peaks.length === 0) return;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      const ctx = canvas.getContext("2d")!;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      // Played bars burn with the brand's ember gradient, amber cooling
      // into deep ember toward the bar tips.
      const ember = ctx.createLinearGradient(0, 0, 0, h);
      ember.addColorStop(0, "#f3a530");
      ember.addColorStop(1, "#d1622b");
      const gap = 2;
      const bw = (w - gap * (BARS - 1)) / BARS;
      peaks.forEach((p, i) => {
        const x = i * (bw + gap);
        const bh = Math.max(2, p * h * 0.9);
        ctx.fillStyle = i / BARS <= prog ? ember : "#3a352e";
        ctx.fillRect(x, (h - bh) / 2, bw, bh);
      });
    },
    [peaks]
  );

  useEffect(() => {
    draw(progress);
  }, [draw, progress]);

  const ensureAudio = (): HTMLAudioElement | null => {
    if (audioRef.current) return audioRef.current;
    if (!urlRef.current) return null;
    const a = new Audio(urlRef.current);
    audioRef.current = a;
    a.onended = () => {
      setPlaying(false);
      setProgress(0);
    };
    a.onpause = () => setPlaying(false);
    a.onplay = () => {
      setPlaying(true);
      const tick = () => {
        if (a.duration) setProgress(a.currentTime / a.duration);
        if (!a.paused) rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    };
    return a;
  };

  const toggle = () => {
    if (playing) {
      audioRef.current?.pause();
      return;
    }
    ensureAudio()?.play();
  };

  const seek = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const a = ensureAudio();
    if (!a || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const d = Number.isFinite(a.duration) && a.duration > 0 ? a.duration : duration;
    a.currentTime = frac * d;
    setProgress(frac);
    if (a.paused) a.play();
  };

  return (
    <div className="wave-well">
      <button
        type="button"
        className="play-btn"
        onClick={toggle}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? (
          <svg width="11" height="12" viewBox="0 0 11 12" aria-hidden="true">
            <rect x="0.5" width="3.6" height="12" rx="1.2" fill="currentColor" />
            <rect x="6.9" width="3.6" height="12" rx="1.2" fill="currentColor" />
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path
              d="M3.1 1.7v8.6c0 .78.86 1.26 1.53.85l7-4.3a1 1 0 0 0 0-1.7l-7-4.3A1 1 0 0 0 3.1 1.7Z"
              fill="currentColor"
            />
          </svg>
        )}
      </button>
      <canvas className="wave-canvas" ref={canvasRef} onPointerDown={seek} />
      <span className="timecode">
        {formatTimecode(progress > 0 ? progress * duration : duration)}
      </span>
    </div>
  );
}
