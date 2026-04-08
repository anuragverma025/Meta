"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE: dataset_loader.py
FOLDER: server/
PURPOSE: Loads PR diffs from HuggingFace dataset — feeds the environment
USED BY: server/environment.py, server/app.py
KEY CLASSES/FUNCTIONS: DatasetLoader
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import random
import logging
from typing import Dict, Any

try:
    from datasets import load_dataset
    DATASETS_AVAILABLE = True
except ImportError:
    DATASETS_AVAILABLE = False

logger = logging.getLogger(__name__)

FALLBACK_SAMPLES = [
    {
        "filename": "utils/pagination.py",
        "patch": "def get_page_items(items, page, page_size):\n-    start = page * page_size\n-    end = start + page_size\n-    return items[start:end]\n+    start = (page - 1) * page_size\n+    end = start + page_size\n+    return items[start:end]",
        "comment": "Line 2: page indexing was wrong — pages are 1-indexed so (page-1)*page_size is correct"
    },
    {
        "filename": "api/userController.js",
        "patch": "- const userName = user.profile.name;\n+ const userName = user?.profile?.name ?? 'Anonymous';",
        "comment": "Missing null check — user.profile could be undefined causing TypeError"
    },
    {
        "filename": "db/queries.py",
        "patch": "- query = f\"SELECT * FROM users WHERE id = {user_id}\"\n+ query = \"SELECT * FROM users WHERE id = %s\"\n+ cursor.execute(query, (user_id,))",
        "comment": "Critical: SQL injection vulnerability — never format user input into queries"
    },
    {
        "filename": "services/emailService.js",
        "patch": "- const result = sendEmail(user.email, template);\n+ const result = await sendEmail(user.email, template);",
        "comment": "Missing await — sendEmail is async, without await result is a Promise not the value"
    },
    {
        "filename": "core/processor.py",
        "patch": "- except:\n+ except (ValueError, TypeError) as e:\n+     logger.error(f\"Processing failed: {e}\")",
        "comment": "Bare except catches everything including SystemExit — always catch specific exceptions"
    }
]

class DatasetLoader:
    """
    Loads real PR diffs from the microsoft/CodeReviewer dataset.
    Falls back to 5 synthetic samples if HuggingFace is unavailable.
    """

    def __init__(self):
        """Initializes the dataset loader, attempting to pull from HF."""
        self.dataset = None
        self.is_loaded = False
        
        # We try to load dataset if HF `datasets` library is available
        if DATASETS_AVAILABLE:
            try:
                # Use a specific split or subset if possible, but CodeReviewer is large. 
                # We'll just configure it gracefully.
                logger.info("Attempting to load 'microsoft/CodeReviewer' dataset...")
                # To avoid downloading 20GB in hackathon setup, we might load with streaming=True
                # But typically we can just rely on the fallback samples if it takes too long.
                ds = load_dataset("microsoft/CodeReviewer", split="train", streaming=True)
                # Keep a robust iterator bounded cache
                self._iterator = iter(ds)
                self.is_loaded = True
            except Exception as e:
                logger.warning(f"Failed to load HuggingFace dataset: {e}. Using fallback samples.")
        else:
            logger.warning("datasets module not found. Using fallback samples.")

        self.samples = []
        for sample in FALLBACK_SAMPLES:
            sample["language"] = self.get_language_from_filename(sample["filename"])
            self.samples.append(sample)

    def get_random_sample(self) -> Dict[str, Any]:
        """Returns a random PR diff sample."""
        if self.is_loaded and self._iterator:
            try:
                # Try getting next valid sample from HF stream
                for _ in range(50): # try up to 50 times to find bounded patch
                    record = next(self._iterator)
                    patch = record.get("patch", "")
                    if 50 <= len(patch) <= 2000:
                        return {
                            "filename": record.get("filename", "unknown"),
                            "patch": patch,
                            "comment": record.get("comment", ""),
                            "language": self.get_language_from_filename(record.get("filename", "unknown")),
                            "msg": record.get("msg", "")
                        }
            except Exception as e:
                logger.warning(f"Error fetching from dataset stream: {e}. Falling back to default.")
                self.is_loaded = False # fallback forever
                
        # Return fallback if streaming failed or isn't loaded
        return random.choice(self.samples)

    def get_language_from_filename(self, filename: str) -> str:
        """Detects programming language from file extension."""
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        mapping = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "java": "java",
            "cpp": "cpp",
            "c": "c",
            "go": "go",
            "rs": "rust",
            "rb": "ruby",
            "cs": "csharp",
            "php": "php",
            "html": "html",
            "css": "css",
            "json": "json"
        }
        return mapping.get(ext, "unknown")

    def get_dataset_stats(self) -> Dict[str, Any]:
        """Returns dummy stats or real stats for the `/stats` endpoint."""
        lang_counts = {}
        for s in self.samples:
            lang_counts[s["language"]] = lang_counts.get(s["language"], 0) + 1
            
        return {
            "total_samples": len(self.samples) if not self.is_loaded else "1M+ (Streaming)",
            "languages_breakdown": lang_counts if not self.is_loaded else "Mixed",
            "avg_patch_length": sum(len(s.get("patch", "")) for s in self.samples) / max(1, len(self.samples)),
            "source": "microsoft/CodeReviewer" if self.is_loaded else "Fallback Synthetic"
        }
