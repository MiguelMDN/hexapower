#!/usr/bin/env python3
import argparse
import csv
import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

DEFAULT_UA = os.getenv(
    "HTTP_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "20"))
REQUEST_RETRY = int(os.getenv("REQUEST_RETRY", "3"))
REQUEST_SLEEP = float(os.getenv("REQUEST_SLEEP", "0.8"))

IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

@dataclass
class ProductRow:
    ref: str
    url: str


def read_csv(path: str) -> List[ProductRow]:
    rows: List[ProductRow] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ref = (r.get("ref") or r.get("REF") or r.get("sku") or "").strip()
            url = (r.get("url") or r.get("URL") or "").strip()
            if not ref or not url:
                continue
            rows.append(ProductRow(ref=ref, url=url))
    return rows


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    })
    return s


def request_with_retries(s: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    last_exc: Optional[Exception] = None
    for i in range(REQUEST_RETRY):
        try:
            resp = s.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            if resp.status_code in (429,) or resp.status_code >= 500:
                time.sleep(REQUEST_SLEEP * (i + 1))
                continue
            return resp
        except requests.RequestException as e:
            last_exc = e
            time.sleep(REQUEST_SLEEP * (i + 1))
    if last_exc:
        raise last_exc
    raise RuntimeError("request failed without exception")


def find_image_candidates(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    cands: List[str] = []

    # 1) OpenGraph
    for m in soup.select('meta[property="og:image"], meta[name="og:image"]'):
        if m.get("content"):
            cands.append(m["content"]) 

    # 2) link rel image_src
    for l in soup.select('link[rel="image_src"]'):
        if l.get("href"):
            cands.append(l["href"]) 

    # 3) Common product image selectors
    img_selectors = [
        "img#product", "img.product", "img.product-image", "img.wp-post-image",
        "img.attachment-shop_single", "img.zoomImg", "img.elevatezoom",
        "img.primary-photo", "img[class*='product']", "img[data-zoom-image]"
    ]
    for sel in img_selectors:
        for img in soup.select(sel):
            src = img.get("data-src") or img.get("data-large_image") or img.get("data-zoom-image") or img.get("src")
            if src:
                cands.append(src)

    # 4) Fallback: any <img>
    if not cands:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                cands.append(src)

    # Normalize, filter by image extensions, deduplicate preserving order
    norm: List[str] = []
    for u in cands:
        u = u.strip()
        if not u:
            continue
        absu = urllib.parse.urljoin(base_url, u)
        if any(absu.lower().split("?")[0].endswith(ext) for ext in IMG_EXTS):
            norm.append(absu)

    seen = set()
    uniq: List[str] = []
    for u in norm:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def filename_for(ref: str, url: str, idx: int) -> str:
    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lower() or ".jpg"
    clean_ref = re.sub(r"[^A-Za-z0-9_.-]", "-", ref)
    if idx == 0:
        return f"{clean_ref}{ext}"
    return f"{clean_ref}_{idx+1}{ext}"


def download_file(s: requests.Session, url: str, out_path: str) -> Tuple[bool, Optional[str]]:
    try:
        with s.get(url, stream=True, timeout=REQUEST_TIMEOUT) as r:
            r.raise_for_status()
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return True, None
    except Exception as e:
        return False, str(e)


def main():
    ap = argparse.ArgumentParser(description="Scraper de imágenes Wega a partir de CSV (ref,url)")
    ap.add_argument("--input-csv", required=True, help="CSV con columnas ref,url")
    ap.add_argument("--out-dir", default="data/wega_images", help="Directorio de salida de imágenes")
    ap.add_argument("--max-per-product", type=int, default=3, help="Máximo de imágenes por producto")
    ap.add_argument("--sleep", type=float, default=REQUEST_SLEEP, help="Espera entre requests")
    args = ap.parse_args()

    rows = read_csv(args.input_csv)
    if not rows:
        print("No se encontraron filas válidas en el CSV (se esperan columnas ref,url)")
        return

    s = session()

    total_downloaded = 0
    errors: List[Tuple[str, str]] = []

    for row in rows:
        try:
            resp = request_with_retries(s, "GET", row.url)
            if resp.status_code != 200:
                errors.append((row.ref, f"HTTP {resp.status_code}"))
                time.sleep(args.sleep)
                continue
            html = resp.text
            imgs = find_image_candidates(html, row.url)
            if not imgs:
                errors.append((row.ref, "No se encontraron imágenes"))
                time.sleep(args.sleep)
                continue
            for idx, img_url in enumerate(imgs[: args.max_per_product]):
                fname = filename_for(row.ref, img_url, idx)
                out_path = os.path.join(args.out_dir, fname)
                ok, err = download_file(s, img_url, out_path)
                if ok:
                    total_downloaded += 1
                else:
                    errors.append((row.ref, f"{img_url} -> {err}"))
            time.sleep(args.sleep)
        except Exception as e:
            errors.append((row.ref, str(e)))
            time.sleep(args.sleep)

    print(f"Descargas completadas: {total_downloaded}")
    if errors:
        print("Errores:")
        for ref, msg in errors:
            print(f" - {ref}: {msg}")

if __name__ == "__main__":
    main()