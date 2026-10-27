import { Command } from "cmdk";
import { Search } from "lucide-react";

export interface PaletteItem { id: string; label: string; group: string; hint?: string; keywords?: string; run: () => void }

/** Command palette (⌘K). Aksi hanya navigasi/pembuka panel; tidak ada aksi berbayar di sini. */
export function CommandPalette({ open, setOpen, items }: { open: boolean; setOpen: (v: boolean) => void; items: PaletteItem[] }) {
  const groups = [...new Set(items.map((i) => i.group))];
  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="Command palette" overlayClassName="palette-overlay" contentClassName="palette-box">
      <div className="palette-input"><Search size={16} />
        <Command.Input placeholder="Ketik perintah atau nama halaman…" /></div>
      <Command.List>
        <Command.Empty>Tidak ada perintah yang cocok.</Command.Empty>
        {groups.map((g) => (
          <Command.Group key={g} heading={g}>
            {items.filter((i) => i.group === g).map((i) => (
              <Command.Item key={i.id} value={`${i.label} ${i.keywords ?? ""}`} onSelect={() => { setOpen(false); i.run(); }}>
                <span>{i.label}</span>{i.hint && <span className="kbd">{i.hint}</span>}
              </Command.Item>
            ))}
          </Command.Group>
        ))}
      </Command.List>
    </Command.Dialog>
  );
}
