#!/usr/bin/env python3
"""Auto-refresh queue + training progress page. Stdlib only.

    python watch_progress.py
    # http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
REFRESH_S = 10
CHART_SAMPLES = 180
MA_WINDOW = 10
SPS_YMAX_FLOOR = 900.0
GB_FPS = 59.727
DEFAULT_NUM_ENVS = 64
DEFAULT_MAX_STEPS = 2048 * 80
DEFAULT_ACTION_FREQ = 24
STATE_ORDER = {"running": 0, "queued": 1, "done": 2, "failed": 3}


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
    if "target-steps" in amap:
        return int(amap["target-steps"])
    if "total-timesteps" in amap:
        return int(amap["total-timesteps"])
    if "minutes" in amap:
        sps = float(amap.get("sps") or 0) or None
        if sps:
            return int(float(amap["minutes"]) * 60 * sps)
    return None


def job_session(amap: dict[str, str | bool]) -> str:
    session = str(amap.get("session-path") or "")
    if session:
        return session
    extend = amap.get("extend")
    if extend and extend is not True:
        name = str(extend)
        if name.startswith("runs_"):
            name = name[len("runs_"):]
        return f"runs_{name}"
    return ""


def sidecar_recipe(session: str) -> dict:
    """Newest lineage sidecar in the local run dir, if one exists (ticket 19)."""
    folder = ROOT / session
    if not session or not folder.is_dir():
        return {}
    best = None
    for path in folder.glob("poke_*_steps.json"):
        try:
            data = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        step = data.get("global_step")
        if isinstance(step, int) and (best is None or step > best[0]):
            best = (step, data)
    return best[1] if best else {}


def job_recipe(amap: dict[str, str | bool]) -> dict:
    num_envs = _as_int(amap.get("num-envs")) or DEFAULT_NUM_ENVS
    max_steps = _as_int(amap.get("max-steps")) or DEFAULT_MAX_STEPS
    action_freq = _as_int(amap.get("action-freq")) or DEFAULT_ACTION_FREQ
    n_steps = _as_int(amap.get("n-steps")) or max_steps // 64
    return {
        "num_envs": num_envs,
        "max_steps": max_steps,
        "n_steps": n_steps,
        "action_freq": action_freq,
        "rollout": n_steps * num_envs,
        "ep_hours": max_steps * action_freq / GB_FPS / 3600,
    }


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
            session = job_session(amap)
            csv_path = ROOT / session / "resource_log.csv" if session else None
            series = load_series(csv_path) if csv_path else []
            perf = series[-1] if series else {}
            target = planned_steps(amap)
            steps = _as_int(perf.get("steps"))
            pct = (100.0 * steps / target) if target and steps is not None else None
            assumed = amap.get("sps")
            try:
                assumed_sps = float(assumed) if assumed not in (None, "", True, False) else 720.0
            except (TypeError, ValueError):
                assumed_sps = 720.0
            recipe = job_recipe(amap)
            if amap.get("extend"):
                sidecar = sidecar_recipe(session)
                recipe["num_envs"] = _as_int(sidecar.get("num_envs")) or recipe["num_envs"]
                recipe["n_steps"] = _as_int(sidecar.get("n_steps")) or recipe["n_steps"]
                recipe["rollout"] = recipe["n_steps"] * recipe["num_envs"]
            rollout = recipe["rollout"]
            planned_updates = math.ceil(target / rollout) if target and rollout else None
            updates = steps // rollout if steps is not None and rollout else None
            rows.append(
                {
                    "file": path.name,
                    "name": name,
                    "args": job.get("args") or [],
                    "state": state,
                    "session": session,
                    "backup": str(amap.get("backup") or ""),
                    "target": target,
                    "assumed_sps": assumed_sps,
                    "start": status.get("start", ""),
                    "end": status.get("end", ""),
                    "exit": status.get("exit", ""),
                    "perf": perf,
                    "series": series,
                    "peak_rss": max((p["rss"] for p in series), default=None),
                    "peak_fp": max((p["fp"] for p in series), default=None),
                    "ma_sps": moving_avg_series(series, done=state == "done"),
                    "pct": pct,
                    "num_envs": recipe["num_envs"],
                    "n_steps": recipe["n_steps"],
                    "ep_hours": recipe["ep_hours"],
                    "updates": updates,
                    "planned_updates": planned_updates,
                }
            )
    rows.sort(key=_job_sort_key)
    return rows


def _job_sort_key(row: dict):
    group = STATE_ORDER.get(row["state"], 9)
    if row["state"] == "queued":
        return (group, 0.0, row["file"])
    start = parse_iso(row.get("start") or "")
    if row["state"] == "running":
        ts = start.timestamp() if start else float("inf")
        return (group, ts, row["file"])
    end = parse_iso(row.get("end") or "")
    end_ts = -end.timestamp() if end else 0.0
    start_ts = -start.timestamp() if start else 0.0
    return (group, end_ts, start_ts, row["file"])


def _as_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def iter_csv(csv_path: Path) -> list[dict[str, str]]:
    if csv_path is None or not csv_path.exists():
        return []
    with csv_path.open() as f:
        return list(csv.DictReader(f))


def load_series(csv_path: Path) -> list[dict]:
    out = []
    for row in iter_csv(csv_path):
        try:
            out.append(
                {
                    "wall": float(row["wall_s"]),
                    "avg_sps": float(row["avg_sps"]),
                    "instant_sps": float(row["instant_sps"]),
                    "rss": float(row["rss_mb"]),
                    "fp": float(row.get("footprint_mb") or row["rss_mb"]),
                    "cpu": float(row.get("cpu_pct") or 0),
                    "speedup": float(row.get("per_env_speedup") or 0),
                    "steps": float(row["timesteps"]),
                }
            )
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _chart_rows(series: list[dict], done: bool) -> list[dict]:
    rows = [p for p in series if p["steps"] > 0]
    if (
        done
        and rows
        and rows[-1]["instant_sps"] < max(rows[-1]["avg_sps"] * 0.25, 200)
    ):
        rows = rows[:-1]
    return rows


def moving_avg_series(series: list[dict], done: bool = False, window: int = MA_WINDOW) -> list[float]:
    instants = [p["instant_sps"] for p in _chart_rows(series, done)]
    if not instants:
        return []
    out = []
    running = 0.0
    for i, value in enumerate(instants):
        running += value
        if i >= window:
            running -= instants[i - window]
        out.append(running / min(i + 1, window))
    return out[-CHART_SAMPLES:]


def sparkline(
    points: list[float],
    ymin: float,
    ymax: float,
    target: float | None = None,
    title: str = "",
    w: int = 240,
    h: int = 48,
) -> str:
    if len(points) < 2:
        return f'<svg width="{w}" height="{h}"></svg>'
    span = (ymax - ymin) or 1.0
    step = (w - 4) / (len(points) - 1)

    def py(value: float) -> float:
        clamped = min(max(value, ymin), ymax)
        return h - 4 - ((clamped - ymin) / span) * (h - 8)

    coords = [f"{2 + i * step:.1f},{py(y):.1f}" for i, y in enumerate(points)]
    target_svg = ""
    if target is not None and ymin < target < ymax:
        y = py(target)
        target_svg = (
            f'<line x1="2" x2="{w - 2}" y1="{y:.1f}" y2="{y:.1f}" '
            f'stroke="#94a3b8" stroke-dasharray="3 3" stroke-width="1"/>'
        )
    title_svg = f"<title>{html.escape(title)}</title>" if title else ""
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f"{title_svg}{target_svg}"
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


def fmt_compact(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    absn = abs(n)
    if absn >= 1_000_000:
        text = f"{n / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if absn >= 1_000:
        text = f"{n / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}k"
    return f"{n:,.0f}"


def stacked_lines(lines: list[str]) -> str:
    if not lines:
        return "—"
    return lines[0] + "".join(f'<div class="muted">{line}</div>' for line in lines[1:])


def _fmt_rss(mb) -> str:
    n = float(mb)
    if n >= 1024:
        return f"{n / 1024:.1f} GB"
    return f"{n:,.0f} MB"


def fmt_ram(mb, peak_mb=None) -> str:
    if mb in (None, "") and peak_mb in (None, ""):
        return "—"
    lines = []
    if peak_mb not in (None, ""):
        lines.append(f"{_fmt_rss(peak_mb)} peak")
        if mb not in (None, ""):
            lines.append(_fmt_rss(mb))
    elif mb not in (None, ""):
        lines.append(_fmt_rss(mb))
    return stacked_lines(lines)


def fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 90 * 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f}h"


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def fmt_clock(dt: datetime, now: datetime) -> str:
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%d %b %H:%M")


def pct_cell(job: dict) -> str:
    pct = job["pct"]
    if pct is None:
        return "—"
    steps = _as_int(job["perf"].get("steps") if job["perf"] else None)
    target = job["target"]
    if target and steps is not None and steps > target:
        extra = steps - target
        return f"100%<div class='muted'>+{fmt_compact(extra)} overshoot</div>"
    return f"{pct:.1f}%"


def time_cell(job: dict, now: datetime) -> str:
    start = parse_iso(job.get("start") or "")
    end = parse_iso(job.get("end") or "")
    perf = job["perf"]
    state = job["state"]
    wall = float(perf["wall"]) if perf.get("wall") not in (None, "") else None

    lines = []
    if start:
        lines.append(f"started {fmt_clock(start, now)}")
    if state == "done" and start and end:
        lines.append(fmt_duration((end - start).total_seconds()) + " elapsed")
    elif wall is not None:
        lines.append(fmt_duration(wall) + " elapsed")

    remaining = None
    target = job["target"]
    steps = _as_int(perf.get("steps") if perf else None)
    avg = perf.get("avg_sps")
    if state == "running" and target and steps is not None and avg:
        leftover = target - steps
        if leftover > 0 and avg > 0:
            remaining = leftover / float(avg)
            eta_at = now + timedelta(seconds=remaining)
            lines.append(f"ETA {fmt_clock(eta_at, now)} ({fmt_duration(remaining)})")

    return stacked_lines(lines)


def job_tooltip(job: dict) -> str:
    args = " ".join(str(a) for a in (job.get("args") or []))
    if args:
        return f"{job['file']}\n{args}"
    return job["file"]


def with_tip(inner: str, tip: str) -> str:
    if not tip:
        return inner
    return f'<div class="tip" data-tip="{html.escape(tip).replace(chr(10), "&#10;")}">{inner}</div>'


def job_cell(job: dict) -> str:
    return (
        f'<strong>{html.escape(job["name"])}</strong>'
        f'<div class="muted">{job["num_envs"]} envs · ~{job["ep_hours"]:.1f}h ep</div>'
        f'<div class="muted">n_steps {fmt(job["n_steps"])}</div>'
    )


def steps_cell(job: dict) -> str:
    perf = job["perf"] or {}
    steps = _as_int(perf.get("steps"))
    target = job["target"]
    compact = f"{fmt_compact(steps)} / {fmt_compact(target)}"
    inner = compact
    if job.get("planned_updates") is not None or job.get("updates") is not None:
        inner += (
            f'<div class="muted">{fmt(job.get("updates"))} / '
            f'{fmt(job.get("planned_updates"))} updates</div>'
        )
    return inner


def steps_title(job: dict) -> str:
    perf = job["perf"] or {}
    return f"{fmt(_as_int(perf.get('steps')))} / {fmt(job['target'])}"


def speedup_cell(job: dict) -> str:
    value = (job.get("perf") or {}).get("speedup")
    if value in (None, ""):
        return "—"
    return f"{fmt(value, 1)}x"


def ram_cell(job: dict) -> str:
    perf = job.get("perf") or {}
    ram = fmt_ram(perf.get("fp"), job.get("peak_fp"))
    cpu = perf.get("cpu")
    if ram == "—" and cpu in (None, ""):
        return "—"
    extra = []
    if perf.get("fp") not in (None, "") and perf.get("rss") not in (None, ""):
        extra.append(f"residente {_fmt_rss(perf['rss'])}")
    if cpu not in (None, ""):
        extra.append(f"cpu {fmt(cpu)}%")
    if ram == "—":
        return stacked_lines(extra)
    return ram + "".join(f'<div class="muted">{line}</div>' for line in extra)


def sps_ymax(jobs: list[dict]) -> float:
    points = [v for job in jobs for v in job.get("ma_sps") or []]
    raw = max(points) if points else 0.0
    return max(SPS_YMAX_FLOOR, float(math.ceil(raw / 100.0) * 100.0))


def render(jobs: list[dict]) -> str:
    lock = JOBS / ".queue.lock"
    lock_note = "queue idle"
    if lock.exists():
        lock_note = f"queue lock pid {lock.read_text().strip()}"

    now = datetime.now().astimezone()
    ymin = 0.0
    ymax = sps_ymax(jobs)
    cards = []
    for job in jobs:
        perf = job["perf"]
        ma = job["ma_sps"]
        last_ma = ma[-1] if ma else None
        this_min = min(ma) if ma else None
        this_max = max(ma) if ma else None
        title = (
            f"axis {ymin:.0f}–{ymax:.0f} · this {this_min:.0f}–{this_max:.0f} · "
            f"last {last_ma:.0f} · target {job['assumed_sps']:.0f}"
            if last_ma is not None
            else ""
        )
        sps_svg = sparkline(ma, ymin, ymax, target=job["assumed_sps"], title=title) if ma else ""
        caption = (
            f"last {last_ma:.0f} · axis {ymin:.0f}–{ymax:.0f}"
            if last_ma is not None
            else "sps ma"
        )
        cards.append(
            f"""
            <tr class="state-{job['state']}">
              <td>{with_tip(job_cell(job), job_tooltip(job))}</td>
              <td><span class="pill">{html.escape(job['state'])}</span></td>
              <td>{pct_cell(job)}</td>
              <td>{with_tip(steps_cell(job), steps_title(job))}</td>
              <td>{fmt(perf.get('avg_sps'))}{f'<div class="muted">~{fmt(last_ma)} ma</div>' if last_ma is not None else ''}</td>
              <td>{time_cell(job, now)}</td>
              <td>{ram_cell(job)}</td>
              <td>{speedup_cell(job)}</td>
              <td class="chart">{sps_svg}<div class="muted">{caption}</div></td>
            </tr>"""
        )

    body = "\n".join(cards) or '<tr><td colspan="9">No jobs found.</td></tr>'
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
    .tip {{ cursor: help; }}
    .tip-box {{
      display: none; position: fixed; z-index: 50;
      max-width: min(28rem, calc(100vw - 16px));
      padding: 6px 8px; border-radius: 6px;
      background: #111827; color: #f9fafb;
      font-size: 12px; line-height: 1.4;
      white-space: pre-wrap; overflow-wrap: anywhere;
      pointer-events: none;
      box-shadow: 0 8px 24px rgba(0,0,0,.18);
    }}
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
        <th>Time</th><th>RAM / CPU</th><th>Game x</th><th>SPS (5 min ma)</th>
      </tr>
    </thead>
    <tbody>
      {body}
    </tbody>
  </table>
  <div class="tip-box" id="tip-box"></div>
  <script>
    (function () {{
      const box = document.getElementById('tip-box');
      let current = null;
      function hide() {{
        box.style.display = 'none';
        current = null;
      }}
      document.addEventListener('mouseover', function (e) {{
        const el = e.target.closest('[data-tip]');
        if (el === current) return;
        if (!el) {{ hide(); return; }}
        current = el;
        box.textContent = el.getAttribute('data-tip') || '';
        box.style.display = 'block';
        const r = el.getBoundingClientRect();
        let left = r.left;
        let top = r.bottom + 6;
        const w = box.offsetWidth;
        const h = box.offsetHeight;
        if (left + w > innerWidth - 8) left = innerWidth - w - 8;
        if (top + h > innerHeight - 8) top = r.top - h - 6;
        box.style.left = Math.max(8, left) + 'px';
        box.style.top = Math.max(8, top) + 'px';
      }});
    }})();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/index.html"}:
            self.send_error(404)
            return
        html_out = render(load_jobs()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(html_out)))
        self.end_headers()
        self.wfile.write(html_out)

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
