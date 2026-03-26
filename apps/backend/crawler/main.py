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

from apps.backend.crawler.config import DATA_OUTPUT_DIR, DOWNLOAD_DIR
from apps.backend.crawler.crawlers.shinhan import ShinhanCrawler
from apps.backend.crawler.crawlers.kb import KBCrawler

# from apps.backend.crawler.crawlers.hyundai import HyundaiCrawler
from apps.backend.crawler.utils.pdf_extractor import PDFExtractor
from apps.backend.crawler.utils.pdf_markdown_extractor import PDFMarkdownExtractor
from apps.backend.crawler.utils.markdown_json_extractor import MarkdownJSONExtractor


TRUE_SET = {"1", "true", "yes", "y", "on"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_SET


def _safe_filename_stem(raw: str) -> str:
    stem = "".join(c for c in raw if c.isalnum() or c in (" ", "-", "_")).strip()
    return stem or "document"


def _base_datasets_dir() -> str:
    # DATA_OUTPUT_DIR is "datasets/text" by default.
    return os.path.dirname(DATA_OUTPUT_DIR) or "datasets"


def _relative_pdf_path(local_path: str) -> str:
    try:
        download_root = os.path.abspath(DOWNLOAD_DIR)
        local_abs = os.path.abspath(local_path)
        rel = os.path.relpath(local_abs, download_root)
        if rel.startswith(".."):
            return os.path.basename(local_path)
        return rel
    except Exception:
        return os.path.basename(local_path)


def _output_path_for_pdf(local_path: str, base_dir: str, extension: str) -> str:
    rel = _relative_pdf_path(local_path)
    stem, _ = os.path.splitext(rel)
    out_path = os.path.join(base_dir, f"{stem}{extension}")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    return out_path


def _normalize_record_keys(record: dict) -> dict:
    record["title"] = record.get("title") or record.get("pdf_title") or ""
    record["url"] = record.get("url") or record.get("source_url") or ""
    return record


def process_pdf(record):
    """
    Process a downloaded PDF and save metadata JSON.
    Parse mode:
    - legacy: PDF -> plain text (pdfplumber)
    - md_llm: PDF -> markdown -> optional LLM JSON
    """
    local_path = record["local_path"]
    if not local_path or not os.path.exists(local_path):
        return None

    record = _normalize_record_keys(record)

    parse_mode = os.environ.get("CRAWLER_PARSE_MODE", "legacy").strip().lower()
    datasets_dir = _base_datasets_dir()
    markdown_dir = os.path.join(datasets_dir, "markdown")
    llm_json_dir = os.environ.get(
        "CRAWLER_JSON_OUTPUT_DIR", os.path.join(datasets_dir, "json_extracted")
    )

    try:
        if parse_mode == "md_llm":
            extraction_result = PDFMarkdownExtractor.extract(local_path)

            markdown_content = extraction_result.get("markdown", "")
            markdown_path = _output_path_for_pdf(local_path, markdown_dir, ".md")
            with open(markdown_path, "w", encoding="utf-8") as md_file:
                md_file.write(markdown_content)
            record["markdown_path"] = markdown_path

            if _env_bool("CRAWLER_ENABLE_LLM_JSON", True):
                try:
                    llm_model = os.environ.get("CRAWLER_LLM_MODEL", "solar-pro2")
                    max_chars = int(
                        os.environ.get("CRAWLER_LLM_MAX_INPUT_CHARS", "18000")
                    )
                    max_chunks = int(os.environ.get("CRAWLER_LLM_MAX_CHUNKS", "12"))
                    extractor = MarkdownJSONExtractor(
                        model=llm_model,
                        max_input_chars=max_chars,
                        max_chunks=max_chunks,
                    )
                    if extractor.init_error:
                        record["llm_error"] = extractor.init_error

                    fallback_name = record.get("card_name") or _safe_filename_stem(
                        os.path.splitext(os.path.basename(local_path))[0]
                    )
                    company_name = record.get("company") or ""

                    extracted_json = extractor.extract(
                        markdown=markdown_content,
                        card_company=company_name,
                        fallback_card_name=fallback_name,
                    )
                    llm_json_path = _output_path_for_pdf(
                        local_path, llm_json_dir, ".json"
                    )
                    with open(llm_json_path, "w", encoding="utf-8") as llm_file:
                        json.dump(extracted_json, llm_file, ensure_ascii=False, indent=2)
                    record["llm_json_path"] = llm_json_path
                except Exception as llm_error:
                    record["llm_error"] = str(llm_error)
        else:
            extraction_result = PDFExtractor.extract(local_path)

    except Exception as e:
        print(f"Extraction failed for {local_path}: {e}")
        extraction_result = {}

    # Merge extraction data with crawler record
    record.update(extraction_result)

    # Save metadata JSON in datasets/text mirroring datasets/pdfs subfolders.
    json_path = _output_path_for_pdf(local_path, DATA_OUTPUT_DIR, ".json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    record["metadata_json_path"] = json_path

    return record


def main():
    # 1. Initialize Crawlers
    # Hyundai is skipped as per user instruction
    crawlers = [ShinhanCrawler(), KBCrawler()]

    all_results = []

    parse_mode = os.environ.get("CRAWLER_PARSE_MODE", "legacy").strip().lower()
    print(f"Starting Crawlers... (parse_mode={parse_mode})")

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
            "title",
            "pdf_title",
            "url",
            "source_url",
            "file_size_bytes",
            "page_count",
            "local_path",
            "parse_method",
            "ocr_required",
            "markdown_path",
            "llm_json_path",
            "metadata_json_path",
            "llm_error",
        ]

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
