# -*- coding: utf-8 -*-
r"""MikoAI Factory — niêm phong USB bằng mật khẩu đơn hàng
Cách dùng:
  python factory.py                       → nhập tay
  python factory.py G:\USB_AI MKO-AB12CD34
Lưu ý: đường dẫn có dấu cách phải đặt trong ngoặc kép: "H:\Miko AI"
"""
import os, sys, json, hashlib, hmac, secrets

COVER_DIRS = ("bin", "ui", "licenses")   # thư mục được bảo vệ

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def derive(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)

def build_manifest(folder):
    manifest = {}
    for sub in COVER_DIRS:
        d = os.path.join(folder, sub)
        if not os.path.isdir(d): continue
        for root, _, files in os.walk(d):
            for fn in files:
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, folder).replace("\\", "/")
                try: manifest[rel] = sha256_file(p)
                except Exception: pass
    return manifest

def sign(folder, password):
    manifest = build_manifest(folder)
    salt = secrets.token_bytes(16)
    key = derive(password, salt)
    payload = json.dumps(manifest, sort_keys=True).encode()
    secure = {"v": 1, "salt": salt.hex(),
              "sig": hmac.new(key, payload, hashlib.sha256).hexdigest(),
              "files": manifest}
    with open(os.path.join(folder, "secure.json"), "w", encoding="utf-8") as f:
        json.dump(secure, f, indent=2)
    print(f"✅ Đã niêm phong {len(manifest)} file bằng mật khẩu {password[:4]}****")
    print(f"   → secure.json tại: {os.path.join(folder, 'secure.json')}")

if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else input("Thư mục USB (VD G:/USB_AI): ").strip()
    password = sys.argv[2] if len(sys.argv) > 2 else input("Mật khẩu bảo trì (từ đơn hàng): ").strip()
    if not os.path.isdir(folder):
        print("❌ Không tìm thấy thư mục:", folder)
        print('   💡 Gợi ý: đường dẫn có dấu cách? Đặt trong ngoặc kép: "H:\\Miko AI"')
        sys.exit(1)
    if not os.path.isfile(os.path.join(folder, "MikoAI.exe")):
        print("⚠️  Cảnh báo: không thấy MikoAI.exe trong thư mục này —")
        print("   bảo đảm bạn trỏ đúng thư mục gốc của sản phẩm (chứa exe + bin/ui/models).")
    if len(password) < 8:
        print("❌ Mật khẩu phải từ 8 ký tự"); sys.exit(1)
    sign(folder, password)