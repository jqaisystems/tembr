// Browser-side audio utilities: decode anything the browser recorded,
// encode to 16-bit PCM WAV (the format every backend engine reads),
// and extract waveform peaks for canvas rendering.

export async function decodeBlob(blob: Blob): Promise<AudioBuffer> {
  const ctx = new AudioContext();
  try {
    return await ctx.decodeAudioData(await blob.arrayBuffer());
  } finally {
    ctx.close();
  }
}

export function audioBufferToWav(buffer: AudioBuffer): Blob {
  // Mono mixdown, 16-bit PCM
  const n = buffer.length;
  const rate = buffer.sampleRate;
  const mono = new Float32Array(n);
  for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
    const data = buffer.getChannelData(ch);
    for (let i = 0; i < n; i++) mono[i] += data[i] / buffer.numberOfChannels;
  }
  const out = new DataView(new ArrayBuffer(44 + n * 2));
  const str = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) out.setUint8(o + i, s.charCodeAt(i));
  };
  str(0, "RIFF");
  out.setUint32(4, 36 + n * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  out.setUint32(16, 16, true);
  out.setUint16(20, 1, true); // PCM
  out.setUint16(22, 1, true); // mono
  out.setUint32(24, rate, true);
  out.setUint32(28, rate * 2, true);
  out.setUint16(32, 2, true);
  out.setUint16(34, 16, true);
  str(36, "data");
  out.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) {
    const s = Math.max(-1, Math.min(1, mono[i]));
    out.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([out.buffer], { type: "audio/wav" });
}

export function peaksFromBuffer(buffer: AudioBuffer, bars: number): number[] {
  const data = buffer.getChannelData(0);
  const step = Math.floor(data.length / bars) || 1;
  const peaks: number[] = [];
  for (let b = 0; b < bars; b++) {
    let max = 0;
    const start = b * step;
    for (let i = start; i < Math.min(start + step, data.length); i += 4) {
      const v = Math.abs(data[i]);
      if (v > max) max = v;
    }
    peaks.push(max);
  }
  const top = Math.max(...peaks, 0.01);
  return peaks.map((p) => p / top);
}

export function formatTimecode(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${String(m).padStart(2, "0")}:${s.toFixed(1).padStart(4, "0")}`;
}
