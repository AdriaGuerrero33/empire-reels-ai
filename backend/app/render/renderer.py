"""Renderizador: plan JSON -> un único grafo de filtros de FFmpeg -> MP4.

Una pasada por versión. La fuente se abre por "clusters" (rangos cercanos) con
búsqueda en la entrada (-ss), así un vídeo largo no se decodifica entero para
sacar 30 segundos.
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from ..config import get_settings
from ..media import run, thumbnail, validate_output
from . import audio_synth
from .geometry import crop_box
from .subtitles import build_ass
from .timeline import build, resolve_anchor

STYLES_COLOR = None  # importado perezosamente para evitar ciclos


def _color_filter(preset: str) -> str:
    from ..pipeline.styles import COLOR_GRADES
    return COLOR_GRADES.get(preset or "none", "")


def _clusters(segments: list[dict], max_gap: float = 20.0) -> list[dict]:
    order = sorted(range(len(segments)), key=lambda i: segments[i]["src_start"])
    clusters: list[dict] = []
    for i in order:
        s = segments[i]
        if clusters and s["src_start"] - clusters[-1]["end"] < max_gap:
            clusters[-1]["end"] = max(clusters[-1]["end"], s["src_end"])
            clusters[-1]["segs"].append(i)
        else:
            clusters.append({"start": s["src_start"], "end": s["src_end"], "segs": [i]})
    return clusters


def _f(v: float) -> str:
    return f"{v:.6f}".rstrip("0").rstrip(".") or "0"


def build_command(plan: dict, tl: dict, source: Path, media: dict, tmp: Path, out: Path,
                  quality: str = "final", brand: dict | None = None) -> tuple[list[str], dict]:
    s = get_settings()
    W, H = plan["format"]["width"], plan["format"]["height"]
    if quality == "preview":
        ph = s.preview_height if H >= W else int(s.preview_height * H / W)
        scale = ph / H
        ow, oh = int(W * scale) // 2 * 2, int(H * scale) // 2 * 2
    else:
        ow, oh = W, H
    sw, sh = media["width"], media["height"]
    fps = plan["format"].get("fps", 30)
    D = tl["duration"]
    reframe = plan.get("reframe", "face")

    inputs: list[list[str]] = []
    fg: list[str] = []

    def add_input(args: list[str]) -> int:
        inputs.append(args)
        return len(inputs) - 1

    segs = tl["segments"]
    clusters = _clusters(segs)
    seg_cluster = {}
    for ci, c in enumerate(clusters):
        c["input"] = add_input(["-ss", _f(c["start"]), "-t", _f(c["end"] - c["start"] + 0.5), "-i", str(source)])
        for si in c["segs"]:
            seg_cluster[si] = ci

    # Planos de vídeo
    shots_by_seg: dict[int, list[dict]] = {}
    for sh_ in tl["shots"]:
        shots_by_seg.setdefault(sh_["seg"], []).append(sh_)
    main_shots_per_cluster: dict[int, int] = {}
    for si, shots in shots_by_seg.items():
        ci = seg_cluster[si]
        main_shots_per_cluster[ci] = main_shots_per_cluster.get(ci, 0) + sum(
            1 for x in shots if not x.get("broll") and not x.get("card"))
    split_names: dict[int, list[str]] = {}
    for ci, c in enumerate(clusters):
        n = main_shots_per_cluster.get(ci, 0)
        if n == 0:
            continue
        names = [f"c{ci}v{k}" for k in range(n)]
        split_names[ci] = names
        outs = "".join(f"[{x}]" for x in names)
        fg.append(f"[{c['input']}:v]fps={fps},setsar=1,split={n}{outs}" if n > 1 else
                  f"[{c['input']}:v]fps={fps},setsar=1[{names[0]}]")
    used_split = {ci: 0 for ci in split_names}

    def reframe_chain(shot: dict, d: float) -> str:
        b = crop_box(shot, sw, sh, W, H, reframe)
        parts = []
        if b["mode"] == "fit":
            return "FIT"
        if shot.get("pan"):
            x0 = crop_box(shot, sw, sh, W, H, reframe, cx=shot["pan"][0])["x"]
            x1 = crop_box(shot, sw, sh, W, H, reframe, cx=shot["pan"][1])["x"]
            xexpr = f"'{x0}+({x1 - x0})*min(t/{_f(max(d, 0.1))},1)'"
            parts.append(f"crop={b['w']}:{b['h']}:{xexpr}:{b['y']}")
        else:
            parts.append(f"crop={b['w']}:{b['h']}:{b['x']}:{b['y']}")
        parts.append(f"scale={ow}:{oh}:flags=bicubic")
        push = float(shot.get("push") or 0)
        if push > 0:
            nfr = max(1, int(round(d * fps)))
            parts.append(f"zoompan=z='1+{_f(push)}*on/{nfr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                         f":d=1:s={ow}x{oh}:fps={fps}")
        return ",".join(parts)

    seg_v: dict[int, str] = {}
    for si, o in enumerate(segs):
        ci = seg_cluster[si]
        base = clusters[ci]["start"]
        labels = []
        for k, shot in enumerate(shots_by_seg.get(si, [])):
            d = shot["out_end"] - shot["out_start"]
            lab = f"v{si}_{k}"
            if shot.get("broll"):
                asset = shot["broll"]
                path = s.data_dir / asset["path"]
                if asset.get("kind") == "image":
                    idx = add_input(["-loop", "1", "-framerate", str(fps), "-t", _f(d + 0.2), "-i", str(path)])
                    nfr = max(1, int(round(d * fps)))
                    fg.append(f"[{idx}:v]scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},setsar=1,"
                              f"zoompan=z='1+0.07*on/{nfr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={ow}x{oh}:fps={fps},"
                              f"trim=duration={_f(d)},setpts=PTS-STARTPTS,format=yuv420p[{lab}]")
                else:
                    idx = add_input(["-stream_loop", "-1", "-t", _f(d + 0.5), "-i", str(path)])
                    fg.append(f"[{idx}:v]fps={fps},scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},"
                              f"setsar=1,trim=duration={_f(d)},setpts=PTS-STARTPTS,format=yuv420p[{lab}]")
            elif shot.get("card"):
                primary = ((brand or {}).get("primary") or "#0F3D2E").lstrip("#")
                fg.append(f"gradients=s={ow}x{oh}:c0=0x{primary}:c1=0x050807:x0=0:y0=0:x1={ow}:y1={oh}:"
                          f"d={_f(d)}:r={fps}:speed=0.02,setsar=1,format=yuv420p[{lab}]")
            else:
                src_name = split_names[ci][used_split[ci]]
                used_split[ci] += 1
                a, b_ = shot["src_start"] - base, shot["src_end"] - base
                chain = reframe_chain(shot, d)
                trim = f"[{src_name}]trim=start={_f(a)}:end={_f(b_)},setpts=PTS-STARTPTS"
                if chain == "FIT":
                    fg.append(f"{trim},split=2[{lab}bg][{lab}fg]")
                    fg.append(f"[{lab}bg]scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},"
                              f"gblur=sigma=28,eq=brightness=-0.08[{lab}bgb]")
                    fg.append(f"[{lab}fg]scale={ow}:{oh}:force_original_aspect_ratio=decrease[{lab}fgs]")
                    fg.append(f"[{lab}bgb][{lab}fgs]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[{lab}]")
                else:
                    fg.append(f"{trim},{chain},setsar=1,format=yuv420p[{lab}]")
            labels.append(lab)
        if len(labels) == 1:
            seg_v[si] = labels[0]
        else:
            fg.append("".join(f"[{x}]" for x in labels) + f"concat=n={len(labels)}:v=1:a=0[sv{si}]")
            seg_v[si] = f"sv{si}"

    # Audio de la voz por segmento
    seg_a: dict[int, str] = {}
    if media.get("has_audio"):
        per_cluster: dict[int, list[int]] = {}
        for si in range(len(segs)):
            per_cluster.setdefault(seg_cluster[si], []).append(si)
        for ci, sis in per_cluster.items():
            names = [f"c{ci}a{k}" for k in range(len(sis))]
            src = f"[{clusters[ci]['input']}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
            fg.append(f"{src},asplit={len(names)}" + "".join(f"[{x}]" for x in names) if len(names) > 1
                      else f"{src}[{names[0]}]")
            for k, si in enumerate(sis):
                o = segs[si]
                a, b_ = o["src_start"] - clusters[ci]["start"], o["src_end"] - clusters[ci]["start"]
                d = o["dur"]
                fg.append(f"[{names[k]}]atrim=start={_f(a)}:end={_f(b_)},asetpts=PTS-STARTPTS,"
                          f"apad=whole_dur={_f(d)},afade=t=in:d=0.012,afade=t=out:st={_f(max(0, d - 0.018))}:d=0.018[sa{si}]")
                seg_a[si] = f"sa{si}"
    else:
        for si, o in enumerate(segs):
            fg.append(f"aevalsrc=0:c=stereo:s=48000:d={_f(o['dur'])}[sa{si}]")
            seg_a[si] = f"sa{si}"

    # Unión de segmentos: grupos por corte seco y fundidos entre grupos
    groups: list[list[int]] = [[0]] if segs else []
    for si in range(1, len(segs)):
        if segs[si - 1].get("trans_out"):
            groups.append([si])
        else:
            groups[-1].append(si)
    g_v, g_a = [], []
    for gi, g in enumerate(groups):
        if len(g) == 1:
            g_v.append(seg_v[g[0]])
            g_a.append(seg_a[g[0]])
        else:
            ins = "".join(f"[{seg_v[si]}][{seg_a[si]}]" for si in g)
            fg.append(f"{ins}concat=n={len(g)}:v=1:a=1[gv{gi}][ga{gi}]")
            g_v.append(f"gv{gi}")
            g_a.append(f"ga{gi}")
    cur_v, cur_a = g_v[0], g_a[0]
    for gi in range(1, len(groups)):
        first = groups[gi][0]
        tr = segs[first - 1]["trans_out"]
        td = tr["dur"]
        offset = segs[first]["out_start"]
        xt = {"fade": "fade", "dissolve": "dissolve", "slide": "slideleft", "wipe": "wipeleft",
              "white": "fadewhite", "black": "fadeblack", "smooth": "smoothleft"}.get(tr["type"], "fade")
        fg.append(f"[{cur_v}][{g_v[gi]}]xfade=transition={xt}:duration={_f(td)}:offset={_f(offset)}[xv{gi}]")
        fg.append(f"[{cur_a}][{g_a[gi]}]acrossfade=d={_f(td)}:c1=tri:c2=tri[xa{gi}]")
        cur_v, cur_a = f"xv{gi}", f"xa{gi}"

    # Postproducción de imagen
    post = []
    col = _color_filter((plan.get("color") or {}).get("preset", "none"))
    if col:
        post.append(col)
    if plan.get("letterbox"):
        post.append("drawbox=x=0:y=0:w=iw:h=ih*0.055:color=black:t=fill,"
                    "drawbox=x=0:y=ih-ih*0.055:w=iw:h=ih*0.055:color=black:t=fill")
    ass_text = build_ass(plan, tl, brand)
    (tmp / "subs.ass").write_text(ass_text, encoding="utf-8")
    fonts_dst = tmp / "fonts"
    if not fonts_dst.exists():
        shutil.copytree(s.fonts_dir, fonts_dst, ignore=shutil.ignore_patterns("*.txt"))
    post.append("ass=subs.ass:fontsdir=fonts")
    fg.append(f"[{cur_v}]" + ",".join(post) + "[vpost]")
    vlast = "vpost"
    logo = plan.get("logo") or {}
    if logo.get("enabled") and logo.get("path"):
        lp = s.library_dir / "logos" / Path(logo["path"]).name
        if lp.exists():
            idx = add_input(["-loop", "1", "-t", _f(D + 0.5), "-i", str(lp)])
            lw = max(16, int(ow * float(logo.get("scale", 0.16))) // 2 * 2)
            op = max(0.1, min(1.0, float(logo.get("opacity", 0.9))))
            pos = logo.get("position", "top-right")
            mx, my = int(ow * 0.05), int(oh * (0.06 if oh > ow else 0.05))
            xy = {"top-right": f"W-w-{mx}:{my}", "top-left": f"{mx}:{my}",
                  "bottom-right": f"W-w-{mx}:H-h-{int(oh * 0.25 if oh > ow else my)}",
                  "bottom-left": f"{mx}:H-h-{int(oh * 0.25 if oh > ow else my)}"}.get(pos, f"W-w-{mx}:{my}")
            fg.append(f"[{idx}:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa={_f(op)}[logo]")
            fg.append(f"[{vlast}][logo]overlay={xy}:shortest=1,format=yuv420p[vlogo]")
            vlast = "vlogo"
    fg.append(f"[{vlast}]format=yuv420p[vout]")

    # Postproducción de audio: música con ducking, efectos y normalización
    mix_inputs = []
    music = plan.get("music") or {}
    mpath = audio_synth.music_file(music.get("preset", "none"), D)
    if mpath:
        idx = add_input(["-stream_loop", "-1", "-t", _f(D + 0.2), "-i", str(mpath)])
        vol = float(music.get("volume_db", -24))
        fg.append(f"[{cur_a}]asplit=2[voice][vkey]")
        fg.append(f"[{idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                  f"atrim=0:{_f(D)},volume={_f(vol + 10)}dB,afade=t=out:st={_f(max(0, D - 1.5))}:d=1.5[mraw]")
        if music.get("duck", True):
            fg.append("[mraw][vkey]sidechaincompress=threshold=0.015:ratio=8:attack=20:release=400:makeup=1[mduck]")
        else:
            fg.append("[vkey]anullsink")
            fg.append("[mraw]anull[mduck]")
        mix_inputs = ["voice", "mduck"]
    else:
        mix_inputs = [cur_a]
    for k, fx in enumerate(plan.get("sfx", [])):
        if fx.get("enabled") is False:
            continue
        span = resolve_anchor(tl, {**fx, "dur": 0.6})
        if not span:
            continue
        try:
            p = audio_synth.sfx_file(fx.get("kind", "whoosh"))
        except ValueError:
            continue
        idx = add_input(["-i", str(p)])
        ms = int(span[0] * 1000)
        fg.append(f"[{idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                  f"volume={_f(float(fx.get('volume_db', -9)))}dB,adelay={ms}|{ms}[fx{k}]")
        mix_inputs.append(f"fx{k}")
    lufs = float((plan.get("audio") or {}).get("loudnorm", -14))
    if len(mix_inputs) > 1:
        fg.append("".join(f"[{x}]" for x in mix_inputs) +
                  f"amix=inputs={len(mix_inputs)}:duration=first:normalize=0[amixed]")
        alast = "amixed"
    else:
        alast = mix_inputs[0]
    fg.append(f"[{alast}]loudnorm=I={_f(lufs)}:TP=-1.5:LRA=11,aresample=48000,"
              f"atrim=0:{_f(D)}[aout]")

    graph = ";\n".join(fg)
    (tmp / "graph.txt").write_text(graph, encoding="utf-8")
    preset = s.x264_preset if quality == "final" else "ultrafast"
    crf = s.x264_crf if quality == "final" else 28
    cmd = [s.ffmpeg_bin, "-y", "-hide_banner", "-v", "error"]
    for a in inputs:
        cmd += a
    cmd += ["-/filter_complex", "graph.txt", "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-r", str(fps), "-c:a", "aac", "-b:a", "160k" if quality == "final" else "96k",
            "-movflags", "+faststart", "-t", _f(D), str(out)]
    return cmd, {"width": ow, "height": oh, "duration": D, "inputs": len(inputs), "filters": len(fg)}


def render_plan(plan: dict, words: list[dict], source: Path, media: dict, out_dir: Path, name: str,
                quality: str = "final", brand: dict | None = None, on_progress=None) -> dict:
    s = get_settings()
    tl = build(plan, words)
    if not tl["segments"] or tl["duration"] < 0.5:
        raise ValueError("El plan no contiene segmentos renderizables.")
    tmp = out_dir / "tmp" / uuid.uuid4().hex[:10]
    tmp.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.mp4"
    part = out_dir / f"{name}.part.mp4"
    try:
        cmd, info = build_command(plan, tl, source.resolve(), media, tmp, part.resolve(), quality, brand)
        res = run(cmd, timeout=s.render_timeout_s, on_progress=on_progress, total_s=tl["duration"], cwd=tmp)
        validation = validate_output(part, info["width"], info["height"], tl["duration"])
        part.replace(out)
        thumb = out_dir / f"{name}.jpg"
        thumbnail(out, min(1.2, tl["duration"] / 3), thumb)
        (out_dir / f"{name}.ass").write_text((tmp / "subs.ass").read_text(encoding="utf-8"), encoding="utf-8")
        return {"path": out, "thumb": thumb, "validation": validation, "duration": tl["duration"],
                "wall_s": res.wall_s, "cpu_s": res.cpu_s, "info": info, "words": tl["words"]}
    finally:
        part.unlink(missing_ok=True)
        if not s.keep_temp:
            shutil.rmtree(tmp, ignore_errors=True)
