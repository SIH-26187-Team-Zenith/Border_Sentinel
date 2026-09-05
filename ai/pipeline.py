"""
ai/pipeline.py
Wires video input -> detection -> tracking -> intrusion/activity/ANPR
checks -> backend alerts into one loop. This is what main.py runs.

A camera_id must be supplied — it should match a real camera row already
created in the backend (via POST /cameras), since backend's ingest route
expects a valid camera_id.
"""
import json
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ai.activity.activity_detector import ActivityDetector
from ai.anpr.anpr_processor import ANPRProcessor
from ai.detection.detector import Detection, Detector
from ai.face.face_detector import FaceDetector
from ai.intrusion.virtual_fence import VirtualFence
from ai.tracking.tracker import CentroidTracker
from ai.utils.backend_client import BackendClientError, send_detection, get_camera_zones
from ai.utils.config import get_settings
from ai.utils.logger import get_logger
from ai.video.frame_processor import FrameProcessor
from ai.video.video_stream import VideoStream

log = get_logger(__name__)

# YOLOv8's default COCO weights use these class names for anything with
# wheels — this is what "vehicle detected" means for ANPR purposes.
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

# How many frames a track must go unseen before we're willing to fire a
# fresh ANPR alert for the "same" track ID again (e.g. it re-enters frame).
ANPR_COOLDOWN_FRAMES = 60


def _severity_for(activity: str) -> str:
    return {
        "rapid_movement": "medium",
        "wrong_direction": "high",
        "loitering": "low",
        "vehicle_loitering": "high",
    }.get(activity, "low")


class Pipeline:
    def __init__(
        self,
        camera_id: str,
        run_face: bool = True,
        run_activity: bool = True,
        run_anpr: bool = True,
        # Dependency injection hooks — real objects are constructed by
        # default (and Detector() requires torch/ultralytics to be
        # installed), but tests can pass in fakes here to exercise the
        # pipeline's wiring logic without needing a real model loaded.
        detector: Optional[Detector] = None,
        tracker: Optional[CentroidTracker] = None,
        face_detector: Optional[FaceDetector] = None,
        activity_detector: Optional[ActivityDetector] = None,
        anpr_processor: Optional[ANPRProcessor] = None,
        frame_callback=None,
    ):
        settings = get_settings()
        self._camera_id = camera_id
        self._frame_callback = frame_callback
        self._detector = detector if detector is not None else Detector()
        self._tracker = tracker if tracker is not None else CentroidTracker()
        self._face_detector = (face_detector if face_detector is not None else FaceDetector()) if run_face else None
        self._activity_detector = (
            activity_detector if activity_detector is not None else ActivityDetector()
        ) if run_activity else None
        self._anpr = (anpr_processor if anpr_processor is not None else ANPRProcessor()) if run_anpr else None

        self._fence: Optional[VirtualFence] = None
        if settings.fence_zone:
            polygon = json.loads(settings.fence_zone)
            self._fence = VirtualFence(polygon)
            log.info("Virtual fence active with %d points", len(polygon))

        # track_id -> last frame index an ANPR alert was fired for it
        self._anpr_last_emitted: Dict[int, int] = {}
        self._frame_index = 0
        self._last_zone_refresh = -9999
        self._fps_started = time.perf_counter()
        self._fps_frames = 0
        self._fps = 0.0
        # Aggregated object counts for recorded-video history. These are
        # persisted once per analysis job instead of creating one DB row per frame.
        self._class_counts: Dict[str, int] = {}
        self._event_counts: Dict[str, int] = {}

    def _refresh_zones(self):
        zones = get_camera_zones(self._camera_id)
        self._last_zone_refresh = self._frame_index
        if zones:
            zone = next((z for z in zones if z.get("enabled", True) and len(z.get("points", [])) >= 3), None)
            if zone:
                self._fence = VirtualFence([(float(p["x"]), float(p["y"])) for p in zone["points"]])
                return
        # Keep env-configured fence if backend has no saved zone.

    def _report(self, alert_type: str, severity: str, confidence: float, description: str):
        try:
            send_detection(
                camera_id=self._camera_id,
                alert_type=alert_type,
                severity=severity,
                confidence=confidence,
                description=description,
            )
        except BackendClientError as exc:
            # Don't crash the whole pipeline because the backend hiccupped
            # once — log it and keep processing frames.
            log.warning("Failed to report %s: %s", alert_type, exc)

    def _anpr_can_emit(self, track_id: int) -> bool:
        last = self._anpr_last_emitted.get(track_id)
        return last is None or (self._frame_index - last) > ANPR_COOLDOWN_FRAMES

    def _draw_overlay(self, frame, detections, faces, events):
        """Draw AI results onto the frame that is sent to the browser preview."""
        for detection in detections:
            x1, y1, x2, y2 = map(int, detection.bbox)
            label = f"{detection.class_name} {detection.confidence:.0%}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 8, y1), (0, 255, 0), -1)
            cv2.putText(frame, label, (x1 + 4, max(th + 2, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)

        for tid, bbox in getattr(self, "_current_tracked", {}).items():
            x1,y1,x2,y2=map(int,bbox)
            cv2.putText(frame, f"ID {tid}", (x1, min(frame.shape[0]-8, y2+18)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2, cv2.LINE_AA)

        if self._fence is not None:
            pts = np.array(self._fence._polygon, dtype=np.int32)
            cv2.polylines(frame, [pts], True, (255, 80, 80), 2)

        for x, y, w, h in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 200, 0), 2)
            cv2.putText(frame, "FACE", (x, max(20, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 2, cv2.LINE_AA)

        # Show the most useful AI events in a compact banner.
        event_text = [f"FPS {self._fps:.1f}"]
        for event in events:
            if event.get("type") == "anpr" and event.get("plate"):
                event_text.append(f"PLATE: {event['plate']}")
            elif event.get("type") == "intrusion":
                event_text.append("INTRUSION")
            elif event.get("type") == "activity":
                event_text.append(str(event.get("activity", "ACTIVITY")).upper())
        banner = "  |  ".join(event_text)
        if banner:
            cv2.rectangle(frame, (0, 0), (frame.shape[1], 38), (20, 20, 20), -1)
            cv2.putText(frame, banner[:120], (12, 26), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, (255, 255, 255), 2, cv2.LINE_AA)

    def process_frame(self, frame) -> dict:
        """Run AI and return a summary. The frame is annotated for the live preview."""
        self._frame_index += 1
        self._fps_frames += 1
        elapsed=time.perf_counter()-self._fps_started
        if elapsed >= 1.0:
            self._fps=self._fps_frames/elapsed; self._fps_frames=0; self._fps_started=time.perf_counter()

        if self._frame_index - self._last_zone_refresh >= 60:
            self._refresh_zones()
        detections: List[Detection] = self._detector.detect(frame)
        for detection in detections:
            name = str(detection.class_name).strip().lower() or "unknown"
            self._class_counts[name] = self._class_counts.get(name, 0) + 1
        bboxes = [d.bbox for d in detections]
        tracked = self._tracker.update(bboxes)
        bbox_to_detection = {d.bbox: d for d in detections}

        self._current_tracked = tracked
        summary = {"detections": len(detections), "tracked": len(tracked), "events": []}
        faces = []

        if self._fence:
            entered = self._fence.check(tracked)
            for track_id in entered:
                self._report("intrusion", "critical", 0.9, f"Track {track_id} entered restricted zone")
                self._event_counts["intrusion"] = self._event_counts.get("intrusion", 0) + 1
                summary["events"].append({"type": "intrusion", "track_id": track_id})

        if self._anpr:
            for track_id, bbox in tracked.items():
                detection = bbox_to_detection.get(bbox)
                if detection is None or detection.class_name not in VEHICLE_CLASSES:
                    continue
                if not self._anpr_can_emit(track_id):
                    continue

                plate_text = self._anpr.read_plate_for_vehicle(frame, bbox)
                if not plate_text:
                    continue

                self._anpr_last_emitted[track_id] = self._frame_index
                self._report("anpr", "high", detection.confidence, f"Vehicle ({detection.class_name}, track {track_id}) — plate {plate_text}")
                self._event_counts["anpr"] = self._event_counts.get("anpr", 0) + 1
                summary["events"].append({"type": "anpr", "track_id": track_id, "plate": plate_text})

        if self._face_detector:
            faces = self._face_detector.detect(frame)
            if faces:
                self._event_counts["face"] = self._event_counts.get("face", 0) + len(faces)
                summary["events"].append({"type": "face", "count": len(faces)})

        if self._activity_detector:
            class_by_id = {tid: bbox_to_detection.get(bbox).class_name for tid,bbox in tracked.items() if bbox_to_detection.get(bbox)}
            for event in self._activity_detector.update(tracked, class_by_id):
                severity = _severity_for(event["activity"])
                self._report("activity", severity, 0.7,
                             f"Track {event['track_id']} — {event['activity']}")
                self._event_counts["activity"] = self._event_counts.get("activity", 0) + 1
                summary["events"].append(event)

        self._draw_overlay(frame, detections, faces, summary["events"])
        return summary

    def analysis_summary(self) -> dict:
        """Return accumulated recorded-video findings for persistence/history."""
        return {
            "objects": dict(sorted(self._class_counts.items(), key=lambda item: (-item[1], item[0]))),
            "events": dict(sorted(self._event_counts.items(), key=lambda item: (-item[1], item[0]))),
        }

    def run(self, source: Optional[str] = None, process_every_n: int = 1, loop: bool = False):
        """
        source: webcam index or video file path (falls back to .env
                CAMERA_SOURCE if not given).
        loop:   if True and the source is a video file that reaches its
                end, reopen it and keep going — useful for a short demo
                clip you want to keep running during a live demo instead
                of the pipeline just stopping.
        """
        source = source or get_settings().camera_source
        while True:
            try:
                with VideoStream(source) as stream:
                    processor = FrameProcessor(stream, process_every_n=process_every_n)
                    for frame in processor.frames():
                        self.process_frame(frame)
                        if self._frame_callback is not None:
                            self._frame_callback(frame)
            except RuntimeError as exc:
                # Do not spin or crash immediately on a temporary camera
                # outage. A persistent worker gives the operator time to
                # restore an RTSP camera/network connection.
                log.error("Video source unavailable: %s", exc)
                if not loop:
                    time.sleep(2)
                    continue
            if not loop:
                return
            log.info("Video source ended — looping (--loop was set).")
