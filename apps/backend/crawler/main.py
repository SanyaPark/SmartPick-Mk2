import os
import sys
import csv
import json
from concurrent.futures import ThreadPoolExecutor

# Add project root to sys.path to allow running from any directory
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from apps.backend.crawler.config import DATA_OUTPUT_DIR, INDEX_FILE
from apps.backend.crawler.crawlers.shinhan import ShinhanCrawler
from apps.backend.crawler.crawlers.kb import KBCrawler

# from apps.backend.crawler.crawlers.hyundai import HyundaiCrawler
from apps.backend.crawler.utils.pdf_extractor import PDFExtractor


def process_pdf(record):
    """
    Extract text from a downloaded PDF and save JSON metadata.
    """
    local_path = record["local_path"]
    if not local_path or not os.path.exists(local_path):
        return None

    # print(f"Processing {local_path}...")
    try:
        extraction_result = PDFExtractor.extract(local_path)
    except Exception as e:
        print(f"Extraction failed for {local_path}: {e}")
        extraction_result = {}

    # Merge extraction data with crawler record
    record.update(extraction_result)

    # Save individual JSON next to the PDF or in a text folder?
    # Original plan said datasets/text, but logic below puts it in DATA_OUTPUT_DIR
    # Let's put it in datasets/text mirroring the structure or flat?
    # For now, let's keep it simple: flat in datasets/text or adjacent to PDF?
    # User asked to organize PDFs.

    # Let's save JSON in datasets/text with a flat structure for now to avoid complexity
    text_dir = os.path.join(os.path.dirname(DATA_OUTPUT_DIR), "text")
    os.makedirs(text_dir, exist_ok=True)

    safe_name = os.path.basename(local_path).replace(".pdf", ".json")
    json_path = os.path.join(text_dir, safe_name)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return record


def main():
    # 1. Initialize Crawlers
    # Hyundai is skipped as per user instruction
    crawlers = [ShinhanCrawler(), KBCrawler()]

    all_results = []

    print("Starting Crawlers...")

    # 2. Run Crawlers
    for crawler in crawlers:
        try:
            results = crawler.run()
            if results:
                all_results.extend(results)
        except Exception as e:
            print(f"Crawler {crawler.company_name} failed: {e}")

    # 3. Process PDFs (Extract Text)
    print(f"Extracting text from {len(all_results)} PDFs...")
    final_records = []

    # Using ThreadPool for extraction
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for record in all_results:
            futures.append(executor.submit(process_pdf, record))

        for future in futures:
            try:
                res = future.result()
                if res:
                    final_records.append(res)
            except Exception as e:
                print(f"Process failed: {e}")

    # 4. Save Master Index CSV
    if final_records:
        keys = [
            "company",
            "card_name",
            "title",  # Changed from pdf_title
            "url",  # Changed from source_url (check consistency)
            "file_size_bytes",
            "page_count",
            "local_path",
        ]

        # Normalize keys before writing
        # KB uses 'title', Shinhan might use 'pdf_title' in old code?
        # Let's standardize in the dict

        index_path = os.path.join(os.path.dirname(DATA_OUTPUT_DIR), "index.csv")

        with open(index_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(final_records)

        print(f"Done. Saved {len(final_records)} records to {index_path}")
    else:
        print("No records found.")


if __name__ == "__main__":
    main()
