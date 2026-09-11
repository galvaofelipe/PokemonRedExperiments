#!/usr/bin/env python3
"""Auto-refresh queue + training progress page. Stdlib only.

    python watch_progress.py
    # http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import csv
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
REFRESH_S = 10


def arg_map(args: list[str]) -> dict[str, str | bool]:
    out: dict[str, str | bool] = {}
    i = 0
    while i < len(args):
        key = args[i]
        if not key.startswith("--"):
            i += 1
            continue
        if i + 1 < len(args) and not args[i + 1].startswith("--"):
            out[key[2:]] = args[i + 1]
            i += 2
        else:
            out[key[2:]] = True
            i += 1
    return out


def planned_steps(amap: dict[str, str | bool]) -> int | None:
    if "total-timesteps" in amap:
        return int(amap["total-timesteps"])
    if "minutes" in amap:
        sps = float(amap.get("sps") or 0) or None
        if sps:
            return int(float(amap["minutes"]) * 60 * sps)
    return None


def read_status(name: str) -> dict[str, str]:
    path = JOBS / f"{name}.status"
    info: dict[str, str] = {"state": "queued"}
    if not path.exists():
        return info
    lines = path.read_text().splitlines()
    if not lines:
        return info
    info["state"] = lines[0].strip()
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    return info


def load_jobs() -> list[dict]:
    rows = []
    seen = set()
    groups = [
        (JOBS, "queued"),
        (JOBS / "done", "done"),
        (JOBS / "failed", "failed"),
    ]
    for folder, fallback in groups:
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            job = json.loads(path.read_text())
            name = job["name"]
            if name in seen:
                continue
            seen.add(name)
            amap = arg_map(job.get("args") or [])
            status = read_status(name)
            state = status.get("state") or fallback
            if folder.name in {"done", "failed"}:
                state = folder.name
            session = str(amap.get("session-path") or "")
            csv_path = ROOT / session / "resource_log.csv" if session else None
            perf = last_perf(csv_path) if csv_path else {}
            series = load_series(csv_path) if csv_path else []
            target = planned_steps(amap)
            steps = _as_int(perf.get("timesteps"))
            pct = (100.0 * steps / target) if target and steps is not None else None
            rows.append(
                {
                    "file": path.name,
                    "name": name,
                    "state": state,
                    "session": session,
                    "backup": str(amap.get("backup") or ""),
                    "target": target,
                    "start": status.get("start", ""),
                    "end": status.get("end", ""),
                    "exit": status.get("exit", ""),
                    "perf": perf,
                    "series": series,
                    "pct": pct,
                }
            )
    order = {"running": 0, "queued": 1, "done": 2, "failed": 3}
    rows.sort(key=lambda r: (order.get(r["state"], 9), r["file"]))
    return rows


def _as_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def last_perf(csv_path: Path) -> dict[str, str]:
    rows = list(iter_csv(csv_path))
    return rows[-1] if rows else {}


def iter_csv(csv_path: Path) -> list[dict[str, str]]:
    if csv_path is None or not csv_path.exists():
        return []
    with csv_path.open() as f:
        return list(csv.DictReader(f))


def load_series(csv_path: Path, limit: int = 180) -> list[dict]:
    rows = iter_csv(csv_path)[-limit:]
    out = []
    for row in rows:
        try:
            out.append(
                {
                    "wall": float(row["wall_s"]),
                    "sps": float(row["avg_sps"]),
                    "rss": float(row["rss_mb"]),
                    "steps": float(row["timesteps"]),
                }
            )
        except (KeyError, ValueError):
            continue
    return out


def sparkline(points: list[float], w=240, h=48) -> str:
    if len(points) < 2:
        return f'<svg width="{w}" height="{h}"></svg>'
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    step = (w - 4) / (len(points) - 1)
    coords = []
    for i, y in enumerate(points):
        px = 2 + i * step
        py = h - 4 - ((y - lo) / span) * (h - 8)
        coords.append(f"{px:.1f},{py:.1f}")
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<polyline fill="none" stroke="#1d4ed8" stroke-width="1.5" '
        f'points="{" ".join(coords)}"/></svg>'
    )


def fmt(value, digits=0, suffix="") -> str:
    if value in (None, ""):
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if digits == 0:
        return f"{n:,.0f}{suffix}"
    return f"{n:,.{digits}f}{suffix}"


def render(jobs: list[dict]) -> str:
    lock = JOBS / ".queue.lock"
    lock_note = "queue idle"
    if lock.exists():
        pid = lock.read_text().strip()
        lock_note = f"queue lock pid {pid}"

    cards = []
    for job in jobs:
        perf = job["perf"]
        series = job["series"]
        sps_svg = sparkline([p["sps"] for p in series]) if series else ""
        rss_svg = sparkline([p["rss"] for p in series]) if series else ""
        pct = f"{job['pct']:.1f}%" if job["pct"] is not None else "—"
        wall_m = float(perf["wall_s"]) / 60 if perf.get("wall_s") else None
        cards.append(
            f"""
            <tr class="state-{job['state']}">
              <td><strong>{job['name']}</strong><div class="muted">{job['file']}</div></td>
              <td><span class="pill">{job['state']}</span></td>
              <td>{pct}</td>
              <td>{fmt(perf.get('timesteps'))} / {fmt(job['target'])}</td>
              <td>{fmt(perf.get('avg_sps'))}<div class="muted">inst {fmt(perf.get('instant_sps'))}</div></td>
              <td>{fmt(wall_m, 1)} min</td>
              <td>{fmt(perf.get('rss_mb'))} MB<div class="muted">cpu {fmt(perf.get('cpu_pct'))}%</div></td>
              <td>{fmt(perf.get('per_env_speedup'), 1)}x</td>
              <td class="chart">{sps_svg}<div class="muted">avg sps</div></td>
              <td class="chart">{rss_svg}<div class="muted">rss</div></td>
            </tr>"""
        )

    body = "\n".join(cards) or '<tr><td colspan="10">No jobs found.</td></tr>'
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta http-equiv="refresh" content="{REFRESH_S}"/>
  <title>Poke queue</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; color: #111; }}
    h1 {{ font-size: 20px; margin: 0 0 4px; }}
    .muted {{ color: #667; font-size: 12px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #556; }}
    .pill {{ padding: 2px 8px; border-radius: 999px; background: #e5e7eb; font-size: 12px; }}
    .state-running .pill {{ background: #dbeafe; color: #1e40af; }}
    .state-done .pill {{ background: #dcfce7; color: #166534; }}
    .state-failed .pill {{ background: #fee2e2; color: #991b1b; }}
    .chart svg {{ display: block; }}
  </style>
</head>
<body>
  <h1>Training queue</h1>
  <div class="muted">{lock_note} · refreshes every {REFRESH_S}s · {len(jobs)} job(s)</div>
  <table>
    <thead>
      <tr>
        <th>Job</th><th>State</th><th>%</th><th>Steps</th><th>SPS</th>
        <th>Wall</th><th>RAM / CPU</th><th>Game x</th><th></th><th></th>
      </tr>
    </thead>
    <tbody>
      {body}
    </tbody>
  </table>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/index.html"}:
            self.send_error(404)
            return
        html = render(load_jobs()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, fmt, *args):
        return


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"progress page: http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
