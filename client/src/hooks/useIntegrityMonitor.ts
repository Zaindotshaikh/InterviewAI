import { useCallback, useEffect, useRef, useState } from "react";
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
import type { IntegrityEvent, IntegrityFlagType } from "../lib/integrity";

type ActiveFlag = {
  type: IntegrityFlagType;
  startMs: number;
};

type Options = {
  /** When false, monitor is idle (e.g. before interview is live). */
  enabled?: boolean;
};

type Landmark = { x: number; y: number; z?: number; visibility?: number; presence?: number };
type FaceBox = { minX: number; maxX: number; minY: number; maxY: number };

const SAMPLE_MS = 500;
const NO_FACE_CHECKS = 4; // ~2s; tolerate brief detector blips
const MULTIPLE_FACE_CHECKS = 4; // ~2s; ghosts during head-turn are 1–2 frames
const LOOK_AWAY_MS = 3500;
const YAW_THRESHOLD_DEG = 30;
/** Only for multi-face filtering (not for presence / no_face). */
const FACE_QUALITY_MIN = 0.55;
const FACE_IOU_MERGE = 0.35;

/**
 * Estimate yaw (degrees) from MediaPipe facial transformation matrix (column-major 4x4).
 */
function yawFromMatrix(matrixData: number[] | Float32Array): number {
  const r02 = matrixData[8];
  const r22 = matrixData[10];
  const r00 = matrixData[0];
  const yaw = (Math.atan2(r02, r22) * 180) / Math.PI;
  if (Number.isFinite(yaw) && Math.abs(yaw) > 0.01) return yaw;
  return (Math.atan2(r02, r00) * 180) / Math.PI;
}

function yawFromLandmarks(landmarks: Landmark[]): number {
  const leftEye = landmarks[33];
  const rightEye = landmarks[263];
  const nose = landmarks[1];
  if (!leftEye || !rightEye || !nose) return 0;
  const eyeDist = Math.abs(rightEye.x - leftEye.x) || 0.001;
  const midX = (leftEye.x + rightEye.x) / 2;
  const offset = (nose.x - midX) / eyeDist;
  return offset * 60;
}

function faceBox(landmarks: Landmark[]): FaceBox {
  let minX = 1;
  let maxX = 0;
  let minY = 1;
  let maxY = 0;
  for (const p of landmarks) {
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  }
  return { minX, maxX, minY, maxY };
}

function boxIou(a: FaceBox, b: FaceBox): number {
  const x1 = Math.max(a.minX, b.minX);
  const y1 = Math.max(a.minY, b.minY);
  const x2 = Math.min(a.maxX, b.maxX);
  const y2 = Math.min(a.maxY, b.maxY);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  if (inter <= 0) return 0;
  const areaA = Math.max(0, a.maxX - a.minX) * Math.max(0, a.maxY - a.minY);
  const areaB = Math.max(0, b.maxX - b.minX) * Math.max(0, b.maxY - b.minY);
  const union = areaA + areaB - inter;
  return union > 0 ? inter / union : 0;
}

/**
 * Score used only to reject multi-face ghosts, never to decide "no face".
 * Close-up faces often fill most of the PiP; that must still count as valid.
 */
function faceQualityScore(landmarks: Landmark[]): number {
  if (!landmarks?.length) return 0;

  const keyIdx = [1, 33, 263, 61, 291, 10, 152];
  let presenceSum = 0;
  let presenceN = 0;
  for (const i of keyIdx) {
    const p = landmarks[i];
    if (!p) continue;
    const score = p.presence ?? p.visibility;
    if (typeof score === "number" && Number.isFinite(score)) {
      presenceSum += score;
      presenceN += 1;
    }
  }
  // Many builds omit presence/visibility; treat as usable, don't zero the face out
  const presence = presenceN > 0 ? presenceSum / presenceN : 1;

  const box = faceBox(landmarks);
  const w = Math.max(0, box.maxX - box.minX);
  const h = Math.max(0, box.maxY - box.minY);
  const area = w * h;
  // Tiny fragments only (ghosts). Large / close-up faces are fine.
  if (area < 0.01 || w < 0.08 || h < 0.08) return Math.min(presence, 0.35);
  return presence;
}

/** Any MediaPipe landmark set = someone is in frame (for no_face). */
function hasAnyFace(faceLandmarks: Landmark[][] | undefined): boolean {
  return Boolean(faceLandmarks?.some((f) => f && f.length > 0));
}

/**
 * Distinct faces for multi-person check. Merges overlapping same-face ghosts.
 * Does not affect presence / no_face.
 */
function countDistinctFaces(faceLandmarks: Landmark[][] | undefined): number {
  if (!faceLandmarks?.length) return 0;

  const scored = faceLandmarks
    .map((landmarks) => ({
      landmarks,
      quality: faceQualityScore(landmarks),
      box: faceBox(landmarks),
    }))
    .filter((f) => f.quality >= FACE_QUALITY_MIN)
    .sort((a, b) => b.quality - a.quality);

  const kept: typeof scored = [];
  for (const face of scored) {
    const overlaps = kept.some((k) => boxIou(k.box, face.box) >= FACE_IOU_MERGE);
    if (!overlaps) kept.push(face);
  }
  return kept.length;
}

/**
 * Client-side only proctoring via MediaPipe Face Landmarker.
 * Does not touch Realtime audio / WebRTC voice path.
 */
export function useIntegrityMonitor(options: Options = {}) {
  const { enabled = true } = options;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const landmarkerRef = useRef<FaceLandmarker | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const eventsRef = useRef<IntegrityEvent[]>([]);
  const activeFlagsRef = useRef<Partial<Record<IntegrityFlagType, ActiveFlag>>>({});
  const noFaceStreakRef = useRef(0);
  const multiFaceStreakRef = useRef(0);
  const lookAwaySinceRef = useRef<number | null>(null);
  const [available, setAvailable] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "active" | "unavailable">(
    "idle",
  );
  const [events, setEvents] = useState<IntegrityEvent[]>([]);
  const [liveWarnings, setLiveWarnings] = useState<IntegrityFlagType[]>([]);

  const syncLiveWarnings = useCallback(() => {
    setLiveWarnings(Object.keys(activeFlagsRef.current) as IntegrityFlagType[]);
  }, []);

  const closeFlag = useCallback(
    (type: IntegrityFlagType, endMs: number) => {
      const active = activeFlagsRef.current[type];
      if (!active) return;
      const durationSeconds = Math.max(0.5, (endMs - active.startMs) / 1000);
      const event: IntegrityEvent = {
        type,
        startTime: new Date(active.startMs).toISOString(),
        endTime: new Date(endMs).toISOString(),
        durationSeconds: Math.round(durationSeconds * 10) / 10,
      };
      eventsRef.current = [...eventsRef.current, event];
      setEvents(eventsRef.current);
      delete activeFlagsRef.current[type];
      syncLiveWarnings();
    },
    [syncLiveWarnings],
  );

  const openFlag = useCallback(
    (type: IntegrityFlagType, startMs: number) => {
      if (activeFlagsRef.current[type]) return;
      activeFlagsRef.current[type] = { type, startMs };
      syncLiveWarnings();
    },
    [syncLiveWarnings],
  );

  const flushOpenFlags = useCallback(() => {
    const now = Date.now();
    (Object.keys(activeFlagsRef.current) as IntegrityFlagType[]).forEach((t) => {
      closeFlag(t, now);
    });
  }, [closeFlag]);

  const getEvents = useCallback(() => {
    flushOpenFlags();
    return [...eventsRef.current];
  }, [flushOpenFlags]);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let intervalId = 0;

    async function start() {
      setStatus("loading");
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;

        const video = videoRef.current;
        if (!video) {
          throw new Error("Video element not ready");
        }
        video.srcObject = stream;
        await video.play().catch(() => undefined);

        const vision = await FilesetResolver.forVisionTasks(
          "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm",
        );

        const landmarker = await FaceLandmarker.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath:
              "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
            delegate: "GPU",
          },
          runningMode: "VIDEO",
          numFaces: 3,
          // Keep presence detection stable; multi-face ghosts filtered in JS
          minFaceDetectionConfidence: 0.5,
          minFacePresenceConfidence: 0.5,
          minTrackingConfidence: 0.5,
          outputFaceBlendshapes: false,
          outputFacialTransformationMatrixes: true,
        });

        if (cancelled) {
          landmarker.close();
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        landmarkerRef.current = landmarker;
        setAvailable(true);
        setStatus("active");

        intervalId = window.setInterval(() => {
          const lm = landmarkerRef.current;
          const vid = videoRef.current;
          if (!lm || !vid || vid.readyState < 2) return;

          const now = Date.now();
          let result;
          try {
            result = lm.detectForVideo(vid, now);
          } catch {
            return;
          }

          const landmarks = result.faceLandmarks as Landmark[][] | undefined;
          // Presence = raw detector output. Do NOT apply multi-face quality filters here
          // (those were rejecting close-up valid faces → false "FACE NOT VISIBLE").
          const present = hasAnyFace(landmarks);
          const distinctFaces = countDistinctFaces(landmarks);

          // --- no face ---
          if (!present) {
            noFaceStreakRef.current += 1;
            multiFaceStreakRef.current = 0;
            lookAwaySinceRef.current = null;
            if (activeFlagsRef.current.looked_away) closeFlag("looked_away", now);
            if (activeFlagsRef.current.multiple_faces) closeFlag("multiple_faces", now);
            if (noFaceStreakRef.current >= NO_FACE_CHECKS) {
              openFlag("no_face", now - NO_FACE_CHECKS * SAMPLE_MS);
            }
            return;
          }

          noFaceStreakRef.current = 0;
          if (activeFlagsRef.current.no_face) closeFlag("no_face", now);

          // --- multiple faces (must persist; ignore 1–2 frame ghosts) ---
          if (distinctFaces > 1) {
            multiFaceStreakRef.current += 1;
            if (multiFaceStreakRef.current >= MULTIPLE_FACE_CHECKS) {
              openFlag(
                "multiple_faces",
                now - (MULTIPLE_FACE_CHECKS - 1) * SAMPLE_MS,
              );
            }
          } else {
            multiFaceStreakRef.current = 0;
            if (activeFlagsRef.current.multiple_faces) closeFlag("multiple_faces", now);
          }

          // --- head turned away ---
          let yaw = 0;
          const matrix = result.facialTransformationMatrixes?.[0];
          if (matrix?.data && matrix.data.length >= 16) {
            yaw = yawFromMatrix(matrix.data);
          } else if (landmarks?.[0]) {
            yaw = yawFromLandmarks(landmarks[0]);
          }

          // While a confirmed multi-face warning is active, skip look-away noise
          if (activeFlagsRef.current.multiple_faces) {
            lookAwaySinceRef.current = null;
            if (activeFlagsRef.current.looked_away) closeFlag("looked_away", now);
            return;
          }

          if (Math.abs(yaw) > YAW_THRESHOLD_DEG) {
            if (lookAwaySinceRef.current == null) lookAwaySinceRef.current = now;
            const elapsed = now - lookAwaySinceRef.current;
            if (elapsed >= LOOK_AWAY_MS) {
              openFlag("looked_away", lookAwaySinceRef.current);
            }
          } else {
            lookAwaySinceRef.current = null;
            if (activeFlagsRef.current.looked_away) closeFlag("looked_away", now);
          }
        }, SAMPLE_MS);
      } catch (err) {
        console.warn("Integrity monitor unavailable:", err);
        if (!cancelled) {
          setAvailable(false);
          setStatus("unavailable");
        }
      }
    }

    // Defer one frame so videoRef is mounted
    const boot = window.setTimeout(() => void start(), 50);

    return () => {
      cancelled = true;
      window.clearTimeout(boot);
      if (intervalId) window.clearInterval(intervalId);
      flushOpenFlags();
      landmarkerRef.current?.close();
      landmarkerRef.current = null;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
    };
  }, [enabled, closeFlag, openFlag, flushOpenFlags]);

  return {
    videoRef,
    available,
    status,
    events,
    liveWarnings,
    getEvents,
  };
}
