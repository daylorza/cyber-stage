"""The only module that talks to the Meta Model API.

Every product-AI call goes through here, one job per model:
  Spark   -> listing copy and reasoning (grounded in evidence + supplied facts only)
  Wonder  -> multimodal room classification, features, walkthrough order
  Image   -> geometry-preserving staging (image-to-image)
  SAM 3.1 -> segmentation and tracking (rooms, objects, faces / personal items to blur)

No other model is used as the product brain, copywriter, or stager, including as a fallback.
The API key comes from the environment (META_API_KEY) and is never logged or committed.
Calls are wired in Stage 1; Stage 0 runs the pipeline skeleton without them.
"""

import os
from dataclasses import dataclass, field


class MetaNotConfigured(RuntimeError):
    pass


@dataclass
class MetaClient:
    api_key: str | None = field(default_factory=lambda: os.environ.get("META_API_KEY"))
    base_url: str | None = field(default_factory=lambda: os.environ.get("META_API_BASE_URL"))

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _require(self) -> None:
        if not self.configured:
            raise MetaNotConfigured("Set META_API_KEY and META_API_BASE_URL to call the Meta Model API.")

    def spark_copy(self, *, facts: dict, evidence: list[dict]) -> dict:
        self._require()
        raise NotImplementedError("Spark copy is wired in Stage 1.")

    def wonder_classify(self, *, frame_path: str) -> dict:
        self._require()
        raise NotImplementedError("Wonder classification is wired in Stage 1.")

    def image_stage(self, *, frame_path: str, style: str) -> bytes:
        self._require()
        raise NotImplementedError("Image staging is wired in Stage 1.")

    def sam_segment(self, *, frame_path: str, concepts: list[str]) -> dict:
        self._require()
        raise NotImplementedError("SAM 3.1 segmentation is wired in Stage 1.")
