#!/usr/bin/env python3
"""Turn one continuous shot of the film into an explorable World Labs Marble world.

    export WLT_API_KEY=...                        # never commit the key
    python world.py temple                        # render clean clip -> upload -> generate -> poll
    python world.py chamber --model marble-1.1-plus

The clip is rendered without subtitles, date stamp or cut glitches (they would be
baked into the world), but keeps the camcorder look. Results land in out/world_<scene>/.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

import numpy as np

import render
from common import FPS, OH, OW, SCENES

API = "https://api.worldlabs.ai/marble/v1"

PROMPTS = {
    "temple": "Interior of a ruined ancient Indian stone temple antechamber lit only by a warm hand torch: "
              "broken carved pillars, eroded relief figures on the walls, rubble and grit on the floor, "
              "and at the rear a heavy stone doorway whose lower edge is buried under rubble. 1987 camcorder footage.",
    "chamber": "A vast dark corbelled stone dome inside an ancient temple, enormous curved walls of ancient masonry "
               "rising into darkness, a single warm torch beam on the stones, rubble floor. 1987 camcorder footage.",
    "hills": "Dry rocky scrubland hills in central India under an overexposed sky, a dirt track, "
             "a carved stone lintel half buried in a rocky outcrop. 1987 camcorder footage.",
}


def clean_frame(fi):
    t = fi / FPS
    name, lt = render.scene_at(t)
    img, gain, blur, _stamp = render.get_scene(name).frame(lt)
    out = render.camcorder(img, fi, gain, blur, None, 0.0)
    out = render.cv2.resize(out, (OW, OH), interpolation=render.cv2.INTER_LINEAR)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes()


def render_clip(scene, path, skip):
    a, b = next((s0, s1) for n, s0, s1 in SCENES if n == scene)
    frames = range(int((a + skip) * FPS) + 1, int(b * FPS))
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{OW}x{OH}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-movflags", "+faststart", path], stdin=subprocess.PIPE)
    from multiprocessing import Pool
    with Pool(os.cpu_count()) as pool:
        for buf in pool.imap(clean_frame, frames, chunksize=4):
            ff.stdin.write(buf)
    ff.stdin.close()
    ff.wait()


def call(method, url, body=None, headers=None):
    hdr = {"WLT-Api-Key": os.environ["WLT_API_KEY"], "Content-Type": "application/json"}
    hdr.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url} -> {e.code}: {e.read().decode()[:2000]}")


def upload(path):
    prep = call("POST", f"{API}/media-assets:prepare_upload",
                {"file_name": os.path.basename(path), "extension": "mp4", "kind": "video"})
    info = prep["upload_info"]
    hdr = {"Content-Type": "video/mp4", **(info.get("required_headers") or {})}
    with open(path, "rb") as f:
        req = urllib.request.Request(info["upload_url"], data=f.read(), headers=hdr,
                                     method=info.get("upload_method", "PUT"))
    with urllib.request.urlopen(req, timeout=600) as r:
        print("uploaded", r.status)
    return prep["media_asset"]["media_asset_id"]


def download(url, path):
    with urllib.request.urlopen(url, timeout=600) as r, open(path, "wb") as f:
        f.write(r.read())
    print("  ->", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", choices=sorted(PROMPTS))
    ap.add_argument("--model", default="marble-1.1")
    ap.add_argument("--skip", type=float, default=1.5, help="seconds to drop from the start of the shot")
    args = ap.parse_args()
    if "WLT_API_KEY" not in os.environ:
        sys.exit("set WLT_API_KEY")

    outdir = os.path.join(render.HERE, "out", f"world_{args.scene}")
    os.makedirs(outdir, exist_ok=True)
    clip = os.path.join(outdir, f"{args.scene}_clean.mp4")
    if not os.path.exists(clip):
        render_clip(args.scene, clip, args.skip)
    print("clip", clip, os.path.getsize(clip) // 1024, "KB")

    asset = upload(clip)
    op = call("POST", f"{API}/worlds:generate", {
        "display_name": f"The Temple - {args.scene}",
        "model": args.model,
        "tags": ["the-temple", "concept"],
        "world_prompt": {"type": "video", "text_prompt": PROMPTS[args.scene],
                         "video_prompt": {"source": "media_asset", "media_asset_id": asset}},
    })
    op_id = op["operation_id"]
    print("operation", op_id)
    while True:
        st = call("GET", f"{API}/operations/{op_id}")
        if st.get("done"):
            break
        print("  ", time.strftime("%H:%M:%S"), json.dumps(st.get("metadata"))[:200], flush=True)
        time.sleep(15)
    if st.get("error"):
        sys.exit(f"failed: {st['error']}")
    world = st["response"]
    json.dump(st, open(os.path.join(outdir, "world.json"), "w"), indent=2)
    print("world", world.get("world_id"), world.get("world_marble_url"))
    assets = world.get("assets") or {}
    pano = (assets.get("imagery") or {}).get("pano_url")
    if pano:
        download(pano, os.path.join(outdir, "pano" + os.path.splitext(pano.split("?")[0])[1]))
    if assets.get("thumbnail_url"):
        download(assets["thumbnail_url"], os.path.join(outdir, "thumbnail.webp"))
    for k, u in ((assets.get("splats") or {}).get("spz_urls") or {}).items():
        download(u, os.path.join(outdir, f"splat_{k}.spz"))
    mesh = (assets.get("mesh") or {}).get("collider_mesh_url")
    if mesh:
        download(mesh, os.path.join(outdir, "collider.glb"))


if __name__ == "__main__":
    main()
