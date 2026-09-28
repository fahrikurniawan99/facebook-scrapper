import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime
import pandas as pd
from playwright.sync_api import sync_playwright

STATE_FILE = "state.json"
DEFAULT_GROUP_URL = "https://www.facebook.com/groups/2297926400597415"

JS_FEED_EXTRACTOR = """
() => {
    const feed = document.querySelector('div[role="feed"]');
    if (!feed) return [];

    const cards = Array.from(feed.children);
    const results = [];

    cards.forEach((card) => {
        const fullText = (card.innerText || "").trim();
        if (fullText.length < 25) return;
        if (fullText.startsWith("Tulis sesuatu...") || fullText.includes("Buat postingan publik")) return;

        // 1. Penulis (Author)
        let author = "";
        let authorUrl = "";
        
        const h2 = card.querySelector('h2, h3');
        if (h2) {
            author = (h2.innerText || "").trim().split('\\n')[0];
        }
        
        const authorLink = card.querySelector('h2 a, h3 a, a[href*="__tn__=-UC"], a[href*="/user/"], a[href*="profile.php"]');
        if (authorLink) {
            if (!author) {
                author = (authorLink.innerText || "").trim().split('\\n')[0];
            }
            authorUrl = authorLink.href.split('?')[0];
        }

        if (!author) {
            if (fullText.includes("Peserta anonim") || fullText.includes("Anonymous participant")) {
                author = "Peserta anonim";
            }
        }
        
        const postLinkMatch = card.innerHTML.match(/\\/posts\\/(\\d+)/);
        if (!author && !postLinkMatch) return;

        // 2. Post URL & Waktu Post
        let postUrl = "";
        if (postLinkMatch) {
            postUrl = `https://www.facebook.com/groups/2297926400597415/posts/${postLinkMatch[1]}/`;
        }

        let postTime = "";
        const lines = fullText.split('\\n').map(l => l.trim()).filter(l => l.length > 0 && l !== "Facebook");
        
        const timeRegex = /^(\\d+\\s*(menit|jam|hari|dtk|minggu|detik|hr|m|h|d|w)|kemarin|sehari|baru saja|just now)/i;
        for (let i = 0; i < Math.min(lines.length, 6); i++) {
            if (timeRegex.test(lines[i])) {
                postTime = lines[i];
                break;
            }
        }

        // 3. Teks Postingan
        let postText = "";
        const msgDiv = card.querySelector('div[data-ad-preview="message"], div[data-ad-comet-preview="message"]');
        if (msgDiv) {
            postText = (msgDiv.innerText || "").trim();
        } else {
            let capturing = false;
            const textLines = [];
            for (const line of lines) {
                if (line === postTime || line === "·" || line === "Dibagikan kepada Grup publik") {
                    capturing = true;
                    continue;
                }
                if (capturing) {
                    if (/^\\d+$/.test(line) || line.includes("Lihat komentar") || line.includes("Suka") || line.includes("Komentari sebagai")) {
                        break;
                    }
                    textLines.push(line);
                }
            }
            postText = textLines.join("\\n").replace(/Lihat selengkapnya|See more/gi, '').trim();
        }

        // 4. Jumlah Likes & Total Komentar FB
        let likes = 0;
        let totalComments = 0;
        const reactionMatch = fullText.match(/(\\d+[\\d.,]*)\\s*\\n\\s*(\\d+[\\d.,]*)\\s*\\n\\s*Lihat/i);
        if (reactionMatch) {
            likes = reactionMatch[1];
            totalComments = reactionMatch[2];
        } else {
            const comM = fullText.match(/(\\d+[\\d.,]*)\\s*(komentar|jawaban|comments)/i);
            if (comM) totalComments = comM[1];
            const likeM = fullText.match(/(\\d+[\\d.,]*)\\s*(reaksi|suka|likes)/i);
            if (likeM) likes = likeM[1];
        }

        // 5. Gambar / Foto Lampiran Postingan
        const imgUrls = [];
        const imgs = Array.from(card.querySelectorAll('img'));
        imgs.forEach(img => {
            const src = img.src || "";
            const width = img.naturalWidth || img.width || 0;
            const height = img.naturalHeight || img.height || 0;
            const isSmall = (width > 0 && width <= 45) || (height > 0 && height <= 45);
            const isEmoji = src.includes("emoji.php") || src.includes("rsrc.php");
            if (src.startsWith("http") && !isEmoji && !isSmall && !src.includes("data:image")) {
                if (!imgUrls.includes(src)) imgUrls.push(src);
            }
        });

        results.push({
            penulis: author,
            waktu_post: postTime,
            teks_postingan: postText,
            jumlah_suka: likes,
            total_komentar_fb: parseInt(totalComments) || 0,
            url_post: postUrl,
            url_profil: authorUrl,
            url_gambar: imgUrls.join(" | ")
        });
    });

    return results;
}
"""

def parse_args():
    parser = argparse.ArgumentParser(description="Facebook Group Scraper (1 Row Postingan + Lengkap Semua Komentar)")
    parser.add_argument("--url", type=str, default=DEFAULT_GROUP_URL, help="URL Group Facebook yang ingin di-scrape")
    parser.add_argument("--scrolls", type=int, default=10, help="Jumlah putaran auto-scroll feed (default: 10)")
    parser.add_argument("--delay", type=float, default=2.5, help="Jeda waktu (detik) antar scroll (default: 2.5)")
    parser.add_argument("--headless", action="store_true", help="Jalankan browser di latar belakang (tanpa jendela)")
    return parser.parse_args()

def expand_see_more(page):
    """Klik tombol 'Lihat selengkapnya' agar teks postingan panjang tidak terpotong."""
    try:
        see_more = page.locator('span:text-is("Lihat selengkapnya"), div[role="button"]:has-text("Lihat selengkapnya"), span:text-is("See more")')
        for i in range(min(see_more.count(), 8)):
            try:
                see_more.nth(i).click(force=True, timeout=800)
            except Exception:
                pass
    except Exception:
        pass

def fetch_post_all_comments(context, post_url: str) -> list:
    """Membuka halaman postingan dan mengambil seluruh komentar sampai tuntas."""
    if not post_url or "/posts/" not in post_url:
        return []

    tab = context.new_page()
    try:
        tab.goto(post_url, wait_until="domcontentloaded")
        tab.wait_for_timeout(3000)

        # 1. Ganti filter komentar "Paling relevan" -> "Semua komentar"
        relevan_btn = tab.locator('div[role="button"]:has(span:text-is("Paling relevan")), span:text-is("Paling relevan")')
        if relevan_btn.count() > 0:
            try:
                relevan_btn.first.click(force=True, timeout=1000)
                tab.wait_for_timeout(800)
                all_com_item = tab.locator('span:text-is("Semua komentar"), div[role="menuitem"]:has-text("Semua komentar")')
                if all_com_item.count() > 0:
                    all_com_item.first.click(force=True, timeout=1000)
                    tab.wait_for_timeout(2000)
            except Exception:
                pass

        # 2. Klik tombol "Lihat komentar sebelumnya / lainnya / balasan"
        for _ in range(6):
            btns = tab.locator('span:has-text("komentar lainnya"), span:has-text("komentar sebelumnya"), span:has-text("Lihat komentar"), span:has-text("Lihat balasan")')
            c = btns.count()
            if c == 0:
                break
            for i in range(min(c, 5)):
                try:
                    btns.nth(i).click(force=True, timeout=800)
                except Exception:
                    pass
            tab.wait_for_timeout(1000)

        # 3. Ekstrak seluruh komentar di halaman ini
        comments = tab.evaluate("""
            () => {
                const commentLinks = Array.from(document.querySelectorAll('a[href*="comment_id="]'));
                const list = [];
                const seen = new Set();
                commentLinks.forEach(cl => {
                    let p = cl.parentElement;
                    let userLink = null;
                    for (let i = 0; i < 8 && p; i++) {
                        userLink = p.querySelector('a[href*="/user/"], a[href*="profile.php"]');
                        if (userLink && (userLink.innerText || "").trim().length > 0) break;
                        p = p.parentElement;
                    }
                    const author = userLink ? (userLink.innerText || "").trim().split('\\n')[0] : "Anonim";
                    const time = (cl.innerText || "").trim();

                    let commentBox = p ? (p.closest('div[role="article"]') || p.parentElement?.parentElement || p.parentElement) : null;
                    let text = "";
                    if (commentBox) {
                        const textDivs = Array.from(commentBox.querySelectorAll('div[dir="auto"]'));
                        for (const td of textDivs) {
                            const txt = (td.innerText || "").trim();
                            if (txt && txt !== author && txt !== time && !txt.includes("Suka") && !txt.includes("Balas") && !txt.includes("Bagikan")) {
                                text = txt;
                                break;
                            }
                        }
                    }
                    if (text && !seen.has(author + "_" + text)) {
                        seen.add(author + "_" + text);
                        list.push({
                            pengomentar: author,
                            waktu: time,
                            teks: text
                        });
                    }
                });
                return list;
            }
        """)
        return comments
    except Exception as e:
        print(f"   [Warning] Gagal mengambil komentar {post_url}: {e}")
        return []
    finally:
        tab.close()

def scrape_group(url: str, max_scrolls: int, base_delay: float = 2.5, headless: bool = True, save_files: bool = True) -> list:
    if not os.path.exists(STATE_FILE):
        print(f"[Peringatan] File '{STATE_FILE}' belum ditemukan.")
        print("Silakan jalankan 'python login.py' atau 'python import_cookie.py' terlebih dahulu.\n")
        sys.exit(1)

    # Otomatis rapikan format state.json jika user mem-paste format array mentah
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                raw_state = json.load(f)
            if isinstance(raw_state, list):
                from import_cookie import create_state_from_json
                formatted_state = create_state_from_json(raw_state)
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(formatted_state, f, indent=2)
                print("[Info] Format state.json otomatis disesuaikan ke standar Playwright.")
        except Exception:
            pass

    print("=" * 75)
    print("Memulai Facebook Group Scraper (1 Row Postingan + Lengkap SEMUA Komentar)")
    print(f"Target URL   : {url}")
    print(f"Max Scrolls  : {max_scrolls}")
    print(f"Mode         : {'Headless' if headless else 'Visible Browser'}")
    print("=" * 75)

    os.makedirs("output", exist_ok=True)
    posts_dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-notifications",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars"
            ]
        )
        context = browser.new_context(
            storage_state=STATE_FILE,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 900}
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = context.new_page()

        print(f"\n[1/3] Membuka URL grup...")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        current_url = page.url
        print(f"[Debug] URL yang terbuka: {current_url}")

        # Otomatis tangani pop-up consent cookie jika muncul
        if "consent" in current_url.lower():
            print("[Info] Terdeteksi pop-up persetujuan cookie Facebook, menyetujui otomatis...")
            selectors = [
                'div[aria-label="Izinkan semua cookie"]',
                'div[role="button"]:has-text("Izinkan semua cookie")',
                'button:has-text("Izinkan semua cookie")',
                'div[aria-label="Allow all cookies"]',
                'button:has-text("Allow all cookies")',
                'div[role="button"]:has-text("Tolak cookie opsional")',
                'button:has-text("Tolak cookie opsional")'
            ]
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=1500):
                        el.click()
                        page.wait_for_timeout(4000)
                        context.storage_state(path=STATE_FILE)
                        current_url = page.url
                        print(f"[Debug] URL setelah persetujuan cookie: {current_url}")
                        break
                except Exception:
                    continue

        if "login" in current_url.lower() or "checkpoint" in current_url.lower():
            os.makedirs("output", exist_ok=True)
            page.screenshot(path="output/debug_login.png")
            print(f"[Error] Sesi Anda belum aktif atau dialihkan ke: {current_url}")
            print("Screenshot disimpan ke 'output/debug_login.png'")
            print("Jalankan 'python login.py' atau 'python import_cookie.py' ulang.")
            browser.close()
            return []

        print(f"[2/3] Memulai auto-scroll feed untuk mengumpulkan postingan...")

        last_height = page.evaluate("document.body.scrollHeight")

        for scroll_idx in range(1, max_scrolls + 1):
            expand_see_more(page)
            extracted_items = page.evaluate(JS_FEED_EXTRACTOR)

            new_in_step = 0
            for item in extracted_items:
                sig_base = f"{item['penulis']}_{item['teks_postingan'][:50]}_{item['url_post']}"
                item_hash = hashlib.md5(sig_base.encode('utf-8')).hexdigest()

                if item_hash not in posts_dict:
                    posts_dict[item_hash] = {
                        "id": item_hash[:10],
                        "penulis": item.get("penulis", ""),
                        "waktu_post": item.get("waktu_post", ""),
                        "teks_postingan": item.get("teks_postingan", ""),
                        "jumlah_suka": item.get("jumlah_suka", 0),
                        "total_komentar_fb": item.get("total_komentar_fb", 0),
                        "komentar_terkumpul": 0,
                        "semua_komentar": "",
                        "url_post": item.get("url_post", ""),
                        "url_profil": item.get("url_profil", ""),
                        "url_gambar": item.get("url_gambar", ""),
                        "daftar_komentar": [],
                        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    new_in_step += 1

            print(f"-> Scroll {scroll_idx}/{max_scrolls} | Post Baru: {new_in_step} | Total Post Feed: {len(posts_dict)}")

            # Scroll ke bawah feed grup
            page.evaluate("window.scrollBy(0, 1200)")

            sleep_time = base_delay + random.uniform(0.3, 1.0)
            page.wait_for_timeout(int(sleep_time * 1000))

            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
            last_height = new_height

        # 3. Ambil SEMUA komentar untuk setiap postingan yang memiliki komentar
        posts_list = list(posts_dict.values())
        print(f"\n[3/3] Mengambil SELURUH komentar secara lengkap untuk {len(posts_list)} postingan...")

        for idx, post in enumerate(posts_list, 1):
            if post["total_komentar_fb"] > 0 and post["url_post"]:
                print(f"   ({idx}/{len(posts_list)}) Mengambil semua komentar: {post['penulis']} ({post['total_komentar_fb']} komentar FB)...")
                all_comments = fetch_post_all_comments(context, post["url_post"])
                
                # Format string nomor
                formatted_comments = []
                for c_idx, c in enumerate(all_comments, 1):
                    w = f" ({c['waktu']})" if c.get('waktu') else ''
                    formatted_comments.append(f"[{c_idx}] {c['pengomentar']}{w}: {c['teks']}")
                
                post["komentar_terkumpul"] = len(all_comments)
                post["daftar_komentar"] = all_comments
                post["semua_komentar"] = "\n".join(formatted_comments)
                print(f"      [OK] Terkumpul: {len(all_comments)} komentar!")

        browser.close()

    if posts_list:
        if save_files:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_file = f"output/posts_{timestamp}.csv"
            json_file = f"output/posts_{timestamp}.json"
            excel_file = f"output/posts_{timestamp}.xlsx"

            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(posts_list, f, ensure_ascii=False, indent=2)

            table_rows = []
            for p in posts_list:
                row = dict(p)
                row.pop("daftar_komentar", None)
                table_rows.append(row)

            df = pd.DataFrame(table_rows)

            columns_order = [
                "id", "penulis", "waktu_post", "teks_postingan",
                "jumlah_suka", "total_komentar_fb", "komentar_terkumpul",
                "semua_komentar", "url_post", "url_profil",
                "url_gambar", "scraped_at"
            ]
            df = df[[c for c in columns_order if c in df.columns]]

            df.to_csv(csv_file, index=False, encoding="utf-8-sig")
            try:
                df.to_excel(excel_file, index=False)
                excel_saved = True
            except Exception:
                excel_saved = False

            print("\n" + "=" * 75)
            print(f"Sukses! {len(posts_list)} baris postingan lengkap dengan SELURUH komentar berhasil disimpan.")
            print(f" - CSV  : {csv_file}")
            print(f" - JSON : {json_file}")
            if excel_saved:
                print(f" - Excel: {excel_file}")
            print("=" * 75)
    else:
        print("\n[Perhatian] Tidak ada postingan yang berhasil diambil.")

    return posts_list

if __name__ == "__main__":
    args = parse_args()
    scrape_group(
        url=args.url,
        max_scrolls=args.scrolls,
        base_delay=args.delay,
        headless=args.headless,
        save_files=True
    )
