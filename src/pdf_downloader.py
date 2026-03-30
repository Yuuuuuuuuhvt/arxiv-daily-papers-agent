from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from .models import ArxivPaper

logger = logging.getLogger(__name__)


def _alphaxiv_pdf_url(paper: ArxivPaper) -> str:
    return f"https://fetcher.alphaxiv.org/v2/pdf/{paper.arxiv_id}v{paper.version}.pdf"


async def download_pdf(
    paper: ArxivPaper,
    output_dir: Path,
    sem: asyncio.Semaphore,
) -> Path | None:
    dest = output_dir / f"{paper.arxiv_id}.pdf"
    if dest.exists():
        logger.debug("PDF already exists: %s", dest)
        return dest

    urls = [paper.pdf_url, _alphaxiv_pdf_url(paper)]

    async with sem:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            for url in urls:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    dest.write_bytes(resp.content)
                    logger.info("Downloaded PDF: %s from %s (%.1f MB)",
                                paper.arxiv_id, url.split("/")[2], len(resp.content) / 1e6)
                    return dest
                except Exception:
                    logger.debug("PDF download failed from %s for %s", url.split("/")[2], paper.arxiv_id)
            logger.warning("Failed to download PDF for %s from all sources", paper.arxiv_id)
            return None


async def download_all_pdfs(
    papers: list[ArxivPaper],
    output_dir: Path,
    max_concurrent: int = 5,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(max_concurrent)

    tasks = [download_pdf(paper, output_dir, sem) for paper in papers]
    results = await asyncio.gather(*tasks)

    downloaded: dict[str, Path] = {}
    for paper, path in zip(papers, results):
        if path is not None:
            downloaded[paper.arxiv_id] = path

    logger.info("PDFs downloaded: %d/%d", len(downloaded), len(papers))
    return downloaded
