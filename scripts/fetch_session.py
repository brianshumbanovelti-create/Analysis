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

# Rate limit: 3 req/sec and 30 req/min. 
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
        print(f"  [rate] 30/min reached, sleeping {sleep_for:.1f}s")
        time.sleep(sleep_for)
        now = time.time()
        _req_times[:] = [t for t in _req_times if t > now - 60]
    _req_times.append(now)

def api_get(path, params=None):
    """GET with retry. Returns (data, row_count, success)."""
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        _wait_for_slot()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "f1-replay-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                count = len(data) if isinstance(data, list) else 1
                print(f"  GET {path} {params or ''} -> {count} rows")
                return data, count, True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  GET {path} {params or ''} -> 404 (no rows)")
                return [], 0, True
            if e.code == 429 or e.code >= 500:
                wait = 2 ** attempt
                print(f"  GET {path} -> HTTP {e.code}, retry in {wait}s (attempt {attempt+1}/5)")
                time.sleep(wait)
                continue
            print(f"  GET {path} -> HTTP {e.code} (giving up)")
            return [], 0, False
        except Exception as e:
            wait = 2 ** attempt
            print(f"  GET {path} -> {e}, retry in {wait}s (attempt {attempt+1}/5)")
            time.sleep(wait)
    
    print(f"  GET {path} -> exhausted retries")
    return [], 0, False

def fetch_all(endpoint, session_key):
    data, _, success = api_get(f"/{endpoint}", {"session_key": session_key})
    if data:
        print(f"  sample {endpoint}: {json.dumps(data[0], default=str)[:300]}")
    return data, success

def downsample_location(samples, start_dt):
    if not samples:
        return []
    samples.sort(key=lambda s: s.get("date", ""))
    
    # ZERO FILTER: drop rows where x == 0 and y == 0
    samples = [s for s in samples if not (s.get("x") == 0 and s.get("y") == 0)]
    
    kept = []
    last_sec = None
    for s in samples:
        try:
            dt = datetime.fromisoformat(s["date"].replace("Z", "+00:00"))
            t = (dt - start_dt).total_seconds()
        except Exception:
            continue
        sec = int(t)
        if sec != last_sec:
            kept.append([round(t, 2), s.get("x"), s.get("y")])
            last_sec = sec
    return kept

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/fetch_session.py <session_key> [--force] [--max_drivers=N] [--max_minutes=N]")
        sys.exit(1)
        
    session_key = sys.argv[1]
    force = "--force" in sys.argv
    max_drivers = None
    max_minutes = None
    for arg in sys.argv[2:]:
        if arg.startswith("--max_drivers="):
            max_drivers = int(arg.split("=")[1])
        elif arg.startswith("--max_minutes="):
            max_minutes = int(arg.split("=")[1])

    out_dir = OUT_ROOT / session_key
    loc_dir = out_dir / "location"
    loc_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== session_key={session_key} ===")
    print("Fetching session + meeting info...")
    sessions, _ = fetch_all("sessions", session_key)
    if not sessions:
        print("FATAL: no session info returned")
        sys.exit(1)
    sess = sessions[0]
    meeting_key = sess.get("meeting_key")
    meetings = []
    
    if meeting_key:
        year = None
        try:
            year = datetime.fromisoformat(sess["date_start"].replace("Z","+00:00")).year
        except Exception:
            pass
        if year:
            meeting_data, _, _ = api_get("/meetings", {"year": year})
            meetings = [m for m in meeting_data if m.get("meeting_key") == meeting_key]
    meeting = meetings[0] if meetings else {}

    meta = {
        "session_key": session_key,
        "session_name": sess.get("session_name"),
        "date_start": sess.get("date_start"),
        "date_end": sess.get("date_end"),
        "year": meeting.get("year"),
        "meeting_name": meeting.get("meeting_name") or meeting.get("circuit_short_name"),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print("meta.json written")

    try:
        start_dt = datetime.fromisoformat(sess["date_start"].replace("Z", "+00:00"))
    except Exception:
        start_dt = None

    drivers, _ = fetch_all("drivers", session_key)
    (out_dir / "drivers.json").write_text(json.dumps(drivers))
    print(f"drivers.json written ({len(drivers)} drivers)")

    laps, _ = fetch_all("laps", session_key)
    (out_dir / "laps.json").write_text(json.dumps(laps))
    print(f"laps.json written ({len(laps)} rows)")

    positions, _ = fetch_all("position", session_key)
    (out_dir / "positions.json").write_text(json.dumps(positions))
    print(f"positions.json written ({len(positions)} rows)")

    stints, _ = fetch_all("stints", session_key)
    (out_dir / "stints.json").write_text(json.dumps(stints))
    print(f"stints.json written ({len(stints)} rows)")

    # --- OUTLINE GENERATION ---
    outline_file = out_dir / "outline.json"
    if not outline_file.exists() or force:
        print("Building outline.json...")
        valid_laps = [l for l in laps if l.get("lap_duration") and not l.get("is_pit_out_lap") and l.get("date_start")]
        if valid_laps:
            fastest = min(valid_laps, key=lambda l: l["lap_duration"])
            dn = fastest["driver_number"]
            lap_num = fastest["lap_number"]
            dur = fastest["lap_duration"]
            try:
                start_dt_outline = datetime.fromisoformat(fastest["date_start"].replace("Z", "+00:00"))
                end_dt_outline = start_dt_outline + timedelta(seconds=dur + 1)
                date_gt_o = start_dt_outline.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
                date_lt_o = end_dt_outline.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
                rows_o, count_o, success_o = api_get("/location", {
                    "session_key": session_key,
                    "driver_number": dn,
                    "date>": date_gt_o,
                    "date<": date_lt_o,
                })
                if success_o and rows_o:
                    points = [[r["x"], r["y"]] for r in rows_o if not (r.get("x") == 0 and r.get("y") == 0)]
                    outline_data = {"driver": dn, "lap": lap_num, "lap_duration": dur, "points": points}
                    outline_file.write_text(json.dumps(outline_data))
                    print(f"outline: driver {dn} lap {lap_num}, {dur}s, {len(points)} points")
            except Exception as e:
                print(f"WARN: outline failed: {e}")
        else:
            print("WARN: no valid lap found for outline")

    # --- LOCATION FETCHING ---
    print("Fetching location (per driver, windowed)...")
    if start_dt is None and laps:
        try:
            start_dt = datetime.fromisoformat(laps[0]["date_start"].replace("Z", "+00:00"))
        except Exception:
            pass
    if start_dt is None:
        start_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)

    end_dt = None
    try:
        end_dt = datetime.fromisoformat(sess["date_end"].replace("Z", "+00:00"))
    except Exception:
        if laps:
            try:
                end_dt = datetime.fromisoformat(laps[-1]["date_start"].replace("Z", "+00:00")) + timedelta(minutes=5)
            except Exception:
                pass
    if end_dt is None:
        end_dt = start_dt + timedelta(hours=3)

    driver_nums = [d["driver_number"] for d in drivers if "driver_number" in d]
    if max_drivers:
        driver_nums = driver_nums[:max_drivers]
    print(f"Fetching location for {len(driver_nums)} drivers")

    window = timedelta(minutes=WINDOW_MINUTES)
    if max_minutes:
        end_dt = min(end_dt, start_dt + timedelta(minutes=max_minutes))
        print(f"Test mode: limiting to {max_minutes} minutes")

    failed_windows = []
    
    for dn in driver_nums:
        loc_file = loc_dir / f"{dn}.json"
        if loc_file.exists() and not force:
            print(f"  driver {dn}: already exists, skipping (use --force to overwrite)")
            continue

        all_samples = []
        cur = start_dt
        driver_has_failures = False
        
        while cur < end_dt:
            nxt = min(cur + window, end_dt)
            date_gt = cur.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
            date_lt = nxt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
            
            rows, count, success = api_get("/location", {
                "session_key": session_key,
                "driver_number": dn,
                "date>": date_gt,
                "date<": date_lt,
            })
            
            if not success:
                driver_has_failures = True
                failed_windows.append(f"Driver {dn}: {cur} to {nxt}")
                
            if rows:
                all_samples.extend(rows)
            cur = nxt

        if driver_has_failures:
            print(f"  driver {dn}: FAILED windows, file not written")
        elif all_samples:
            down = downsample_location(all_samples, start_dt)
            (loc_dir / f"{dn}.json").write_text(json.dumps(down))
            print(f"  driver {dn}: {len(all_samples)} raw -> {len(down)} kept")
        else:
            print(f"  driver {dn}: no location data")
            
        time.sleep(MIN_GAP)

    idx_path = OUT_ROOT / "sessions.json"
    idx = []
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text())
        except Exception:
            idx = []
    idx = [e for e in idx if str(e.get("session_key")) != str(session_key)]
    idx.append({
        "session_key": session_key,
        "year": meta.get("year"),
        "meeting_name": meta.get("meeting_name"),
        "session_name": meta.get("session_name"),
        "date_start": meta.get("date_start"),
    })
    idx_path.write_text(json.dumps(idx, indent=2))
    print(f"sessions.json updated ({len(idx)} entries)")

    print(f"Failed windows: {len(failed_windows)}")
    if failed_windows:
        print("Failed window details:")
        for w in failed_windows:
            print(f"  - {w}")
        sys.exit(1)
        
    print("=== DONE ===")

if __name__ == "__main__":
    main()
