import { useEffect, useState } from "react";
import { api, Img } from "./api";
import { useAsync } from "./components";
import Generate from "./pages/Generate";
import EditPage from "./pages/EditPage";
import Library from "./pages/Library";

type Tab = "generate" | "edit" | "library";

export default function App() {
  const [tab, setTab] = useState<Tab>("generate");
  const [selected, setSelected] = useState<string | null>(null);
  const health = useAsync(api.health, []);
  useEffect(() => { api.health().then(health.setData).catch(() => {}); }, [tab]); // biaya hari ini tetap segar
  const images = useAsync(api.images, []);
  const list: Img[] = images.data ?? [];
  const addImage = (img: Img) => images.setData([img, ...list.filter((i) => i.id !== img.id)]);
  const refreshImages = () => api.images().then(images.setData);

  return (
    <div className="app">
      <header>
        <h1>AI Animation Studio</h1>
        <nav>
          {(["generate", "edit", "library"] as Tab[]).map((t) => (
            <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>
              {{ generate: "Gambar → Video", edit: "Edit Foto", library: "Library & Extend" }[t]}
            </button>
          ))}
        </nav>
        {health.data && (
          <span className="muted">
            ${health.data.spent_today.toFixed(2)} / ${health.data.daily_budget.toFixed(2)} hari ini
          </span>
        )}
      </header>
      {health.data && !health.data.api_key && <p className="error banner">OPENROUTER_API_KEY belum diatur di server.</p>}
      {health.data && !health.data.ffmpeg && <p className="error banner">ffmpeg/ffprobe tidak ditemukan; extend dan gabung klip tidak akan jalan.</p>}
      <main>
        {tab === "generate" && <Generate images={list} selected={selected} setSelected={setSelected}
          addImage={addImage} onCreated={() => setTab("library")} />}
        {tab === "edit" && <EditPage images={list} selected={selected} setSelected={setSelected}
          addImage={addImage} refresh={refreshImages} toVideo={(id) => { setSelected(id); setTab("generate"); }} />}
        {tab === "library" && <Library refreshImages={refreshImages} />}
      </main>
    </div>
  );
}
