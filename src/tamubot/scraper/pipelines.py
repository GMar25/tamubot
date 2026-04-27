import json
import os
import re

from scrapy import Request
from scrapy.pipelines.files import FilesPipeline

from tamubot.scraper.items import ClassSectionItem, SimpleSyllabusItem


class SyllabusPipeline(FilesPipeline):
    _TERM_SEMESTER = {"11": "Spring", "21": "Summer", "31": "Fall"}

    def get_media_requests(self, item, info):
        if not item.get("file_urls"):
            return

        # Build the output path to check if the file already exists on disk
        store = info.spider.settings.get("FILES_STORE", "")
        rel_path = self._item_file_path(item)
        full_path = os.path.join(store, rel_path)
        if os.path.exists(full_path):
            info.spider.logger.debug(f"Skip (exists): {rel_path}")
            return

        for file_url in item["file_urls"]:
            yield Request(file_url, meta={"item": item})

    @staticmethod
    def _term_code_to_folder(term_code: str) -> str:
        """'202611' → 'Spring_2026'"""
        year = term_code[:4]
        sem_code = term_code[4:]
        sem = SyllabusPipeline._TERM_SEMESTER.get(sem_code, sem_code)
        return f"{sem}_{year}"

    @classmethod
    def _item_file_path(cls, item) -> str:
        """Build relative path for an item (used by both skip-check and file_path)."""
        term = item.get("term_code", "unknown")
        subject = item.get("subject", "UNK")
        course = item.get("course", "000")
        section = item.get("section", "000")
        crn = item.get("crn", "00000")

        filename = f"{term}_{subject}_{course}_{section}_{crn}.pdf"

        if isinstance(item, ClassSectionItem):
            subgroup = "graduate" if int(course) >= 600 else "undergraduate"
            term_folder = cls._term_code_to_folder(term)
            return os.path.join("howdy_portal", subject, subgroup, term_folder, filename)

        return filename

    def file_path(self, request, response=None, info=None, *, item=None):
        return self._item_file_path(request.meta.get("item"))


class ManifestPipeline:
    """Records syllabus_url + doc_id for each downloaded Simple Syllabus PDF."""

    def open_spider(self, spider):
        self._records = {}
        store = spider.settings.get("FILES_STORE")
        os.makedirs(store, exist_ok=True)
        self._manifest_path = os.path.join(store, "simple_syllabus_metadata.json")

    def process_item(self, item, spider):
        if not isinstance(item, SimpleSyllabusItem):
            return item

        term_code = item.get("term_code", "unknown")
        subject = item.get("subject", "UNK")
        course = item.get("course", "000")
        section = item.get("section", "000")
        crn = item.get("crn", "")
        filename = f"{term_code}_{subject}_{course}_{section}_{crn}.pdf"

        self._records[filename] = {
            "syllabus_url": item.get("syllabus_url", ""),
            "doc_id": item.get("doc_id", ""),
        }
        return item

    def close_spider(self, spider):
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(self._records, f, indent=2)
        spider.logger.info(f"ManifestPipeline: wrote {len(self._records)} entries to {self._manifest_path}")


class ProgressPipeline:
    def __init__(self):
        self.log_path = os.path.join("tamu_data", "scraper", "logs", "progress_log.txt")
        # Ensure logs directory exists
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    def process_item(self, item, spider):
        if spider.name == "catalog" and "url" in item:
            url = item["url"]
            # Only log TamuPageItem (pages), not PdfManifestItem
            if "content" in item:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(url + "\n")
        return item


class CatalogPagePipeline:
    """Saves TamuPageItem content as .md files under tamu_data/raw/catalog/<DEPT>/."""

    _SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")

    def process_item(self, item, spider):
        from tamubot.scraper.items import TamuPageItem
        from tamubot.scraper.spiders.catalog_spider import CatalogSpider

        if not isinstance(item, TamuPageItem):
            return item

        content = item.get("content", "")
        if not content:
            return item

        dept = CatalogSpider.dept_for_url(item["url"])
        if not dept:
            dept = "general"

        store = spider.settings.get("FILES_STORE", "tamu_data/raw")
        out_dir = os.path.join(store, "catalog", dept)
        os.makedirs(out_dir, exist_ok=True)

        slug = self._SLUG_RE.sub("_", item["url"].split("catalog.tamu.edu")[-1]).strip("_")
        if not slug:
            slug = "index"
        filename = f"{slug}.md"

        filepath = os.path.join(out_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {item.get('title', '')}\n\n")
            f.write(f"Source: {item['url']}\n\n")
            f.write(content)

        spider.logger.info(f"CatalogPagePipeline: saved {filepath}")
        return item
