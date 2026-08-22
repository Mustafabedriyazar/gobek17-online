#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — HTTP controller + arka plan worker.

Uclar:
  POST /tasks          {build, task, mode?, provider?, dryRun?, noDeploy?} -> 202 {id}
                        mode: feature|fix|chore (yoksa feature). Gorev tipi
                        YALNIZCA bu alandan belirlenir; gorev metninden tip
                        cikarimi YAPILMAZ. mode=fix disinda REPRODUCE atlanir.
  GET  /tasks          son gorevler
  GET  /tasks/:id      tek gorev durumu (faz gecisleri dahil)
  GET  /status         servis + GitHub + production ozeti (SIR ICERMEZ)
  GET  /health         canlilik (kimlik istemez)

Yetki: Authorization: Bearer <G17_API_TOKEN>. Token yoksa ve G17_DEV_MODE
kapaliysa servis yazma uclarini REDDEDER (internete acik olacagi icin).
"""
import json
import queue
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .config import NAME, VERSION, Config
from .github_core import GitHubCore, GitHubError
from .maintenance import NO_REDO_STATES as MAINT_NO_REDO
from .maintenance import MaintenancePipeline, is_maintenance
from .pipeline import Pipeline
from .production import ProductionController
from .store import ReleaseLock, TaskStore, resolve_task_mode


# ============================================================================
# WEB KONSOLU — telefondan curl yazmadan gorev vermek icin.
# Token tarayicida localStorage'ta tutulur; sunucuya yalnizca Authorization
# basligiyla gider. Sayfa kimlik ISTEMEDEN servis edilir ama hicbir veri
# icermez; butun veri uclari yine token ister.
# ============================================================================
CONSOLE_HTML = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>G17 Cloud Agent</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
     background:#0f1115;color:#e7e9ee;padding:16px;max-width:720px;margin:0 auto}
h1{font-size:19px;margin:4px 0 2px}
.sub{color:#8b93a7;font-size:13px;margin-bottom:18px}
label{display:block;font-size:12px;color:#8b93a7;margin:14px 0 5px;letter-spacing:.04em;text-transform:uppercase}
input,textarea,select{width:100%;padding:12px;border-radius:10px;border:1px solid #2a2f3d;
     background:#161a22;color:#e7e9ee;font:inherit}
textarea{min-height:110px;resize:vertical}
button{width:100%;margin-top:16px;padding:14px;border:0;border-radius:10px;font:600 16px inherit;
     background:#3d7bfd;color:#fff}
button:disabled{opacity:.5}
.row{display:flex;gap:10px}.row>*{flex:1}
#out{margin-top:18px;padding:14px;border-radius:10px;background:#161a22;border:1px solid #2a2f3d;
     white-space:pre-wrap;font:13px/1.5 ui-monospace,Menlo,monospace;display:none}
.ph{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700}
.run{background:#2b3a55;color:#9dc0ff}.ok{background:#1e4030;color:#7ee2ac}.err{background:#4a2230;color:#ff9db0}
.ev{color:#8b93a7;font-size:12px}
</style></head><body>
<h1>G17 Cloud Agent</h1>
<div class="sub">Gorevi dogal dille yaz. Gerisi bulutta akar.</div>

<label>Erisim anahtari</label>
<input id="tok" type="password" placeholder="G17_API_TOKEN" autocomplete="current-password">

<div class="row">
  <div><label>Build</label><input id="build" placeholder="v171" value="v171"></div>
  <div><label>Saglayici</label><select id="prov">
    <option value="">otomatik</option><option value="fable">fable (buyuk is)</option>
    <option value="opus">opus (audit/hata)</option></select></div>
</div>

<label>Gorev</label>
<textarea id="task" placeholder="Ranked mac sonunda rating panelindeki hatayi duzelt ve yayinla"></textarea>

<div class="row">
  <div><label>Prova (dry-run)</label><select id="dry">
    <option value="0">hayir - yayinla</option><option value="1">evet - sadece dene</option></select></div>
</div>

<button id="go">GOREVI BASLAT</button>
<div id="out"></div>

<script>
var out=document.getElementById('out'),tok=document.getElementById('tok'),timer=null;
tok.value=localStorage.getItem('g17tok')||'';
tok.addEventListener('change',function(){localStorage.setItem('g17tok',tok.value)});
function show(h){out.style.display='block';out.innerHTML=h}
function esc(s){return String(s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
function hdrs(){return {'content-type':'application/json','Authorization':'Bearer '+tok.value}}
document.getElementById('go').onclick=async function(){
  var b=document.getElementById('build').value.trim(),t=document.getElementById('task').value.trim();
  if(!tok.value){return show('Once erisim anahtarini gir.')}
  if(!b||!t){return show('Build ve gorev bos olamaz.')}
  localStorage.setItem('g17tok',tok.value);
  this.disabled=true;show('Gorev gonderiliyor...');
  try{
    var body={build:b,task:t,dryRun:document.getElementById('dry').value==='1'};
    var pv=document.getElementById('prov').value; if(pv)body.provider=pv;
    var r=await fetch('/tasks',{method:'POST',headers:hdrs(),body:JSON.stringify(body)});
    var j=await r.json();
    if(!j.id){this.disabled=false;return show('Hata: '+esc(JSON.stringify(j)))}
    poll(j.id);
  }catch(e){this.disabled=false;show('Baglanti hatasi: '+esc(e.message))}
};
async function poll(id){
  clearTimeout(timer);
  try{
    var r=await fetch('/tasks/'+id,{headers:hdrs()}),j=await r.json(),k=j.task||{};
    var cls=k.status==='success'?'ok':(k.status==='failed'?'err':'run');
    var evs=(k.events||[]).slice(-8).map(function(e){
      return '<div class="ev">• '+esc(e.phase)+': '+esc(e.message)+'</div>'}).join('');
    show('<span class="ph '+cls+'">'+esc(k.status||'?')+'</span> '+esc(k.phase||'')+
         '<div style="margin-top:10px">'+evs+'</div>');
    if(k.status==='queued'||k.status==='running'){timer=setTimeout(function(){poll(id)},3000)}
    else{document.getElementById('go').disabled=false}
  }catch(e){timer=setTimeout(function(){poll(id)},5000)}
}
</script></body></html>"""

def log(*a):
    print("[g17]", *a, flush=True)


class Service:
    """Servis govdesi: kuyruk + worker thread'leri + kalici durum."""

    def __init__(self, cfg=None):
        self.cfg = cfg or Config()
        self.cfg.ensure_dirs()
        self.store = TaskStore(self.cfg.state_dir)
        self.lock = ReleaseLock(self.cfg.state_dir)
        self.q = queue.Queue()
        self.pipeline = Pipeline(self.cfg, self.store, self.lock, log=log)
        self.maintenance = MaintenancePipeline(self.cfg, self.store, self.lock, log=log)
        self.started_at = int(time.time())
        self.workers = []
        self._stop = threading.Event()

    # ------------------------------------------------------------------ worker
    def start_workers(self, n=2):
        for i in range(n):
            t = threading.Thread(target=self._worker, name="g17-worker-%d" % i, daemon=True)
            t.start()
            self.workers.append(t)

    def _worker(self):
        while not self._stop.is_set():
            try:
                tid = self.q.get(timeout=1)
            except queue.Empty:
                continue
            try:
                rec = self.store.get(tid) or {}
                if is_maintenance(rec.get("build")):
                    self.maintenance.run(tid)
                else:
                    self.pipeline.run(tid)
            except Exception:
                log("worker hatasi:", traceback.format_exc(limit=3))
                self.store.update(tid, status="failed", phase="INTERNAL")
            finally:
                self.q.task_done()

    def recover(self):
        """Restart sonrasi yarim kalan gorevleri kurtarir.

        Push EDILMIS ama dogrulanmamis gorevler yeniden kuyruga ALINMAZ
        (duplicate release riski); insan incelemesi icin isaretlenir.
        """
        recovered = []
        for rec in self.store.recoverable():
            # --- RESTART-SAFE SELF-UPDATE -------------------------------
            # Bakim gorevi push asamasindaysa edit/push TEKRARLANMAZ;
            # yalnizca dogrulama icin kuyruga alinir (MaintenancePipeline
            # NO_REDO_STATES gorunce resume() calistirir).
            if is_maintenance(rec.get("build")):
                st = ((rec.get("result") or {}).get("selfState"))
                if st in MAINT_NO_REDO:
                    self.store.update(rec["id"], status="queued",
                                      phase="resume:" + str(st))
                    self.q.put(rec["id"])
                    recovered.append((rec["id"], "resume:%s" % st))
                    continue
                self.store.update(rec["id"], status="queued", phase="requeued")
                self.q.put(rec["id"])
                recovered.append((rec["id"], "requeued"))
                continue
            if (rec.get("result") or {}).get("pushed"):
                self.store.update(rec["id"], status="needs_review",
                                  phase="RECOVERY_REQUIRES_REVIEW")
                recovered.append((rec["id"], "needs_review"))
                continue
            self.store.update(rec["id"], status="queued", phase="requeued")
            self.q.put(rec["id"])
            recovered.append((rec["id"], "requeued"))
        # Sahipsiz release kilidi: sahibi terminal duruma dusmusse birak
        holder = self.lock.holder()
        if holder:
            owner = self.store.get(holder.get("taskId") or "")
            if not owner or owner.get("status") in ("success", "failed", "cancelled"):
                self.lock.release(force=True)
        return recovered

    def submit(self, build, task, provider=None, dry_run=False, no_deploy=False, mode=None):
        rec = self.store.create(build, task, provider, dry_run, no_deploy, mode)
        self.q.put(rec["id"])
        return rec

    # ------------------------------------------------------------------ durum
    def status(self):
        gh = GitHubCore(self.cfg)
        try:
            try:
                auth = gh.auth_status()
            except Exception as ex:
                # /status TANI amaclidir; GitHub erisilemese bile 200 donmeli.
                auth = {"mode": "unknown", "read": "UNKNOWN", "write": "UNKNOWN",
                        "error": type(ex).__name__}
        except GitHubError as ex:
            auth = {"mode": "error", "error": str(ex)[:200]}
        prod = ProductionController(self.cfg)
        try:
            build = prod.current_build()
        except Exception:
            build = None
        holder = self.lock.holder()
        tasks = self.store.list(limit=20)
        return {
            "service": {"name": NAME, "version": VERSION,
                        "uptimeSec": int(time.time()) - self.started_at,
                        "queued": self.q.qsize(),
                        "workers": len(self.workers)},
            "config": self.cfg.public_dict(),
            "github": auth,
            "production": {"healthUrl": self.cfg.health_url, "build": build},
            "releaseLock": {"held": bool(holder),
                            "build": (holder or {}).get("build"),
                            "taskId": (holder or {}).get("taskId")},
            "tasks": {"recent": [{"id": t["id"], "build": t["build"],
                                  "status": t["status"], "phase": t["phase"]}
                                 for t in tasks]},
        }


def make_handler(svc: Service):
    class Handler(BaseHTTPRequestHandler):
        server_version = "G17CloudAgent/" + VERSION

        def log_message(self, fmt, *args):      # sessiz; kendi loglarimiz var
            pass

        # -------------------------------------------------------------- yardim
        def _send(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authed(self):
            tok = svc.cfg.api_token
            if not tok:
                return bool(svc.cfg.dev_mode)
            hdr = self.headers.get("Authorization", "")
            if not hdr.startswith("Bearer "):
                return False
            return secrets.compare_digest(hdr[7:].strip(), tok)

        def _body(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return {}
            if n <= 0 or n > 256 * 1024:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except (ValueError, OSError):
                return {}

        # -------------------------------------------------------------- GET
        def do_GET(self):
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path == "/":
                # Konsol sayfasi: veri ICERMEZ, yalnizca arayuz. Butun veri
                # uclari (POST /tasks, GET /tasks, /status) token ister.
                body = CONSOLE_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.send_header("x-content-type-options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/ready":
                # Saglayici durumu. Kimlik DEGERI asla dahil edilmez.
                mode = svc.cfg.ai_auth_mode()
                ready = mode != "AI_UNAUTHENTICATED"
                body = {
                    "ok": ready,
                    "provider": mode,
                    "aiProvider": svc.cfg.ai_provider,
                    "claudeConfigDir": svc.cfg.claude_config_dir,
                    "claudeHome": svc.cfg.claude_home,
                    # Abonelik kimligi nereden geliyor — DEGER degil, KAYNAK.
                    "subscriptionSource": ("setup-token" if svc.cfg.claude_oauth()
                                           else ("login-persisted" if svc.cfg.claude_credentials_on_disk()
                                                 else None)),
                    "apiKeyPresent": bool(svc.cfg.ai_key()),
                    # Abonelik yolu YALNIZ claude-cli uzerinden isler; CLI
                    # konteynerde yoksa bu yol sessizce kullanilamaz olur.
                    "claudeCli": _claude_cli_probe(svc.cfg),
                    "github": bool(svc.cfg.repo),
                    "hint": None if ready else
                            "Claude Pro/Max aboneligi icin: tarayicisi olan bir makinede "
                            "'claude setup-token' calistirin (bir kez), cikan token'i "
                            "CLAUDE_CODE_OAUTH_TOKEN degiskeni olarak girin. "
                            "ANTHROPIC_API_KEY ZORUNLU DEGILDIR, istege baglidir.",
                }
                return self._send(200 if ready else 503, body)
            if path == "/health":
                return self._send(200, {"ok": True, "name": NAME, "version": VERSION,
                                        "uptimeSec": int(time.time()) - svc.started_at})
            if not self._authed():
                return self._send(401, {"ok": False, "error": "unauthorized"})
            if path == "/status":
                return self._send(200, svc.status())
            if path == "/tasks":
                return self._send(200, {"ok": True, "tasks": svc.store.list(limit=50)})
            if path.startswith("/tasks/"):
                rec = svc.store.get(path.split("/")[-1])
                if not rec:
                    return self._send(404, {"ok": False, "error": "task bulunamadi"})
                return self._send(200, {"ok": True, "task": rec})
            return self._send(404, {"ok": False, "error": "bilinmeyen uc"})

        # -------------------------------------------------------------- POST
        def do_POST(self):
            path = urlparse(self.path).path.rstrip("/") or "/"
            if not self._authed():
                return self._send(401, {"ok": False, "error": "unauthorized"})
            if path != "/tasks":
                return self._send(404, {"ok": False, "error": "bilinmeyen uc"})
            b = self._body()
            build = str(b.get("build") or "").strip()
            task = str(b.get("task") or "").strip()
            if not build or not task:
                return self._send(400, {"ok": False,
                                        "error": "build ve task zorunlu"})
            try:
                if not is_maintenance(build):
                    int(build.lstrip("vV"))
            except ValueError:
                return self._send(400, {"ok": False,
                                        "error": "gecersiz build (ornek: v171 veya bakim)"})
            if is_maintenance(build) and not svc.cfg.maintenance_ready():
                return self._send(400, {"ok": False,
                                        "error": "bakim lane kapali: ajan reposu tanimli degil"})
            prov = (b.get("provider") or "auto").lower()
            if prov not in ("auto", "fable", "opus", "claude-cli", "mock"):
                return self._send(400, {"ok": False, "error": "gecersiz provider"})
            try:
                mode = resolve_task_mode(b.get("mode"))
            except ValueError:
                return self._send(400, {"ok": False, "error": "gecersiz mode"})
            rec = svc.submit(build, task, prov, bool(b.get("dryRun")),
                             bool(b.get("noDeploy")), mode)
            return self._send(202, {"ok": True, "id": rec["id"], "status": rec["status"],
                                    "poll": "/tasks/%s" % rec["id"]})

    return Handler


def serve(cfg=None):
    svc = Service(cfg)
    rec = svc.recover()
    if rec:
        log("kurtarilan gorev:", rec)
    svc.start_workers(int(2))
    httpd = ThreadingHTTPServer((svc.cfg.host, svc.cfg.port), make_handler(svc))
    log("%s %s dinliyor: %s:%d" % (NAME, VERSION, svc.cfg.host, svc.cfg.port))
    if not svc.cfg.api_token and not svc.cfg.dev_mode:
        log("UYARI: G17_API_TOKEN yok — yazma uclari REDDEDILECEK")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return svc


def _claude_cli_probe(cfg):
    """Konteynerde claude CLI var mi ve --tools destekliyor mu.
    Sir icermez; yalnizca varlik ve yol bilgisi doner."""
    import shutil as _sh
    try:
        from .ai_worker import ClaudeCLIProvider
        p = ClaudeCLIProvider(cfg)
        path = _sh.which(getattr(p, "command", "claude") or "claude")
        return {"path": path, "available": bool(path) and bool(p.available())}
    except Exception as ex:
        return {"path": None, "available": False,
                "error": type(ex).__name__}
