import { useCallback, useEffect, useRef, useState } from "react";
import {
  FaceDetector,
  FaceLandmarker,
  FilesetResolver,
} from "@mediapipe/tasks-vision";
import type { IntegrityEvent, IntegrityFlagType } from "../lib/integrity";
import {
  countFacesFromDetections,
  pitchFromMatrix,
  yawFromLandmarks,
  yawFromMatrix,
  type Landmark,
} from "../lib/integrityFaces";

type ActiveFlag = {
  type: IntegrityFlagType;
  startMs: number;
};

type Options = {
  /** When false, monitor is idle (e.g. before interview is live). */
  enabled?: boolean;
};

const SAMPLE_MS = 500;
const NO_FACE_CHECKS = 4; // ~2s; tolerate brief detector blips
const MULTIPLE_FACE_CHECKS = 3; // ~1.5s with FaceDetector (more stable than landmarker)
const LOOK_AWAY_MS = 3500;
const YAW_THRESHOLD_DEG = 30;
const PITCH_THRESHOLD_DEG = 28; // looking down at notes / phone
const WASM_CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const FACE_DETECTOR_MODEL =
  "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite";
const FACE_LANDMARKER_MODEL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

/**
 * Client-side proctoring: FaceDetector for presence / multi-face,
 * FaceLandmarker for look-away (yaw + pitch). Same IntegrityEvent flow as before.
 */
export function useIntegrityMonitor(options: Options = {}) {
  const { enabled = true } = options;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const detectorRef = useRef<FaceDetector | null>(null);
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

    async function createWithDelegate<T>(
      factory: (delegate: "GPU" | "CPU") => Promise<T>,
    ): Promise<T> {
      try {
        return await factory("GPU");
      } catch {
        return await factory("CPU");
      }
    }

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

        const vision = await FilesetResolver.forVisionTasks(WASM_CDN);

        // FaceDetector is built for counting people; FaceLandmarker is weak at multi-face.
        const detector = await createWithDelegate((delegate) =>
          FaceDetector.createFromOptions(vision, {
            baseOptions: {
              modelAssetPath: FACE_DETECTOR_MODEL,
              delegate,
            },
            runningMode: "VIDEO",
            minDetectionConfidence: 0.5,
            minSuppressionThreshold: 0.3,
          }),
        );

        if (cancelled) {
          detector.close();
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        let landmarker: FaceLandmarker | null = null;
        try {
          landmarker = await createWithDelegate((delegate) =>
            FaceLandmarker.createFromOptions(vision, {
              baseOptions: {
                modelAssetPath: FACE_LANDMARKER_MODEL,
                delegate,
              },
              runningMode: "VIDEO",
              numFaces: 1,
              minFaceDetectionConfidence: 0.5,
              minFacePresenceConfidence: 0.5,
              minTrackingConfidence: 0.5,
              outputFaceBlendshapes: false,
              outputFacialTransformationMatrixes: true,
            }),
          );
        } catch (err) {
          console.warn("Face landmarker unavailable; look-away disabled:", err);
        }

        if (cancelled) {
          detector.close();
          landmarker?.close();
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        detectorRef.current = detector;
        landmarkerRef.current = landmarker;
        setAvailable(true);
        setStatus("active");

        const onTrackEnded = () => {
          const now = Date.now();
          openFlag("no_face", now);
          if (activeFlagsRef.current.multiple_faces) closeFlag("multiple_faces", now);
          if (activeFlagsRef.current.looked_away) closeFlag("looked_away", now);
        };
        stream.getVideoTracks().forEach((t) => t.addEventListener("ended", onTrackEnded));

        intervalId = window.setInterval(() => {
          const det = detectorRef.current;
          const lm = landmarkerRef.current;
          const vid = videoRef.current;
          if (!det || !vid || vid.readyState < 2) return;

          const now = Date.now();
          const frameW = vid.videoWidth || 640;
          const frameH = vid.videoHeight || 480;

          let faceCount = 0;
          try {
            const detection = det.detectForVideo(vid, now);
            const boxes = (detection.detections ?? []).map((d) => {
              const score = d.categories?.[0]?.score ?? 0;
              const box = d.boundingBox;
              return {
                score,
                originX: box?.originX ?? 0,
                originY: box?.originY ?? 0,
                width: box?.width ?? 0,
                height: box?.height ?? 0,
              };
            });
            faceCount = countFacesFromDetections(boxes, frameW, frameH);
          } catch {
            return;
          }

          // --- no face ---
          if (faceCount === 0) {
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

          // --- multiple faces ---
          if (faceCount > 1) {
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

          // While multi-face is active, skip look-away (noisy / wrong primary face)
          if (activeFlagsRef.current.multiple_faces || faceCount > 1) {
            lookAwaySinceRef.current = null;
            if (activeFlagsRef.current.looked_away) closeFlag("looked_away", now);
            return;
          }

          // --- head turned / looking down ---
          if (!lm) return;

          let yaw = 0;
          let pitch = 0;
          try {
            const result = lm.detectForVideo(vid, now + 1);
            const matrix = result.facialTransformationMatrixes?.[0];
            const landmarks = result.faceLandmarks as Landmark[][] | undefined;
            if (matrix?.data && matrix.data.length >= 16) {
              yaw = yawFromMatrix(matrix.data);
              pitch = pitchFromMatrix(matrix.data);
            } else if (landmarks?.[0]) {
              yaw = yawFromLandmarks(landmarks[0]);
            }
          } catch {
            return;
          }

          const lookingAway =
            Math.abs(yaw) > YAW_THRESHOLD_DEG || pitch > PITCH_THRESHOLD_DEG;

          if (lookingAway) {
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
      detectorRef.current?.close();
      detectorRef.current = null;
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
