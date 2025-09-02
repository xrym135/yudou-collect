import base64
import logging
import os
import random
import re
import sys
import time
import urllib.parse
import urllib3


import requests
from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Util.Padding import unpad
from lxml import etree

# ---------------- CONFIG ---------------- #
HOME_PAGE = "https://yudou.cook369.xyz/"
AES_PATTERN = r"U2FsdGVkX1[0-9A-Za-z+/=]+"
OUTPUT_DIR = OUTPUT_DIR = "../../dist/"
PASSWORD_RANGE = (1000, 9999)
DOWNLOAD_TIMEOUT = 30
REQUEST_DELAY = (2, 5)
# --------------------------------------- #

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

session = requests.Session()
session.verify = False


# ---------------- UTIL FUNCTIONS ---------------- #
def evp_bytes_to_key(password: str, salt: bytes, key_len: int = 32, iv_len: int = 16):
    """Derive key and IV using OpenSSL-compatible EVP_BytesToKey (MD5)."""
    derived = b""
    prev = b""
    password_bytes = password.encode("utf-8")
    while len(derived) < key_len + iv_len:
        prev = MD5.new(prev + password_bytes + salt).digest()
        derived += prev
    return derived[:key_len], derived[key_len : key_len + iv_len]


def decrypt(ciphertext: str, password: str) -> str:
    """Decrypt AES-CBC encrypted data (CryptoJS compatible)."""
    try:
        data = base64.b64decode(ciphertext)
        if not data.startswith(b"Salted__"):
            raise ValueError("Ciphertext missing 'Salted__' prefix")
        salt = data[8:16]
        cipher_bytes = data[16:]
        key, iv = evp_bytes_to_key(password, salt)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(cipher_bytes), AES.block_size)
        return decrypted.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Decryption failed: {e}")


def fetch_html(url: str) -> etree._Element:
    """Fetch HTML content and parse with lxml."""
    time.sleep(random.uniform(*REQUEST_DELAY))
    try:
        response = session.get(url, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status()
        return etree.HTML(response.text)
    except Exception as e:
        raise ConnectionError(f"Failed to fetch URL {url}: {e}")


def extract_encryption_data(page_etree: etree._Element) -> str:
    """Extract AES-encrypted string from page scripts."""
    scripts = page_etree.xpath("//script[contains(text(), 'U2FsdGVkX1')]/text()")
    if not scripts:
        raise ValueError("No encryption scripts found.")
    match = re.search(AES_PATTERN, scripts[0])
    if not match:
        raise ValueError("Failed to extract encryption data from script.")
    return match.group(0)


def brute_force_password(
    encrypted_data: str, start: int = PASSWORD_RANGE[0], end: int = PASSWORD_RANGE[1]
) -> str:
    """Brute-force AES password (4-digit numeric)."""
    for pwd in range(start, end + 1):
        try:
            decrypted = decrypt(encrypted_data, str(pwd))
            return urllib.parse.unquote(decrypted)
        except ValueError:
            continue
    raise ValueError("Failed to brute-force the encryption password.")


def parse_urls(decrypted_data: str) -> list[str]:
    """Extract URLs ending with .txt or .yaml from decrypted data."""
    urls = re.findall(r"https?://[^\s'\"<>]+?\.(?:txt|yaml)", decrypted_data)
    if not urls:
        raise ValueError("No downloadable URLs found.")
    return urls


def download_file(url: str, output_dir: str):
    """Download a single file to the output directory."""
    os.makedirs(output_dir, exist_ok=True)
    try:
        logging.info(f"Downloading: {url}")
        resp = session.get(url, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        ext = url.split(".")[-1]
        file_name = "v2ray.txt" if ext == "txt" else "clash.yaml"
        path = os.path.join(output_dir, file_name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        logging.info(f"Saved to: {path}")
    except Exception as e:
        logging.error(f"Failed to download {url}: {e}")


def download_files(urls: list[str], output_dir: str):
    """Download multiple files."""
    for url in urls:
        download_file(url, output_dir)


# ---------------- MAIN ---------------- #
def main():
    try:
        logging.info("Fetching homepage...")
        home_etree = fetch_html(HOME_PAGE)
        links = home_etree.xpath('//*[@id="main"]//a/@href')
        if not links:
            raise ValueError("No links found on homepage.")
        today_url = links[0]
        logging.info(f"Today's URL: {today_url}")

        logging.info("Fetching today's page...")
        today_etree = fetch_html(today_url)
        encrypted_data = extract_encryption_data(today_etree)
        logging.info("Encrypted data extracted.")

        decrypted_data = brute_force_password(encrypted_data)
        logging.info("Decryption successful.")

        urls = parse_urls(decrypted_data)
        logging.info(f"Found {len(urls)} URLs.")

        download_files(urls, OUTPUT_DIR)
        logging.info("All files downloaded successfully.")

    except Exception as e:
        logging.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
