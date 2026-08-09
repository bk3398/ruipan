#!/usr/bin/env python3
"""Patch live-scores-preview-v6.html to add live polling + goal alerts.
- Polls /api/v1/live every 20s
- Updates minute/score for live matches in-place
- Flash + beep on score change
"""
import re, sys

HTML = "/opt/ruipan/static/live-scores-preview-v6.html"

CSS_BLOCK = """
/* ── Live goal flash ── */
@keyframes goalFlash {
  0% { background: rgba(255, 215, 0, 0.6); }
  50% { background: rgba(255, 215, 0, 0.3); }
  100% { background: transparent; }
}
.match-row.goal-flash {
  animation: goalFlash 2s ease-out;
}
.match-row.live .score-cell { transition: all 0.3s; }
.score-cell.goal-scored {
  color: #ff6b00 !important;
  font-weight: 800;
  transform: scale(1.3);
  display: inline-block;
}
"""

JS_BLOCK = r"""
// ── Live polling: minute + score + goal alerts ──
let _livePrevScores = {};
let _livePollTimer = null;
let _liveAudioCtx = null;
let _liveSoundOn = true;

function _liveBeep() {
  if (!_liveSoundOn) return;
  try {
    if (!_liveAudioCtx) _liveAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const ctx = _liveAudioCtx;
    // Two-tone beep
    [{"f":880,"t":0,"d":0.15},{"f":1100,"t":0.18,"d":0.2}].forEach(n => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.connect(g); g.connect(ctx.destination);
      o.frequency.value = n.f;
      o.type = "sine";
      g.gain.setValueAtTime(0.3, ctx.currentTime + n.t);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + n.t + n.d);
      o.start(ctx.currentTime + n.t);
      o.stop(ctx.currentTime + n.t + n.d);
    });
  } catch(e) {}
}

async function pollLiveUpdates() {
  try {
    const resp = await fetch("/api/v1/live", {cache: "no-store"});
    const data = await resp.json();
    if (data.status !== "ok" || !data.data) return;
    let changed = false;
    let goals = [];
    data.data.forEach(lm => {
      // Find match by schedule_id (fixture_id in our data)
      const m = matchData.find(x => String(x.fixture_id) === String(lm.schedule_id) || String(x.schedule_id) === String(lm.schedule_id));
      if (!m) return;
      // Track score change
      const key = lm.schedule_id;
      const prev = _livePrevScores[key];
      const curScore = lm.home_score + "-" + lm.away_score;
      if (prev && prev !== curScore) {
        goals.push({fid: m.fixture_id, score: curScore, home: lm.home_score, away: lm.away_score});
      }
      _livePrevScores[key] = curScore;
      // Update match data
      if (m.status !== "live") {
        m.status = "live";
        changed = true;
      }
      if (m.minute !== lm.minute) { m.minute = lm.minute; changed = true; }
      if (m.home_score !== lm.home_score) { m.home_score = lm.home_score; changed = true; }
      if (m.away_score !== lm.away_score) { m.away_score = lm.away_score; changed = true; }
      if (lm.home_ht_score != null) m.home_ht_score = lm.home_ht_score;
      if (lm.away_ht_score != null) m.away_ht_score = lm.away_ht_score;
    });
    if (changed) {
      renderMatches();
      updateSummaryFromData();
    }
    // Goal alerts
    goals.forEach(g => {
      const row = document.querySelector(`tr[data-fid="${g.fid}"]`);
      if (row) {
        row.classList.remove("goal-flash");
        void row.offsetWidth;
        row.classList.add("goal-flash");
      }
      _liveBeep();
    });
  } catch(e) {
    // silently retry next cycle
  }
}

function updateSummaryFromData() {
  const s = {total: matchData.length, live: 0, not_started: 0, finished: 0, postponed: 0, cancelled: 0};
  matchData.forEach(m => { s[m.status] = (s[m.status]||0) + 1; });
  document.getElementById("sumTotal").textContent = s.total;
  document.getElementById("sumLive").textContent = s.live;
  document.getElementById("sumWaiting").textContent = s.not_started;
  document.getElementById("sumDone").textContent = s.finished;
}

function startLivePolling() {
  if (_livePollTimer) clearInterval(_livePollTimer);
  pollLiveUpdates();
  _livePollTimer = setInterval(pollLiveUpdates, 20000);
}

// Toggle sound button (added next to refresh)
function toggleLiveSound() {
  _liveSoundOn = !_liveSoundOn;
  const btn = document.getElementById("soundToggleBtn");
  if (btn) btn.textContent = _liveSoundOn ? String.fromCharCode(0xD83D,0xDD0A) : String.fromCharCode(0xD83D,0xDD07);
}
"""

# HTML to inject sound toggle button - we'll add it via JS in startLivePolling
SOUND_BTN_JS = """
// Add sound toggle button
(function(){
  const refreshBtn = document.querySelector(".refresh-btn") || document.getElementById("refreshBtn");
  if (refreshBtn && !document.getElementById("soundToggleBtn")) {
    const btn = document.createElement("button");
    btn.id = "soundToggleBtn";
    btn.className = refreshBtn.className;
    btn.style.cssText = "margin-left:8px;font-size:1rem;cursor:pointer;";
    btn.textContent = _liveSoundOn ? String.fromCharCode(0xD83D,0xDD0A) : String.fromCharCode(0xD83D,0xDD07);
    btn.onclick = toggleLiveSound;
    refreshBtn.parentNode.insertBefore(btn, refreshBtn.nextSibling);
  }
})();
"""

def main():
    with open(HTML, "r", encoding="utf-8") as f:
        src = f.read()

    if "pollLiveUpdates" in src:
        print("[SKIP] live polling already present")
        return

    # 1. Insert CSS before </style>
    if "</style>" in src:
        src = src.replace("</style>", CSS_BLOCK + "\n</style>", 1)
    else:
        print("[WARN] no </style> found, CSS not inserted")

    # 2. Insert JS before </body> or at end
    js_full = JS_BLOCK + "\n" + SOUND_BTN_JS + "\nstartLivePolling();\n"
    if "</body>" in src:
        src = src.replace("</body>", "<script>\n" + js_full + "\n</script>\n</body>", 1)
    elif "</html>" in src:
        src = src.replace("</html>", "<script>\n" + js_full + "\n</script>\n</html>", 1)
    else:
        src += "\n<script>\n" + js_full + "\n</script>\n"

    with open(HTML, "w", encoding="utf-8") as f:
        f.write(src)

    # Basic JS syntax check using node if available
    import subprocess
    try:
        r = subprocess.run(["node", "--check", HTML], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            print(f"[WARN] node check: {r.stderr[:300]}")
    except FileNotFoundError:
        pass

    print(f"[OK] live polling patch applied ({len(js_full)} chars JS + {len(CSS_BLOCK)} chars CSS)")

if __name__ == "__main__":
    main()
