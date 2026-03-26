import os
import re
from typing import Any, Dict, List

import pdfplumber


class PDFMarkdownExtractor:
    @staticmethod
    def extract(file_path: str) -> Dict[str, Any]:
        """
        Extract markdown-friendly text from a PDF.

        Preferred engine: pymupdf4llm (if installed)
        Fallback engine: pdfplumber
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        file_size = os.path.getsize(file_path)
        page_count = PDFMarkdownExtractor._count_pages(file_path)
        markdown = ""
        parse_method = ""
        parse_error = ""

        try:
            markdown = PDFMarkdownExtractor._extract_with_pymupdf4llm(file_path)
            parse_method = "pymupdf4llm"
        except Exception as primary_error:
            parse_error = str(primary_error)
            try:
                markdown = PDFMarkdownExtractor._extract_with_pdfplumber(file_path)
                parse_method = "pdfplumber_fallback"
            except Exception as fallback_error:
                return {
                    "file_size_bytes": file_size,
                    "page_count": page_count,
                    "markdown": "",
                    "text": "",
                    "ocr_required": True,
                    "parse_method": "failed",
                    "error": f"{parse_error}; fallback={fallback_error}",
                }

        normalized_markdown = PDFMarkdownExtractor._normalize_markdown(markdown)
        plain_text = PDFMarkdownExtractor._markdown_to_text(normalized_markdown)

        return {
            "file_size_bytes": file_size,
            "page_count": page_count,
            "markdown": normalized_markdown,
            "text": plain_text,
            "ocr_required": bool(page_count > 0 and not plain_text.strip()),
            "parse_method": parse_method,
            "parse_error": parse_error,
        }

    @staticmethod
    def _count_pages(file_path: str) -> int:
        try:
            with pdfplumber.open(file_path) as pdf:
                return len(pdf.pages)
        except Exception:
            return 0

    @staticmethod
    def _extract_with_pymupdf4llm(file_path: str) -> str:
        import pymupdf4llm

        rendered = pymupdf4llm.to_markdown(file_path)
        if isinstance(rendered, list):
            rendered = "\n\n".join(str(item) for item in rendered if item is not None)
        if not isinstance(rendered, str):
            raise RuntimeError("pymupdf4llm returned non-string markdown payload")
        return rendered

    @staticmethod
    def _extract_with_pdfplumber(file_path: str) -> str:
        blocks: List[str] = []
        with pdfplumber.open(file_path) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                text = text.strip()
                if not text:
                    continue
                blocks.append(f"## Page {idx}\n\n{text}")
        return "\n\n".join(blocks)

    @staticmethod
    def _normalize_markdown(markdown: str) -> str:
        if not markdown:
            return ""
        markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
        markdown = "\n".join(line.rstrip() for line in markdown.split("\n"))
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)
        return markdown.strip()

    @staticmethod
    def _markdown_to_text(markdown: str) -> str:
        if not markdown:
            return ""
        text = markdown
        text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
        text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = text.replace("`", "")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
