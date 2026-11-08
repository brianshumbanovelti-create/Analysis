import sys
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = "https://api.openf1.org/v1"
OUT_ROOT = Path("data")
WINDOW_MINUTES = 10
MIN_GAP = 0.35
_req_times = []

def _wait_for_slot():
    now = time.time()
    if _req_times:
        elapsed = now - _req_times[-1]
        if elapsed < MIN_GAP:
            time.sleep(MIN_GAP - elapsed)
            now = time.time()
    cutoff = now - 60
    _req_times[:] = [t for t in _req_times if t > cutoff]
    if len(_req_times) >= 30:
        sleep_for = 60 - (now - _req_times[0]) + 0.1
        time.sleep(sleep_for)
        now = time.time()
        _req_times[:] = [t for t in _req_times if t > now - 60]
    _req_times.append(now)

def api_get(path, params=None):
    url = BASE + path
    if params: url += "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        _wait_for_slot()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "f1-replay/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data, len(data) if isinstance(data, list) else 1, True
        except urllib.error.HTTPError as e:
            if e.code == 404: return [], 0, True
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            return [], 0, False
        except Exception:
            time.sleep(2 ** attempt)
    return [], 0, False

def fetch_all(endpoint, session_key):
    data, _, success = api_get(f"/{endpoint}", {"session_key": session_key})
    return data, success

def downsample_location(samples, start_dt):
    if not samples: return []
    samples.sort(key=lambda s: s.get("date", ""))
    samples = [s for s in samples if not (s.get("x") == 0 and s.get("y") == 0)]
    kept, last_sec = [], None
    for s in samples:
        try:
            dt = datetime.fromisoformat(s["date"].replace("Z", "+00:00"))
            t = (dt - start_dt).total_seconds()
        except Exception: continue
        sec = int(t)
        if sec != last_sec:
            kept.append([round(t, 2), s.get("x"), s.get("y")])
            last_sec = sec
    return kept

def main():
    if len(sys.argv) < 2: sys.exit(1)
    session_key = sys.argv[1]
    force = "--force" in sys.argv
    max_drivers, max_minutes = None, None
    for arg in sys.argv[2:]:
        if arg.startswith("--max_drivers="): max_drivers = int(arg.split("=")[1])
        elif arg.startswith("--max_minutes="): max_minutes = int(arg.split("=")[1])

    out_dir = OUT_ROOT / session_key
    loc_dir = out_dir / "location"
    loc_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== session_key={session_key} ===")
    sessions, _ = fetch_all("sessions", session_key)
    if not sessions: sys.exit(1)
    sess = sessions[0]
    
    meeting_key = sess.get("meeting_key")
    meetings = []
    if meeting_key:
        year = None
        try: year = datetime.fromisoformat(sess["date_start"].replace("Z","+00:00")).year
        except: pass
        if year:
            meeting_data, _, _ = api_get("/meetings", {"year": year})
            meetings = [m for m in meeting_data if m.get("meeting_key") == meeting_key]
    meeting = meetings[0] if meetings else {}

    meta = {
        "session_key": session_key, "session_name": sess.get("session_name"),
        "date_start": sess.get("date_start"), "date_end": sess.get("date_end"),
        "year": meeting.get("year"),
        "meeting_name": meeting.get("meeting_name") or meeting.get("circuit_short_name"),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    laps, _ = fetch_all("laps", session_key); (out_dir / "laps.json").write_text(json.dumps(laps))
    race_control, _ = fetch_all("race_control", session_key); (out_dir / "race_control.json").write_text(json.dumps(race_control))
    session_result, _ = fetch_all("session_result", session_key); (out_dir / "session_result.json").write_text(json.dumps(session_result))
    drivers, _ = fetch_all("drivers", session_key); (out_dir / "drivers.json").write_text(json.dumps(drivers))
    stints, _ = fetch_all("stints", session_key); (out_dir / "stints.json").write_text(json.dumps(stints))

    start_dt, end_dt = None, None
    if race_control:
        valid_rc = [m for m in race_control if m.get("date")]
        if valid_rc:
            start_dt = datetime.fromisoformat(valid_rc[0]["date"].replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(valid_rc[-1]["date"].replace("Z", "+00:00"))
    if not start_dt:
        try: start_dt = datetime.fromisoformat(sess["date_start"].replace("Z", "+00:00"))
        except: start_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if not end_dt: end_dt = start_dt + timedelta(hours=3)

    outline_file = out_dir / "outline.json"
    if not outline_file.exists() or force:
        valid_laps = [l for l in laps if l.get("lap_duration") and not l.get("is_pit_out_lap") and l.get("date_start")]
        if valid_laps:
            fastest = min(valid_laps, key=lambda l: l["lap_duration"])
            dn, lap_num, dur = fastest["driver_number"], fastest["lap_number"], fastest["lap_duration"]
            try:
                start_dt_outline = datetime.fromisoformat(fastest["date_start"].replace("Z", "+00:00"))
                end_dt_outline = start_dt_outline + timedelta(seconds=dur + 1)
                date_gt_o = start_dt_outline.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
                date_lt_o = end_dt_outline.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
                rows_o, _, success_o = api_get("/location", {"session_key": session_key, "driver_number": dn, "date>": date_gt_o, "date<": date_lt_o})
                if success_o and rows_o:
                    points = []
                    for r in rows_o:
                        if r.get("x") == 0 and r.get("y") == 0: continue
                        t_offset = (datetime.fromisoformat(r["date"].replace("Z", "+00:00")) - start_dt_outline).total_seconds()
                        points.append([r["x"], r["y"], t_offset])
                    outline_file.write_text(json.dumps({"driver": dn, "lap": lap_num, "lap_duration": dur, "points": points}))
            except Exception: pass

    driver_nums = [d["driver_number"] for d in drivers if "driver_number" in d]
    if max_drivers: driver_nums = driver_nums[:max_drivers]
    
    window = timedelta(minutes=WINDOW_MINUTES)
    if max_minutes: end_dt = min(end_dt, start_dt + timedelta(minutes=max_minutes))

    for dn in driver_nums:
        loc_file = loc_dir / f"{dn}.json"
        if loc_file.exists() and not force: continue
        all_samples, cur = [], start_dt
        while cur < end_dt:
            nxt = min(cur + window, end_dt)
            date_gt = cur.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
            date_lt = nxt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
            rows, _, success = api_get("/location", {"session_key": session_key, "driver_number": dn, "date>": date_gt, "date<": date_lt})
            if success and rows: all_samples.extend(rows)
            cur = nxt
        if all_samples:
            (loc_dir / f"{dn}.json").write_text(json.dumps(downsample_location(all_samples, start_dt)))
        time.sleep(MIN_GAP)

    idx_path = OUT_ROOT / "sessions.json"
    idx = []
    if idx_path.exists():
        try: idx = json.loads(idx_path.read_text())
        except: pass
    idx = [e for e in idx if str(e.get("session_key")) != str(session_key)]
    idx.append({"session_key": session_key, "year": meta.get("year"), "meeting_name": meta.get("meeting_name"), "session_name": meta.get("session_name")})
    idx_path.write_text(json.dumps(idx, indent=2))
    print("=== DONE ===")

if __name__ == "__main__": main()
