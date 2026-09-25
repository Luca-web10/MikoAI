import subprocess, threading, time, os, sys, socket, webbrowser, urllib.request, secrets
import hashlib, hmac as _hmac, json
from http.server import BaseHTTPRequestHandler, HTTPServer

os.chdir(os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, 'frozen', False) else __file__)))

EXE   = os.path.join("bin", "llama-server.exe")
MODEL = os.path.join("models", "model.gguf")

DRIVE = os.path.splitdrive(os.getcwd())[0].upper()
PORT = 8765 + (ord(DRIVE[0]) - ord('C'))
CTRL = PORT + 100
URL  = f"http://127.0.0.1:{PORT}"

# ===== TEMPLATE GEMMA 3 ĐÚNG CHUẨN =====
# Gemma chỉ hiểu vai "user" và "model" — KHÔNG có "system".
# Tin system sẽ được gói vào lượt user đầu tiên (đúng quy ước chính thức của Gemma 3).
GEMMA3_TEMPLATE = (
    "{% for message in messages %}"
    "{% if message['role'] == 'system' %}"
    "{{ '<start_of_turn>user\\n' + message['content'] + '<end_of_turn>\\n' }}"
    "{% elif message['role'] == 'user' %}"
    "{{ '<start_of_turn>user\\n' + message['content'] + '<end_of_turn>\\n' }}"
    "{% elif message['role'] == 'assistant' %}"
    "{{ '<start_of_turn>model\\n' + message['content'] + '<end_of_turn>\\n' }}"
    "{% endif %}"
    "{% endfor %}"
    "{% if add_generation_prompt %}{{ '<start_of_turn>model\\n' }}{% endif %}"
)

proc = None
quit_event = threading.Event()

# ==================== BẢO MẬT: NIÊM PHONG ====================

COVER_DIRS = ("bin", "ui", "licenses")

def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _derive(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)

def _build_manifest(folder):
    manifest = {}
    for sub in COVER_DIRS:
        d = os.path.join(folder, sub)
        if not os.path.isdir(d): continue
        for root, _, files in os.walk(d):
            for fn in files:
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, folder).replace("\\", "/")
                try: manifest[rel] = _sha256_file(p)
                except Exception: pass
    return manifest

def reseal(folder, password):
    manifest = _build_manifest(folder)
    salt = secrets.token_bytes(16)
    key = _derive(password, salt)
    payload = json.dumps(manifest, sort_keys=True).encode()
    secure = {"v": 1, "salt": salt.hex(),
              "sig": _hmac.new(key, payload, hashlib.sha256).hexdigest(),
              "files": manifest}
    with open(os.path.join(folder, "secure.json"), "w", encoding="utf-8") as f:
        json.dump(secure, f, indent=2)

def check_seal():
    sp = os.path.join(os.getcwd(), "secure.json")
    if not os.path.exists(sp): return None
    try:
        with open(sp, encoding="utf-8") as f:
            data = json.load(f)
        manifest = data["files"]
        for rel, expected in manifest.items():
            p = os.path.join(os.getcwd(), rel.replace("/", os.sep))
            if not os.path.exists(p):
                return {"status": "tampered", "detail": f"Thiếu file: {rel}"}
            if _sha256_file(p) != expected:
                return {"status": "tampered", "detail": f"File bị thay đổi: {rel}"}
        current = _build_manifest(os.getcwd())
        for rel in current:
            if rel not in manifest:
                return {"status": "tampered",
                        "detail": f"File lạ không có trong niêm phong: {rel}"}
        return {"status": "ok"}
    except Exception:
        return {"status": "tampered", "detail": "secure.json hỏng"}

def password_ok(password, secure_data):
    try:
        salt = bytes.fromhex(secure_data["salt"])
        key = _derive(password, salt)
        payload = json.dumps(secure_data["files"], sort_keys=True).encode()
        return _hmac.new(key, payload, hashlib.sha256).hexdigest() == secure_data["sig"]
    except Exception:
        return False

def load_seal():
    sp = os.path.join(os.getcwd(), "secure.json")
    try:
        with open(sp, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

# ---------- Cửa sổ bảo trì pywebview ----------

HTML_GATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font-family:'Segoe UI',sans-serif;background:#FFF9F1;color:#4A3A2E;
  display:grid;place-items:center;height:100vh;margin:0}
.card{background:#fff;border:1px solid rgba(190,140,90,.25);border-radius:18px;
  padding:26px;box-shadow:0 20px 50px rgba(190,130,70,.2);max-width:340px;text-align:center}
h2{font-family:Georgia,serif;margin:6px 0 8px}
.lock{font-size:40px}
.warn{font-size:12.5px;color:#94816F;line-height:1.55;margin-bottom:12px}
.err{background:#FDECEC;border:1px solid #E07856;color:#D95F3B;border-radius:10px;
  padding:8px;font-size:13px;margin-bottom:12px}
input{width:100%;padding:12px;border:1.5px solid rgba(190,140,90,.3);border-radius:12px;
  font-size:15px;box-sizing:border-box;text-align:center;letter-spacing:2px;outline:none}
input:focus{border-color:#E9A84E;box-shadow:0 0 0 3px rgba(233,168,78,.18)}
button{width:100%;margin-top:12px;padding:12px;border:none;border-radius:12px;
  background:linear-gradient(135deg,#F3B95F,#F0977B);color:#fff;font-weight:700;
  font-size:15px;cursor:pointer;font-family:inherit}
button:hover{filter:brightness(1.06)}
small{color:#B7A492;font-size:11px}
</style></head><body>
<div class="card">
  <div class="lock">🔒</div>
  <h2>MikoAI — Bảo mật</h2>
  <div class="warn">Phát hiện sản phẩm đã bị thay đổi.<br>
  <b>Nếu bạn đang bảo trì:</b> hoàn tất chỉnh sửa file TRƯỚC khi nhập mật khẩu.<br>
  <small>(Chỉ đội ngũ MikoAI có mật khẩu — liên hệ ct4s.teams@gmail.com)</small></div>
  {ERR}
  <input id="pw" type="password" placeholder="Mật khẩu bảo trì" autocomplete="off">
  <button onclick="go()">Xác thực</button>
</div>
<script>
document.getElementById('pw').focus();
document.getElementById('pw').addEventListener('keydown',e=>{
  if(e.key==='Enter')go()});
function go(){pywebview.api.submit(document.getElementById('pw').value)}
</script></body></html>"""

HTML_LOCKED = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font-family:'Segoe UI',sans-serif;background:#FFF9F1;color:#4A3A2E;
  display:grid;place-items:center;height:100vh;margin:0}
.card{background:#fff;border:1px solid rgba(190,140,90,.25);border-radius:18px;
  padding:34px;box-shadow:0 20px 50px rgba(190,130,70,.2);max-width:360px;text-align:center}
h2{font-family:Georgia,serif;margin:8px 0}
</style></head><body>
<div class="card">
  <div style="font-size:48px">🔒</div>
  <h2>Sản phẩm tạm khóa</h2>
  <p style="color:#94816F;font-size:14px;line-height:1.6">Sai mật khẩu 3 lần.<br>
  Liên hệ đội ngũ MikoAI:<br><b>ct4s.teams@gmail.com</b></p>
</div></body></html>"""

def maintenance_gate_web(error_msg):
    import webview
    result = {"pw": None}
    err_html = f'<div class="err">{error_msg}</div>' if error_msg else ''
    html = HTML_GATE.replace("{ERR}", err_html)

    class Api:
        def submit(self, pw):
            result["pw"] = pw
            for w in webview.windows:
                try: w.destroy()
                except Exception: pass
        def cancel(self):
            for w in webview.windows:
                try: w.destroy()
                except Exception: pass

    webview.create_window("MikoAI — Bảo mật", html=html, js_api=Api(),
                          width=430, height=440, on_top=True, resizable=False)
    webview.start(private_mode=True)
    return result["pw"]

def show_locked_screen():
    import webview
    webview.create_window("MikoAI", html=HTML_LOCKED,
                          width=400, height=300, on_top=True, resizable=False)
    webview.start(private_mode=True)

def run_maintenance_loop():
    data = load_seal()
    if not data:
        error_box("secure.json hỏng — cần niêm phong lại từ máy chủ.")
        return False
    detail = ""
    attempts = 0
    while attempts < 3:
        pw = maintenance_gate_web(detail)
        if not pw:
            return False
        if password_ok(pw, data):
            reseal(os.getcwd(), pw)
            return True
        attempts += 1
        detail = f"Mật khẩu không đúng (lần {attempts}/3)"
    show_locked_screen()
    return False

# ==================== TIỆN ÍCH ====================

def port_open(p):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", p)) == 0

def http_ok():
    try:
        with urllib.request.urlopen(URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False

def wait_healthy(max_half_seconds):
    for _ in range(max_half_seconds):
        if http_ok(): return True
        if quit_event.is_set(): return False
        if proc is not None and proc.poll() is not None: return False
        time.sleep(0.5)
    return False

def kill_zombie():
    try:
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"],
                       capture_output=True, timeout=10)
        time.sleep(2)
    except Exception: pass

def error_box(msg):
    try:
        import webview
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{font-family:'Segoe UI',sans-serif;background:#FFF9F1;color:#4A3A2E;
display:grid;place-items:center;height:100vh;margin:0;text-align:center}}
.card{{background:#fff;border:1px solid rgba(190,140,90,.25);border-radius:18px;
padding:30px;max-width:380px;box-shadow:0 20px 50px rgba(190,130,70,.2)}}
</style></head><body><div class="card"><div style="font-size:42px">⚠️</div>
<p style="line-height:1.6">{safe}</p></div></body></html>"""
        webview.create_window("MikoAI", html=html, width=440, height=320, on_top=True)
        webview.start(private_mode=True)
        return
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk(); r.withdraw()
        messagebox.showerror("MikoAI", msg)
    except Exception: pass

# ==================== CỔNG ĐIỀU KHIỂN ====================

class Ctrl(BaseHTTPRequestHandler):
    def _bye(self):
        quit_event.set()
        self.send_response(200); self.end_headers()
        try: self.wfile.write(b"bye")
        except Exception: pass
    def do_GET(self):
        if self.path.startswith("/quit"): self._bye()
        else: self.send_response(404); self.end_headers()
    def do_POST(self): self.do_GET()
    def log_message(self, *a): pass

def start_ctrl():
    if not port_open(CTRL):
        threading.Thread(
            target=lambda: HTTPServer(("127.0.0.1", CTRL), Ctrl).serve_forever(),
            daemon=True).start()

# ==================== CỬA SỔ APP ====================

def show_window():
    try:
        import webview
        class Api:
            def quit(self):
                quit_event.set()
                for w in webview.windows:
                    try: w.destroy()
                    except Exception: pass
        webview.create_window("MikoAI", URL + "/?v=" + str(int(time.time())),
                              width=1040, height=750,
                              min_size=(430, 560), js_api=Api())
        webview.start(private_mode=False,
                      storage_path=os.path.join(os.getcwd(), 'MikoAI-data'))
        return True
    except Exception:
        try: os.startfile(URL)
        except Exception: webbrowser.open(URL)
        return False

# ==================== MAIN ====================

def main():
    global proc
    start_ctrl()

    seal = check_seal()
    if seal and seal["status"] != "ok":
        if not run_maintenance_loop():
            sys.exit(1)

    if port_open(PORT):
        if http_ok():
            show_window()
            sys.exit(0)
        if wait_healthy(240):
            show_window(); sys.exit(0)
        kill_zombie()

    if not os.path.exists(EXE) or not os.path.exists(MODEL):
        error_box("Thiếu file hệ thống (bin/ hoặc models/).\nHãy bảo đảm thư mục đầy đủ.")
        sys.exit(1)

    proc = subprocess.Popen(
        [EXE, "-m", MODEL, "-c", "4096", "-t", str(os.cpu_count() or 4),
         "--chat-template", GEMMA3_TEMPLATE,
         "--port", str(PORT), "--path", "ui"],
        creationflags=subprocess.CREATE_NO_WINDOW)

    if not wait_healthy(240):
        if proc.poll() is not None:
            error_box("Không khởi động được trợ lý.\nRút USB, đợi 10 giây, cắm lại nhé.")
        else:
            error_box("Trợ lý khởi động quá lâu.\nRút USB, đợi 10 giây, cắm lại nhé.")
        sys.exit(1)

    try:
        if show_window():
            quit_event.set()
        else:
            while not quit_event.wait(2):
                if not http_ok() or proc.poll() is not None: break
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=5)
            except Exception: proc.kill()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            if proc and proc.poll() is None: proc.terminate()
        except Exception: pass