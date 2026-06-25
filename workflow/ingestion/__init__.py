"""Ingestion framework -- file type detection, routing, and synthesis signals.

Handles incoming files (via API or direct drop) and routes them:
- Small files (<=5KB): directly to canon/
- Large files (>5KB): to canon/sources/ with a synthesis signal
  for the enrichment phase to process into canon documents.

Tracks all mappings in canon/.manifest.json.
"""

from workflow.ingestion.core import (
    FileType,
    IngestResult,
    SourceManifest,
    detect_file_type,
    ingest_file,
)
from workflow.ingestion.extractors import extract_text, synthesize_source
from workflow.ingestion.image_extractor import extract_image_description
from workflow.ingestion.video_extractor import extract_video_description

__all__ = [
    "FileType",
    "IngestResult",
    "SourceManifest",
    "detect_file_type",
    "extract_image_description",
    "extract_text",
    "extract_video_description",
    "ingest_file",
    "synthesize_source",
]
