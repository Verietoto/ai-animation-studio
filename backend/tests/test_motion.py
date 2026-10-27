"""Plan 09: frame akhir di Gambar->Video dan backend tiru gerakan (plan 03) lewat API."""
import json

from conftest import make_video, png_bytes, upload

VIDEO = {"model": "bytedance/seedance-2.5", "prompt": "adegan", "duration": 4, "resolution": "720p", "aspect_ratio": "16:9"}
FLUX = "black-forest-labs/flux-video-edit"
ALEPH = "runway/aleph-2"


def hdr(ws):
    return {"headers": {"X-Workspace-Id": ws}}


def mkws(api, name="Kedua"):
    return api.post("/api/workspaces", json={"name": name}).json()["id"]


def up(api, ws="main"):
    r = api.post("/api/images", files={"file": ("a.png", png_bytes(), "image/png")}, **hdr(ws))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def ref_from_clip(api, ws="main"):
    clip = api.post("/api/clips", json={**VIDEO, "image_id": up(api, ws)}, **hdr(ws)).json()
    api.studio.poll_once()
    r = api.post(f"/api/references/from-clip/{clip['id']}", **hdr(ws))
    assert r.status_code == 200, r.text
    return r.json()


def confirmed(api, est_body, ws="main"):
    r = api.raw.post("/api/estimate", json=est_body, **hdr(ws))
    assert r.status_code == 200, r.text
    return {"confirmed_cost": r.json()["high"]}


# ---------- frame akhir ----------
def test_last_frame_is_sent_and_exposed(api, fake):
    first, last = up(api), up(api)
    r = api.post("/api/clips", json={**VIDEO, "image_id": first, "last_image_id": last})
    assert r.status_code == 200, r.text
    frames = fake.last_json("/videos")["frame_images"]
    assert [f["frame_type"] for f in frames] == ["first_frame", "last_frame"]
    assert "last_image_id" not in fake.last_json("/videos")
    assert r.json()["last_image_id"] == last
    assert api.get("/api/clips").json()[0]["last_image_id"] == last
    plain = api.post("/api/clips", json={**VIDEO, "image_id": first}).json()
    assert plain["last_image_id"] is None


def test_last_frame_rejected_for_model_without_support(api, fake):
    first, last = up(api), up(api)
    r = api.post("/api/clips", json={"model": "x/no-audio", "prompt": "p", "duration": 4,
                                     "image_id": first, "last_image_id": last})
    assert r.status_code == 400 and "frame akhir" in r.json()["detail"]
    assert fake.submit_count == 0


def test_last_frame_from_other_workspace_is_404(api, fake):
    other = up(api, mkws(api))
    r = api.post("/api/clips", json={**VIDEO, "image_id": up(api), "last_image_id": other})
    assert r.status_code == 404
    assert fake.submit_count == 0


# ---------- tiru gerakan ----------
def test_health_reports_public_media(api):
    assert api.get("/api/health").json()["public_media"] is False


def test_flux_edit_from_clip_in_second_workspace(api, fake):
    """Grill 09 bug 1: estimate di dalam create dulu tidak menerima ws -> 404 di workspace selain main."""
    ws = mkws(api)
    ref = ref_from_clip(api, ws)
    src = up(api, ws)
    ch = api.post("/api/characters", json={"name": "Rina", "description": "short black bob, red jacket",
                                           "source_image_id": src}, **hdr(ws)).json()
    body = {"mode": "flux_edit", "model": FLUX, "reference_id": ref["id"], "prompt": "replace the person",
            "character_id": ch["id"]}
    conf = confirmed(api, {"kind": "motion", "mode": "flux_edit", "model": FLUX, "reference_id": ref["id"]}, ws)
    r = api.raw.post("/api/motion", json={**body, **conf}, **hdr(ws))
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "motion" and r.json()["workspace_id"] == ws
    sent = fake.last_json("/videos")
    assert sent["input_references"] == [{"type": "video_url", "video_url": {"url": "https://or.test/signed/job1.mp4"}}]
    assert "short black bob" in sent["prompt"] and "frame_images" not in sent


def test_motion_requires_confirmation(api, fake):
    ref = ref_from_clip(api)
    before = fake.submit_count
    r = api.raw.post("/api/motion", json={"mode": "flux_edit", "model": FLUX, "reference_id": ref["id"], "prompt": "p"})
    assert r.status_code == 409
    assert fake.submit_count == before


def test_uploaded_reference_without_public_storage_is_501(api, fake, tmp_path):
    vid = make_video(tmp_path / "ref.mp4", seconds=1)
    r = api.post("/api/references", files={"file": ("ref.mp4", vid.read_bytes(), "video/mp4")})
    assert r.status_code == 200, r.text
    ref = r.json()
    conf = confirmed(api, {"kind": "motion", "mode": "flux_edit", "model": FLUX, "reference_id": ref["id"]})
    r = api.raw.post("/api/motion", json={"mode": "flux_edit", "model": FLUX, "reference_id": ref["id"],
                                          "prompt": "p", **conf})
    assert r.status_code == 501
    assert fake.submit_count == 0


def test_anchor_estimate_matches_generate_for_character_without_sheet(api, fake):
    """Grill 09 bug 3: estimasi anchor dulu selalu 3 input; karakter tanpa sheet mengirim 2 -> 409 selamanya."""
    ref = ref_from_clip(api)
    ch = api.post("/api/characters", json={"name": "Rina", "description": "bob", "source_image_id": up(api)}).json()
    est = {"kind": "motion_anchor", "model": "openai/gpt-image-2", "character_id": ch["id"]}
    r = api.raw.post("/api/motion/anchor", json={"reference_id": ref["id"], "character_id": ch["id"],
                                                 "model": "openai/gpt-image-2", **confirmed(api, est)})
    assert r.status_code == 200, r.text
    anchor = r.json()
    assert anchor["kind"] == "anchor"
    assert api.raw.post("/api/estimate", json={"kind": "motion_anchor", "model": "openai/gpt-image-2"}).status_code == 400

    body = {"mode": "anchor_edit", "model": ALEPH, "reference_id": ref["id"], "prompt": "keep motion"}
    conf = confirmed(api, {"kind": "motion", "mode": "anchor_edit", "model": ALEPH, "reference_id": ref["id"]})
    assert api.raw.post("/api/motion", json={**body, **conf}).status_code == 400   # tanpa anchor
    r = api.raw.post("/api/motion", json={**body, **conf, "anchor_image_id": anchor["id"]})
    assert r.status_code == 200, r.text
    keyframes = fake.last_json("/videos")["provider"]["options"]["runway"]["keyframes"]
    assert keyframes[0]["seconds"] == 0 and keyframes[0]["uri"].startswith("data:image/")


def test_reference_mode_rejects_small_clip_before_cost(api, fake):
    ref = ref_from_clip(api)   # klip uji 160x90, di bawah batas piksel Seedance
    r = api.raw.post("/api/estimate", json={"kind": "motion", "mode": "reference", "model": "bytedance/seedance-2.5",
                                            "reference_id": ref["id"], "duration": 4, "resolution": "720p"})
    assert r.status_code == 400 and "terlalu kecil" in r.json()["detail"]


def test_moderation_rejection_is_explained(api, fake):
    ref = ref_from_clip(api)
    fake.video_submit_error = "InputVideoSensitiveContentDetected.PrivacyInformation: may contain real person"
    conf = confirmed(api, {"kind": "motion", "mode": "flux_edit", "model": FLUX, "reference_id": ref["id"]})
    r = api.raw.post("/api/motion", json={"mode": "flux_edit", "model": FLUX, "reference_id": ref["id"],
                                          "prompt": "p", **conf})
    assert r.status_code == 422 and "foto-realistik" in r.json()["detail"]
    assert not [c for c in api.get("/api/clips").json() if c["kind"] == "motion"]


def test_reference_from_clip_of_other_workspace_is_404(api):
    clip = api.post("/api/clips", json={**VIDEO, "image_id": up(api)}).json()
    api.studio.poll_once()
    assert api.post(f"/api/references/from-clip/{clip['id']}", **hdr(mkws(api))).status_code == 404


# ---------- trim video referensi (plan 11) ----------
def upload_ref(api, tmp_path, seconds, ws="main"):
    vid = make_video(tmp_path / f"u{seconds}.mp4", seconds=seconds)
    r = api.post("/api/references", files={"file": ("ref.mp4", vid.read_bytes(), "video/mp4")}, **hdr(ws))
    assert r.status_code == 200, r.text
    return r.json()


def test_long_upload_kept_whole_but_unusable_until_trimmed(api, fake, tmp_path):
    ref = upload_ref(api, tmp_path, 14)   # batas pakai 10 dtk, batas sumber 120 dtk
    assert 13.5 < ref["duration"] < 14.5
    r = api.raw.post("/api/estimate", json={"kind": "motion", "mode": "flux_edit", "model": FLUX, "reference_id": ref["id"]})
    assert r.status_code == 400 and "Potong" in r.json()["detail"]
    assert fake.submit_count == 0


def test_upload_over_source_limit_is_rejected(api, tmp_path, settings):
    import dataclasses
    api.studio.s = dataclasses.replace(api.studio.s, max_source_seconds=3.0)
    vid = make_video(tmp_path / "long.mp4", seconds=5)
    r = api.post("/api/references", files={"file": ("ref.mp4", vid.read_bytes(), "video/mp4")})
    assert r.status_code == 413 and "batas unggah" in r.json()["detail"]


def test_trim_makes_new_shorter_reference_and_lowers_estimate(api, fake, tmp_path):
    ref = upload_ref(api, tmp_path, 8)
    full = api.raw.post("/api/estimate", json={"kind": "motion", "mode": "flux_edit", "model": FLUX, "reference_id": ref["id"]}).json()
    r = api.post(f"/api/references/{ref['id']}/trim", json={"start": 2, "end": 5})
    assert r.status_code == 200, r.text
    cut = r.json()
    assert cut["id"] != ref["id"] and cut["trimmed"] is True and abs(cut["duration"] - 3) < 0.3
    est = api.raw.post("/api/estimate", json={"kind": "motion", "mode": "flux_edit", "model": FLUX, "reference_id": cut["id"]}).json()
    assert est["high"] < full["high"] * 0.6
    assert api.studio.motion.get_ref(ref["id"])["duration"] == ref["duration"]   # asal tidak berubah
    again = api.post(f"/api/references/{cut['id']}/trim", json={"start": 0, "end": 1.5}).json()   # trim berulang
    assert abs(again["duration"] - 1.5) < 0.3


def test_trim_validates_range(api, tmp_path):
    ref = upload_ref(api, tmp_path, 14)
    url = f"/api/references/{ref['id']}/trim"
    for body in ({"start": -1, "end": 3}, {"start": 3, "end": 3}, {"start": 3, "end": 3.5},
                 {"start": 0, "end": 13}, {"start": 5, "end": 2}):   # negatif, kosong, < 1 dtk, > 10 dtk, terbalik
        assert api.post(url, json=body).status_code == 400, body
    assert api.post(url, json={"start": "a", "end": 2}).status_code == 422
    ok = api.post(url, json={"start": 12, "end": 99})   # end melewati durasi: dipotong ke durasi, sisa 2 dtk
    assert ok.status_code == 200 and 1.5 < ok.json()["duration"] < 2.6


def test_trim_library_clip_needs_public_hosting(api, fake):
    ref = ref_from_clip(api)
    r = api.post(f"/api/references/{ref['id']}/trim", json={"start": 0, "end": 1})
    assert r.status_code == 501 and "PUBLIC_TUNNEL" in r.json()["detail"]


def test_trim_library_clip_with_hosting_gives_uploaded_style_reference(api, fake):
    from app.publicmedia import TunnelPublicMedia
    api.studio.public = TunnelPublicMedia(ttl=3600, starter=lambda port: (f"http://127.0.0.1:{port}", None))
    ref = ref_from_clip(api)
    r = api.post(f"/api/references/{ref['id']}/trim", json={"start": 0, "end": 1})
    assert r.status_code == 200, r.text
    assert r.json()["source_clip_id"] is None   # berkas baru: disajikan lewat hosting publik, bukan URL klip


def test_trim_reference_of_other_workspace_is_404(api, tmp_path):
    ref = upload_ref(api, tmp_path, 3)
    assert api.post(f"/api/references/{ref['id']}/trim", json={"start": 0, "end": 2}, **hdr(mkws(api))).status_code == 404


def test_health_exposes_reference_limit(api):
    assert api.get("/api/health").json()["max_reference_seconds"] == 10


def test_flux_subject_text_replaces_character_description(api, fake):
    """Deskripsi baku 'seperti di foto' membuat FLUX menolak (422); user bisa menggantinya dengan teks sendiri."""
    ref = ref_from_clip(api)
    ch = api.post("/api/characters", json={"name": "Rina", "description": "Seperti di foto", "source_image_id": up(api)}).json()
    conf = confirmed(api, {"kind": "motion", "mode": "flux_edit", "model": FLUX, "reference_id": ref["id"]})
    body = {"mode": "flux_edit", "model": FLUX, "reference_id": ref["id"], "prompt": "Replace the person.", "character_id": ch["id"], **conf}
    assert api.raw.post("/api/motion", json={**body, "subject_text": "young woman, short black bob, red jacket"}).status_code == 200
    sent = fake.last_json("/videos")["prompt"]
    assert "The new subject: young woman, short black bob, red jacket" in sent and "foto" not in sent
    assert api.raw.post("/api/motion", json=body).status_code == 200   # tanpa subject_text: deskripsi karakter (perilaku lama)
    assert "The new subject: Seperti di foto" in fake.last_json("/videos")["prompt"]
