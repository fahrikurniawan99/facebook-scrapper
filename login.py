import os
import sys
from playwright.sync_api import sync_playwright

STATE_FILE = "state.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def login_and_save_session():
    print("=" * 65)
    print(" Facebook Login & Session Saver (Stealth Mode)")
    print("=" * 65)
    print("1. Jendela browser Chrome akan terbuka dalam mode anti-deteksi bot.")
    print("2. Halaman 2FA (Verifikasi 2 Langkah) sekarang dapat dimuat normal.")
    print("3. Silakan masukkan kode 2FA / approve login di browser.")
    print("4. Setelah berhasil masuk ke Beranda Facebook, tekan ENTER di sini.")
    print("=" * 65)

    with sync_playwright() as p:
        # Jalankan Google Chrome asli yang terpasang di sistem
        try:
            browser = p.chromium.launch(
                channel="chrome",  # Gunakan browser Chrome asli
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox"
                ]
            )
        except Exception:
            # Fallback jika channel chrome gagal
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars"
                ]
            )

        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 850}
        )

        # Hapus flag navigator.webdriver agar Meta tidak memblokir halaman 2FA
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = context.new_page()

        print("\n-> Membuka halaman login Facebook...")
        page.goto("https://www.facebook.com", wait_until="domcontentloaded")

        input("\n[Tekan ENTER di sini SETELAH Anda berhasil masuk ke Beranda Facebook...]")

        # Simpan state (cookies & storage)
        context.storage_state(path=STATE_FILE)
        print(f"\n[SUKSES] Sesi login berhasil disimpan ke: {STATE_FILE}")

        browser.close()

if __name__ == "__main__":
    try:
        login_and_save_session()
    except Exception as e:
        print(f"[Error]: {e}", file=sys.stderr)
