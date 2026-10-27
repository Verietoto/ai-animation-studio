// Penggambar panel komik (plan 21): gambar + balon ke <canvas>. Dipakai untuk tampilan DAN unduh PNG, jadi hasil unduhan = yang dilihat.
import type { Bubble } from "../api";

// ponytail: font sistem bergaya komik, tanpa Google Fonts; canvas tidak perlu menunggu font web dimuat
export const COMIC_FONT = `"Comic Sans MS", "Comic Neue", "Chalkboard SE", "Marker Felt", cursive`;

function wrap(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const out: string[] = [];
  for (const para of text.split("\n")) {
    let line = "";
    for (const word of para.split(/\s+/).filter(Boolean)) {
      const next = line ? `${line} ${word}` : word;
      if (ctx.measureText(next).width <= maxW || !line) line = next;
      else { out.push(line); line = word; }
    }
    out.push(line);
  }
  return out;
}

/** Ukuran huruf terbesar yang muat di kotak (turun bertahap); mengembalikan baris dan ukurannya. */
function fit(ctx: CanvasRenderingContext2D, text: string, w: number, h: number, weight: string, scale: number) {
  for (let size = Math.max(10 * scale, h * 0.5); size >= 8 * scale; size *= 0.92) {
    ctx.font = `${weight} ${size}px ${COMIC_FONT}`;
    const lines = wrap(ctx, text, w);
    if (lines.length * size * 1.15 <= h && lines.every((l) => ctx.measureText(l).width <= w)) return { lines, size };
  }
  const size = 8 * scale;
  ctx.font = `${weight} ${size}px ${COMIC_FONT}`;
  return { lines: wrap(ctx, text, w), size };
}

function drawText(ctx: CanvasRenderingContext2D, lines: string[], size: number, cx: number, cy: number, stroke = false) {
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const top = cy - ((lines.length - 1) * size * 1.15) / 2;
  lines.forEach((l, i) => {
    if (stroke) ctx.strokeText(l, cx, top + i * size * 1.15);
    ctx.fillText(l, cx, top + i * size * 1.15);
  });
}

export function drawBubble(ctx: CanvasRenderingContext2D, b: Bubble, W: number, H: number) {
  const x = b.x * W, y = b.y * H, w = b.w * W, h = b.h * H;
  const cx = x + w / 2, cy = y + h / 2, rx = w / 2, ry = h / 2;
  const scale = Math.max(W, H) / 1000;
  ctx.save();
  ctx.lineWidth = Math.max(1.5, 2.5 * scale);
  ctx.strokeStyle = "#111";
  ctx.lineJoin = "round";
  if (b.kind === "sfx") {
    const { lines, size } = fit(ctx, b.text, w, h, "900", scale);
    ctx.translate(cx, cy);
    ctx.rotate(-0.12);
    ctx.lineWidth = Math.max(3, size * 0.14);
    ctx.fillStyle = "#ffd23f";
    drawText(ctx, lines, size, 0, 0, true);
    ctx.restore();
    return;
  }
  if (b.kind === "caption") {
    ctx.fillStyle = "#fff6c9";
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
  } else {
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (b.tail_x != null && b.tail_y != null) {
      const tx = b.tail_x * W, ty = b.tail_y * H;
      if (b.kind === "thought") {   // ekor pikiran: tiga lingkaran mengecil ke arah pembicara
        for (let i = 1; i <= 3; i++) {
          const t = i / 3.4, r = Math.max(3, Math.min(rx, ry) * (0.22 - i * 0.05));
          ctx.beginPath();
          ctx.arc(cx + (tx - cx) * (0.5 + t * 0.5), cy + (ty - cy) * (0.5 + t * 0.5), r, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        }
      } else {   // ekor bicara: segitiga dari tepi elips; isinya menutup garis elips di pangkal
        const a = Math.atan2((ty - cy) / ry, (tx - cx) / rx), d = 0.22;
        const p1 = [cx + rx * Math.cos(a - d), cy + ry * Math.sin(a - d)], p2 = [cx + rx * Math.cos(a + d), cy + ry * Math.sin(a + d)];
        ctx.beginPath();
        ctx.moveTo(p1[0], p1[1]); ctx.lineTo(tx, ty); ctx.lineTo(p2[0], p2[1]);
        ctx.closePath();
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(p1[0], p1[1]); ctx.lineTo(tx, ty); ctx.lineTo(p2[0], p2[1]);
        ctx.stroke();
      }
    }
  }
  // kotak teks: elips memakai ~70% lebar/tinggi supaya teks tidak menyentuh tepi
  const weight = b.kind === "caption" ? "600" : "700";
  const inset = b.kind === "caption" ? [w - 12 * scale, h - 10 * scale] : [w * 0.7, h * 0.66];
  const { lines, size } = fit(ctx, b.text, inset[0], inset[1], weight, scale);
  ctx.fillStyle = "#111";
  ctx.font = `${weight} ${size}px ${COMIC_FONT}`;
  drawText(ctx, lines, size, cx, cy);
  ctx.restore();
}

/** Gambar panel lengkap. `img` null = latar abu-abu (balon bisa diatur sebelum gambar dibuat). */
export function drawPanel(canvas: HTMLCanvasElement, img: HTMLImageElement | null, bubbles: Bubble[], fallback: [number, number]) {
  const [W, H] = img ? [img.naturalWidth, img.naturalHeight] : fallback;
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d")!;
  if (img) ctx.drawImage(img, 0, 0, W, H);
  else { ctx.fillStyle = "#2a2d3a"; ctx.fillRect(0, 0, W, H); }
  ctx.lineWidth = Math.max(4, W / 200);
  ctx.strokeStyle = "#111";
  ctx.strokeRect(0, 0, W, H);   // bingkai panel
  for (const b of bubbles) drawBubble(ctx, b, W, H);
}
