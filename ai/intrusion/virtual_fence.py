"""
ai/intrusion/virtual_fence.py
Defines a polygon "restricted zone" and detects when a tracked object's
centroid crosses into it — debounced so a single crossing fires exactly
one event, not one per frame the object stays inside the zone.
"""
from typing import Dict, List, Set, Tuple

import cv2
import numpy as np

from ai.utils.logger import get_logger

log = get_logger(__name__)

Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]


def _centroid(bbox: BBox) -> Point:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


class VirtualFence:
    def __init__(self, polygon: List[Point]):
        if len(polygon) < 3:
            raise ValueError("A fence zone needs at least 3 points")
        self._polygon = np.array(polygon, dtype=np.float32)
        self._inside_ids: Set[int] = set()  # track IDs currently inside the zone

    def is_inside(self, point: Point) -> bool:
        result = cv2.pointPolygonTest(self._polygon, point, False)
        return result >= 0

    def check(self, tracked: Dict[int, BBox]) -> List[int]:
        """
        Given this frame's {track_id: bbox}, returns the list of track IDs
        that just crossed INTO the zone this frame (i.e. weren't inside last
        frame, are inside now). Only these should trigger a new alert.
        """
        currently_inside = set()
        newly_entered = []

        for track_id, bbox in tracked.items():
            c = _centroid(bbox)
            if self.is_inside(c):
                currently_inside.add(track_id)
                if track_id not in self._inside_ids:
                    newly_entered.append(track_id)

        self._inside_ids = currently_inside
        if newly_entered:
            log.info("Zone crossed by track IDs: %s", newly_entered)
        return newly_entered
