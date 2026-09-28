import json
import os
import sys

STATE_FILE = "state.json"

def get_clipboard_text():
    """Membaca isi clipboard secara otomatis di Windows/Linux tanpa library tambahan"""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        clipboard = root.clipboard_get()
        root.destroy()
        return clipboard.strip()
    except Exception:
        return ""

def create_state_from_cookie_string(cookie_str: str):
    """Mengubah format 'c_user=1000...; xs=...' menjadi state.json Playwright"""
    cookies = []
    pairs = [p.strip() for p in cookie_str.split(";") if "=" in p]
    for pair in pairs:
        name, val = pair.split("=", 1)
        cookies.append({
            "name": name.strip(),
            "value": val.strip(),
            "domain": ".facebook.com",
            "path": "/",
            "expires": -1,
            "httpOnly": False,
            "secure": True,
            "sameSite": "None"
        })
    return {"cookies": cookies, "origins": []}

def create_state_from_json(json_data):
    """Mendukung format array export dari ekstensi Cookie-Editor / EditThisCookie"""
    if isinstance(json_data, dict) and "cookies" in json_data:
        return json_data

    cookies = []
    for item in json_data:
        same_site = item.get("sameSite", "None")
        if same_site in ["no_restriction", "unspecified", None]:
            same_site = "None"
        elif same_site.lower() == "lax":
            same_site = "Lax"
        elif same_site.lower() == "strict":
            same_site = "Strict"
        elif same_site not in ["Strict", "Lax", "None"]:
            same_site = "None"

        cookies.append({
            "name": item.get("name", ""),
            "value": item.get("value", ""),
            "domain": item.get("domain", ".facebook.com"),
            "path": item.get("path", "/"),
            "expires": item.get("expirationDate", -1),
            "httpOnly": item.get("httpOnly", False),
            "secure": item.get("secure", True),
            "sameSite": same_site
        })
    return {"cookies": cookies, "origins": []}

def save_state(state_data):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2)
    print(f"\n[SUKSES] Berhasil menyimpan {len(state_data['cookies'])} cookies ke '{STATE_FILE}'!")
    print("Format telah disesuaikan sempurna untuk Playwright.")
    print("Sekarang Anda bisa langsung menjalankan scraper atau API.\n")

def main():
    print("=" * 65)
    print(" Import Cookie Facebook ke state.json (Otomatis & Fleksibel)")
    print("=" * 65)

    # 1. Cek apakah ada file cookies.json atau cookies.txt
    for fname in ["cookies.json", "cookies.txt"]:
        if os.path.exists(fname):
            print(f"[Info] Ditemukan file '{fname}', mencoba membaca...")
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content.startswith("[") or content.startswith("{"):
                    data = json.loads(content)
                    save_state(create_state_from_json(data))
                    return
                elif "c_user" in content:
                    save_state(create_state_from_cookie_string(content))
                    return
            except Exception as e:
                print(f"[Warning] Gagal membaca '{fname}': {e}")

    # 2. Cek apakah di Clipboard sudah ada data cookie
    cb_text = get_clipboard_text()
    if cb_text and ("c_user" in cb_text or ("[" in cb_text and "name" in cb_text)):
        print("\n[Terdeteksi] Ada cookie Facebook di Clipboard Anda!")
        choice = input("Gunakan cookie dari Clipboard sekarang? (Y/n): ").strip().lower()
        if choice in ["", "y", "ya", "yes"]:
            try:
                if cb_text.startswith("[") or cb_text.startswith("{"):
                    data = json.loads(cb_text)
                    save_state(create_state_from_json(data))
                    return
                else:
                    save_state(create_state_from_cookie_string(cb_text))
                    return
            except Exception as e:
                print(f"[Warning] Gagal membaca clipboard: {e}")

    # 3. Input manual jika tidak ada di clipboard/file
    print("\nSilakan tempel (paste) cookie Anda di bawah ini:")
    print("(Bisa berupa format JSON [ { ... } ] atau format teks 'c_user=...; xs=...')")
    print("Tekan ENTER lalu ketik 'DONE' dan tekan ENTER lagi jika selesai menempel:\n")

    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "DONE":
                break
            lines.append(line)
            # Jika user mem-paste single line text cookie
            if len(lines) == 1 and "c_user=" in line and ";" in line:
                break
        except EOFError:
            break

    full_input = "\n".join(lines).strip()
    if not full_input:
        print("[Batal] Tidak ada input cookie yang dimasukkan.")
        return

    try:
        if full_input.startswith("[") or full_input.startswith("{"):
            data = json.loads(full_input)
            save_state(create_state_from_json(data))
        else:
            save_state(create_state_from_cookie_string(full_input))
    except Exception as e:
        print(f"[Error] Format cookie tidak dikenali: {e}")

if __name__ == "__main__":
    main()
