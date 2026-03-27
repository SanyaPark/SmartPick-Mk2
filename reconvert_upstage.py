import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / "apps" / "backend" / ".env")

from apps.backend.crawler.utils.pdf_markdown_extractor import PDFMarkdownExtractor

def main():
    pdfs_dir = project_root / "datasets" / "pdfs"
    md_upstage_dir = project_root / "datasets" / "markdown_upstage"
    
    pdf_files = list(pdfs_dir.rglob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files to process.")
    
    success_count = 0
    fail_count = 0

    for pdf_file in pdf_files:
        rel_path = pdf_file.relative_to(pdfs_dir)
        output_path = md_upstage_dir / rel_path.with_suffix(".md")
        
        # We already processed this one in the previous step, so we can skip it,
        # but the user might want a clean run. We'll skip if exists to save Upstage API cost.
        if output_path.exists():
            print(f"Skipping already processed: {rel_path.name}")
            success_count += 1
            continue
            
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Converting: {rel_path.name}")
        
        try:
            result = PDFMarkdownExtractor.extract(str(pdf_file))
            markdown_content = result.get("markdown", "")
            
            # Additional safety parse check
            if result.get("parse_error"):
                print(f"  [WARN] Parse Error: {result.get('parse_error')}")
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            
            success_count += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            fail_count += 1

    print(f"\nCompleted! Success: {success_count}, Failed: {fail_count}")

if __name__ == "__main__":
    main()
