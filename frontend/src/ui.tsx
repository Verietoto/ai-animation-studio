import { ReactNode, useState } from "react";
import { createPortal } from "react-dom";
import { SlidersHorizontal, X } from "lucide-react";

/** Kanvas di kiri, inspector di kanan; di bawah 1024px inspector menjadi drawer. */
export function Stage({ canvas, inspector }: { canvas: ReactNode; inspector: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="stage">
      <div className="canvas">{canvas}</div>
      <aside className={`inspector ${open ? "open" : ""}`}>
        <button className="btn ghost sm" style={{ alignSelf: "flex-end", display: open ? "inline-flex" : "none" }}
          onClick={() => setOpen(false)} aria-label="Tutup panel"><X size={16} /></button>
        {inspector}
      </aside>
      <button className="btn primary inspector-toggle" onClick={() => setOpen(true)}>
        <SlidersHorizontal size={16} /> Pengaturan
      </button>
    </div>
  );
}

/** Modal harus keluar dari inspector: backdrop-filter membuat position:fixed terkurung di induknya. */
export const Portal = ({ children }: { children: ReactNode }) => createPortal(children, document.body);

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="section"><h3>{title}</h3>{children}</section>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field">{label}{children}</label>;
}

export function EmptyState({ icon, title, hint, children }: { icon: ReactNode; title: string; hint?: string; children?: ReactNode }) {
  return (
    <div className="empty">
      {icon}
      <strong style={{ color: "var(--text)" }}>{title}</strong>
      {hint && <span className="muted">{hint}</span>}
      {children}
    </div>
  );
}
