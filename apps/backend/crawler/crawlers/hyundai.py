from typing import List, Dict
from playwright.sync_api import Page
from apps.backend.crawler.crawlers.base import BaseCrawler


class HyundaiCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Hyundai")
        self.list_url = "https://www.hyundaicard.com/cpc/cr/CPCCR0201_01.hc"

    def find_pdf_links_playwright(self, page: Page) -> List[Dict]:
        links = []
        try:
            print(f"Navigating to {self.list_url}...")
            page.goto(self.list_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(15000)

            elements = page.query_selector_all("a, button")
            for el in elements:
                text = el.inner_text().strip()
                onclick = el.get_attribute("onclick") or ""
                href = el.get_attribute("href") or ""

                if (
                    "설명서" in text
                    or "약관" in text
                    or "download" in onclick.lower()
                    or ".pdf" in href.lower()
                ):
                    card_name = ""
                    # Simple heuristic: look for nearby titles
                    js = """
                        (el) => {
                            let curr = el;
                            for(let i=0; i<5; i++) {
                                if(!curr) break;
                                let tit = curr.querySelector('.tit, .name, strong, h3, h4');
                                if(tit && tit.innerText.length > 2) return tit.innerText;
                                curr = curr.parentElement;
                            }
                            return '';
                        }
                    """
                    card_name = page.evaluate(js, el)

                    links.append(
                        {
                            "title": text,
                            "url": f"js:{onclick}" if onclick else href,
                            "card_name": card_name,
                            "source_page": self.list_url,
                        }
                    )
        except Exception as e:
            print(f"Error crawling Hyundai: {e}")

        return links
