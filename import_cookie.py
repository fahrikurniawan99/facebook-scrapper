import json
import os
import sys

STATE_FILE = "state.json"

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
        if same_site not in ["Strict", "Lax", "None"]:
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

def main():
    print("=" * 65)
    print(" Import Cookie Facebook ke state.json (Opsi Tanpa Login Manual)")
    print("=" * 65)
    print("Jika Anda sudah login di Google Chrome biasa dan ingin langsung pakai:")
    print("1. Salin cookie Facebook Anda (bisa berupa teks 'c_user=...; xs=...'")
    print("   atau export JSON dari ekstensi 'Cookie-Editor').")
    print("=" * 65)

    input_text = input("Tempel (Paste) teks cookie atau JSON di sini:\n").strip()
    if not input_text:
        print("[Batal] Tidak ada input.")
        return

    try:
        if input_text.startswith("[") or input_text.startswith("{"):
            parsed_json = json.loads(input_text)
            state_data = create_state_from_json(parsed_json)
        else:
            state_data = create_state_from_cookie_string(input_text)

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2)

        print(f"\n[SUKSES] Berhasil menyimpan {len(state_data['cookies'])} cookies ke '{STATE_FILE}'!")
        print("Sekarang Anda bisa langsung menjalankan 'python scraper.py' tanpa perlu login lagi.")
    except Exception as e:
        print(f"[Error] Gagal membaca format cookie: {e}")

if __name__ == "__main__":
    main()
