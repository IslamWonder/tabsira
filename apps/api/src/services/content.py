"""
Prepared content shipped as data: the world's regions, their place on the world picture, the rain tutorial.

All are versioned files under `data/`, read once and checked: a release adds a
file, it changes no code (v2 §13 and §16, decision 59). The tutorial cites its
verses and hadith by reference only; their text is always read from the store.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.world import MAX_REVEAL_RADIUS, WorldTheme
from src.pipeline.engine import ExplanationPart, RelationType, SmallStep, WhyThis
from src.pipeline.schemas import BBox

# apps/api/src/services/content.py -> the repository root, four levels up.
REPO_ROOT = Path(__file__).resolve().parents[4]
REGIONS_PATH = REPO_ROOT / "data" / "world" / "regions-1.0.json"
LAYOUT_PATH = REPO_ROOT / "data" / "world" / "layout-1.json"
TUTORIAL_PATH = REPO_ROOT / "data" / "tutorial" / "rain-1.0.json"

Ratio = Annotated[float, Field(ge=0, le=1)]
Radius = Annotated[float, Field(gt=0, le=MAX_REVEAL_RADIUS)]


class _Data(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Position(_Data):
    x: Ratio
    y: Ratio


class Region(_Data):
    id: str
    domain_id: str
    name: str
    position: Position


class Regions(_Data):
    version: str
    path_version: str
    description: str
    fallback_region: str
    regions: list[Region]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [region.id for region in self.regions]
        if len(ids) != len(set(ids)):
            message = "a region id appears twice"
            raise ValueError(message)
        domains = [region.domain_id for region in self.regions]
        if len(domains) != len(set(domains)):
            message = "a domain has two regions"
            raise ValueError(message)
        if self.fallback_region not in ids:
            message = "the fallback region is not a region"
            raise ValueError(message)
        return self

    def by_id(self, region_id: str) -> Region | None:
        return next((region for region in self.regions if region.id == region_id), None)

    def name_of(self, region_id: str) -> str:
        """Return a region's name; a region a later file dropped keeps its id as its name."""
        region = self.by_id(region_id)
        return region.name if region is not None else region_id

    def for_domain(self, domain_id: str | None) -> Region:
        """Return the region of a domain, or the fallback region for an insight with none."""
        found = next((region for region in self.regions if region.domain_id == domain_id), None)
        if found is not None:
            return found
        # The validator made sure the fallback region exists.
        return next(region for region in self.regions if region.id == self.fallback_region)


class LayoutImage(_Data):
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class LayoutSlot(_Data):
    """One circle of the picture: its centre as ratios of the picture, its radius of its width."""

    x: Ratio
    y: Ratio
    radius: Radius


class LayoutRegion(_Data):
    id: str
    theme: WorldTheme
    # The landmark's drawing in the web app's icon set.
    icon: Annotated[str, Field(pattern=r"^[a-z]{2,16}$")]
    # Slot 0 is the landmark; each further concept learned in the region takes the next free one.
    slots: Annotated[list[LayoutSlot], Field(min_length=1)]

    @model_validator(mode="before")
    @classmethod
    def _slots_as_triples(cls, data: object) -> object:
        # The file writes each slot as [x, y, radius], one line per region.
        if isinstance(data, dict) and isinstance(data.get("slots"), list):
            data = {
                **data,
                "slots": [
                    dict(zip(("x", "y", "radius"), slot, strict=True))
                    if isinstance(slot, list)
                    else slot
                    for slot in data["slots"]
                ],
            }
        return data


class Layout(_Data):
    version: Annotated[str, Field(pattern=r"^[0-9]{1,8}$")]
    regions_version: str
    description: str
    image: LayoutImage
    regions: list[LayoutRegion]

    @model_validator(mode="after")
    def _one_entry_per_region(self) -> Self:
        ids = [region.id for region in self.regions]
        if len(ids) != len(set(ids)):
            message = "a region is laid out twice"
            raise ValueError(message)
        return self

    def region(self, region_id: str) -> LayoutRegion | None:
        return next((region for region in self.regions if region.id == region_id), None)


class TutorialQuran(_Data):
    surah: Annotated[int, Field(ge=1, le=114)]
    ayah: Annotated[int, Field(ge=1, le=286)]
    relation: RelationType
    matched_on: str


class TutorialHadith(_Data):
    collection: str
    number: str
    relation: RelationType
    matched_on: str


class TutorialImage(_Data):
    path: str
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    alt: str


class TutorialInsight(_Data):
    slug: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")]
    title: str
    glimpse: str
    anchor: BBox
    relation: RelationType
    quran: TutorialQuran
    hadith: TutorialHadith | None
    explanation: list[ExplanationPart]
    why: WhyThis
    small_step: SmallStep | None
    learning_unit_id: str
    learning_path_version: str


class Tutorial(_Data):
    scene: str
    version: str
    description: str
    title: str
    image: TutorialImage
    insights: list[TutorialInsight]

    @property
    def key(self) -> str:
        """The scene and its version, as a kept copy of one of its insights names them."""
        return f"{self.scene}-{self.version}"

    def insight(self, slug: str) -> TutorialInsight | None:
        return next((insight for insight in self.insights if insight.slug == slug), None)


@lru_cache(maxsize=4)
def load_regions(path: Path = REGIONS_PATH) -> Regions:
    return Regions.model_validate_json(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def load_layout(path: Path = LAYOUT_PATH) -> Layout:
    """Read the world picture's layout; refuse one that leaves a region of the regions file out."""
    layout = Layout.model_validate_json(path.read_text(encoding="utf-8"))
    regions = load_regions()
    missing = {region.id for region in regions.regions} - {region.id for region in layout.regions}
    if layout.regions_version != regions.version or missing:
        message = f"layout {layout.version} does not lay out regions {regions.version}"
        raise ValueError(message)
    return layout


@lru_cache(maxsize=4)
def load_tutorial(path: Path = TUTORIAL_PATH) -> Tutorial:
    return Tutorial.model_validate_json(path.read_text(encoding="utf-8"))
