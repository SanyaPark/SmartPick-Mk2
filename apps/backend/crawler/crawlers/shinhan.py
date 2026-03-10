from typing import List, Tuple, Dict, Optional
from urllib.parse import urljoin
import requests
import time
from bs4 import BeautifulSoup
from playwright.sync_api import Page
from apps.backend.crawler.crawlers.base import BaseCrawler
from apps.backend.crawler.config import TARGET_CARDS


class ShinhanCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Shinhan", use_playwright=True)
        # We now use the full list pages instead of the limited API
        self.list_urls = [
            "https://www.shinhancard.com/pconts/html/card/credit/MOBFM281/MOBFM281R11.html",  # Credit
            "https://www.shinhancard.com/pconts/html/card/check/MOBFM282R11.html",  # Check
        ]
        self.base_url = "https://www.shinhancard.com"
        self.target_cards = set(TARGET_CARDS.get("Shinhan", []))

    def find_pdf_links_playwright(self, page: Page) -> List[Dict]:
        results: List[Dict] = []
        session = requests.Session()

        # 1. Collect all potential product links from list pages
        product_links = set()

        for url in self.list_urls:
            print(f"Shinhan: Visiting list page {url}...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                # Wait for list to render
                page.wait_for_timeout(5000)

                # Extract links
                # We look for links containing /card/apply/
                links = page.evaluate("""() => {
                    const extracted = [];
                    document.querySelectorAll('a[href*="/card/apply/"]').forEach(a => {
                        const text = a.innerText.trim();
                        const href = a.href;
                        if (text && href) {
                            extracted.push({text, href});
                        }
                    });
                    return extracted;
                }""")

                print(f"Shinhan: Found {len(links)} links on {url}")

                for link in links:
                    text = link["text"]
                    href = link["href"]

                    # Check if this card matches our targets
                    normalized_name = self._match_target(text)
                    if normalized_name:
                        product_links.add((normalized_name, href))
                        # print(f"  [MATCH] {text} -> {normalized_name}")

            except Exception as e:
                print(f"Shinhan: Error visiting {url}: {e}")

        print(f"Shinhan: Found {len(product_links)} unique target cards to process.")

        # 2. Visit each product page to find PDF
        for card_name, detail_url in product_links:
            # print(f"Shinhan: Checking details for {card_name} at {detail_url}")
            pdfs = self._extract_pdfs(session, detail_url)
            for title, pdf_url in pdfs:
                results.append(
                    {
                        "title": title,
                        "url": pdf_url,
                        "card_name": card_name,
                        "source_page": detail_url,
                    }
                )

        return results

    def _extract_pdfs(
        self, session: requests.Session, detail_url: str
    ) -> List[Tuple[str, str]]:
        pdfs: List[Tuple[str, str]] = []
        try:
            resp = session.get(detail_url, timeout=15)
            resp.raise_for_status()
            resp.encoding = "utf-8"
        except Exception as exc:
            print(f"Failed to load {detail_url}: {exc}")
            return pdfs

        soup = BeautifulSoup(resp.text, "html.parser")
        for anchor in soup.select("a[href]"):
            text = anchor.get_text(strip=True)
            href_value = anchor.get("href")
            if not href_value:
                continue
            href = str(href_value)
            if "설명서" in text or "약관" in text or href.lower().endswith(".pdf"):
                pdf_url = urljoin(self.base_url, href)
                title = text or pdf_url.split("/")[-1]
                pdfs.append((title, pdf_url))
        return pdfs

    def find_pdf_links_requests(self) -> List[Dict]:
        raise NotImplementedError("Shinhan crawler uses Playwright mode")

    def _match_target(self, text: str) -> Optional[str]:
        # Normalize text for matching
        text_norm = text.lower().replace(" ", "").replace("신한카드", "")

        for candidate in self.target_cards:
            candidate_norm = candidate.lower().replace(" ", "")
            if candidate_norm in text_norm:
                return candidate

            # Handle special cases or partial matches if needed
            if (
                candidate == "Deep Dream Platinum+"
                and "deepdreamplatinum+" in text_norm
            ):
                return candidate

        return None
