from abc import ABC
from typing import List, Dict, Optional
import os
import requests
from playwright.sync_api import sync_playwright, Page
from apps.backend.crawler.config import DATA_OUTPUT_DIR, DOWNLOAD_DIR
from apps.backend.crawler.utils.card_matcher import CardMatcher


class BaseCrawler(ABC):
    def __init__(self, company_name: str, use_playwright: bool = True):
        self.company_name = company_name
        self.matcher = CardMatcher()
        self.use_playwright = use_playwright
        # Ensure directories exist
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)

    # Subclasses can override one or both of these hooks
    def find_pdf_links_playwright(self, page: Page) -> List[Dict]:
        raise NotImplementedError

    def find_pdf_links_requests(self) -> List[Dict]:
        raise NotImplementedError

    def download_pdf(
        self, page: Optional[Page], url_or_js: str, title: str, card_name: str
    ) -> Optional[str]:
        try:
            if page and url_or_js.startswith("/") and not url_or_js.startswith("//"):
                from urllib.parse import urljoin

                url_or_js = urljoin(page.url, url_or_js)

            # Sanitize filename
            safe_title = "".join(
                c for c in title if c.isalnum() or c in (" ", "-", "_")
            ).strip()
            safe_card = "".join(
                c for c in card_name if c.isalnum() or c in (" ", "-", "_")
            ).strip()
            filename = f"{self.company_name}_{safe_card}_{safe_title}.pdf"

            # Determine subfolder based on content
            subfolder = "manuals"
            if (
                "terms" in filename.lower()
                or "stpul" in url_or_js.lower()
                or "agreement" in url_or_js.lower()
            ):
                subfolder = "terms"
            elif "manual" in filename.lower() or "prdctopmn" in url_or_js.lower():
                subfolder = "manuals"

            # Create company-specific structure: datasets/pdfs/{company}/{subfolder}
            company_dir = os.path.join(
                DOWNLOAD_DIR, self.company_name.lower(), subfolder
            )
            os.makedirs(company_dir, exist_ok=True)

            filepath = os.path.join(company_dir, filename)

            if page:
                if url_or_js.startswith("http"):
                    try:
                        with page.expect_download(timeout=60000) as download_info:
                            try:
                                page.goto(url_or_js)
                            except Exception as e:
                                # Playwright throws this if the navigation becomes a download
                                if "Download is starting" not in str(
                                    e
                                ) and "net::ERR_ABORTED" not in str(e):
                                    raise e
                        download = download_info.value
                        download.save_as(filepath)
                    except Exception as e:
                        print(
                            f"Playwright download failed, falling back to requests: {e}"
                        )
                        # Fallback to requests
                        response = requests.get(url_or_js, stream=True, timeout=30)
                        response.raise_for_status()
                        with open(filepath, "wb") as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                elif url_or_js.startswith("js:"):
                    js_code = url_or_js.replace("js:", "")
                    with page.expect_download(timeout=60000) as download_info:
                        page.evaluate(js_code)
                    download = download_info.value
                    download.save_as(filepath)
                else:
                    with page.expect_download(timeout=60000) as download_info:
                        page.click(f"a[href='{url_or_js}']")
                    download = download_info.value
                    download.save_as(filepath)
            else:
                response = requests.get(url_or_js, stream=True, timeout=30)
                response.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

            return filepath
        except Exception as e:
            print(f"Error downloading {url_or_js}: {e}")
            return None

    def run(self):
        results = []
        if self.use_playwright:
            print(f"Starting Playwright crawler for {self.company_name}...")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                links = self.find_pdf_links_playwright(page)
                print(f"Found {len(links)} potential PDF links.")
                for link in links:
                    results.extend(self._process_link(page, link))
                browser.close()
        else:
            print(f"Starting requests crawler for {self.company_name}...")
            links = self.find_pdf_links_requests()
            print(f"Found {len(links)} potential PDF links.")
            for link in links:
                results.extend(self._process_link(None, link))
        return results

    def _process_link(self, page: Optional[Page], link: Dict) -> List[Dict]:
        output: List[Dict] = []
        title = link.get("title", "")
        url = link.get("url", "")
        card_name = link.get("card_name")
        if not card_name:
            card_name = self.matcher.find_best_match(self.company_name, [title, url])
        if not card_name:
            return output
        print(f"Processing target card PDF: {card_name} - {title}")
        local_path = self.download_pdf(page, url, title, card_name)
        if local_path:
            output.append(
                {
                    "company": self.company_name,
                    "card_name": card_name,
                    "pdf_title": title,
                    "source_url": url,
                    "local_path": local_path,
                }
            )
        return output
