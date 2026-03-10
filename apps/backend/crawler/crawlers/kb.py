from typing import List, Dict, Optional, Tuple
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import quote, urljoin
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page
from apps.backend.crawler.crawlers.base import BaseCrawler
from apps.backend.crawler.config import TARGET_CARDS


class KBCrawler(BaseCrawler):
    search_url = "https://card.kbcard.com/CMN/DVIEW/HOBMCXPRIZZC0003?topquery={query}"
    detail_url = "https://card.kbcard.com/CRD/DVIEW/HCAMCXPRICAC0076"
    fallback_codes = {
        "KB 탄탄대로 Miz&Mr": "09183",
        "KB 탄탄대로 Biz": "09214",
        "KB Star 카드": "09310",
        "KB 마이원 카드": "02050",
        "KB 직장인 보너스 체크카드": "01690",
        "KB 국민 굿데이 카드": "09063",
        "KB Easy Pick 카드": "09243",
        "KB The Easy 카드": "09250",
        "KB My WE:SH 카드": "09923",
        "KB 청춘대로 톡톡카드": "09174",
    }

    def __init__(self):
        super().__init__("KB", use_playwright=False)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        self.target_cards = TARGET_CARDS.get("KB", [])

    def find_pdf_links_requests(self) -> List[Dict]:
        records: List[Dict] = []
        for card_name in self.target_cards:
            code = self._find_cooperation_code(card_name)
            if not code:
                print(f"KB: unable to find disclosure for {card_name}; skipping")
                continue

            detail_url = f"{self.detail_url}?mainCC=a&cooperationcode={code}"
            pdfs = self._extract_pdfs(detail_url)
            if not pdfs:
                print(f"KB: no PDF links found for {card_name} at {detail_url}")
                continue

            for title, pdf_url in pdfs:
                records.append(
                    {
                        "company": self.company_name,
                        "card_name": card_name,
                        "title": title,
                        "url": pdf_url,
                        "source_page": detail_url,
                    }
                )

        return records

    def _extract_pdfs(self, detail_url: str) -> List[Tuple[str, str]]:
        try:
            resp = self.session.get(detail_url, timeout=20)
            resp.raise_for_status()
        except Exception as exc:
            print(f"KB: failed to fetch {detail_url}: {exc}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Tuple[str, str]] = []
        seen = set()

        for anchor in soup.select("a"):
            raw_href = anchor.get("href")
            href = str(raw_href) if raw_href else ""
            raw_onclick = anchor.get("onclick")
            onclick = str(raw_onclick) if raw_onclick else ""

            candidates = []
            if href.lower().endswith(".pdf"):
                candidates.append(urljoin(detail_url, href))
            for match in re.findall(r"'([^']+\.pdf)'", onclick):
                candidates.append(match)

            for pdf_url in candidates:
                if pdf_url in seen:
                    continue
                seen.add(pdf_url)
                title = anchor.get_text(strip=True) or pdf_url.split("/")[-1]

                # Determine document type for filename uniqueness
                doc_type = "manual" if "prdctOpmn" in pdf_url else "terms"
                # Keep title clean but meaningful
                title = f"{title}_{doc_type}"

                results.append((title, pdf_url))

        return results

    def _find_cooperation_code(self, card_name: str) -> Optional[str]:
        if card_name in self.fallback_codes:
            return self.fallback_codes[card_name]

        attempts = 0
        for query in self._query_variations(card_name):
            if attempts >= 3:
                break
            attempts += 1
            url = self.search_url.format(query=quote(query))
            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
            except Exception:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            candidates: List[Tuple[float, str]] = []
            for anchor in soup.select("a[href*='cooperationcode']"):
                raw_href = anchor.get("href")
                href = str(raw_href) if raw_href else ""
                if "cooperationcode=" not in href:
                    continue
                code = href.split("cooperationcode=")[-1]
                text = anchor.get_text(strip=True)
                score = SequenceMatcher(
                    None, self._normalize(card_name), self._normalize(text)
                ).ratio()
                candidates.append((score, code))

            if candidates:
                candidates.sort(reverse=True)
                best_score, best_code = candidates[0]
                if best_score > 0.35:
                    return best_code

        return None

    def _query_variations(self, card_name: str) -> List[str]:
        variations = set()
        variations.add(card_name)
        variations.add(card_name.replace("KB", "").strip())
        variations.update(card_name.split())
        hangul = re.sub(r"[^가-힣]", "", card_name)
        if hangul:
            variations.add(hangul)
        variations.add(hangul.replace(" ", "")) if hangul else None
        letters = re.sub(r"[^A-Za-z&]", " ", card_name)
        for token in letters.split():
            variations.add(token)
        # Remove generic suffixes
        variations = {v for v in variations if v}
        return list(variations)

    def _normalize(self, text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        for token in ["KB", "케이비", "국민", "카드", "체크", "신용", "카드"]:
            text = text.replace(token, "")
        return re.sub(r"\s+", "", text).lower()

    # Playwright path unused
    def find_pdf_links_playwright(self, page: Page) -> List[Dict]:  # pragma: no cover
        raise NotImplementedError("KB crawler uses requests mode")
