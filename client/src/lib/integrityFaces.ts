/**
 * Pure helpers for video proctoring face counting / head pose.
 * FaceDetector boxes are preferred for multi-person; landmarks for look-away.
 */

export type NormBox = { minX: number; maxX: number; minY: number; maxY: number };
export type Landmark = { x: number; y: number; z?: number; visibility?: number; presence?: number };

export type DetectorBoxInput = {
  score: number;
  /** Pixel bounding box from MediaPipe FaceDetector */
  originX: number;
  originY: number;
  width: number;
  height: number;
};

/** Multi-face: reject tiny ghosts; keep real second people. */
export const FACE_DETECT_SCORE_MIN = 0.55;
export const FACE_DETECT_AREA_MIN = 0.012;
export const FACE_DETECT_IOU_MERGE = 0.4;

export function boxIou(a: NormBox, b: NormBox): number {
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
 * Count distinct faces from FaceDetector outputs (normalized by frame size).
 * Merges overlapping duplicates; filters low-score / tiny boxes.
 */
export function countFacesFromDetections(
  detections: DetectorBoxInput[],
  frameW: number,
  frameH: number,
): number {
  if (!detections.length || frameW <= 0 || frameH <= 0) return 0;

  const scored = detections
    .map((d) => {
      const minX = d.originX / frameW;
      const minY = d.originY / frameH;
      const maxX = (d.originX + d.width) / frameW;
      const maxY = (d.originY + d.height) / frameH;
      const w = Math.max(0, maxX - minX);
      const h = Math.max(0, maxY - minY);
      return {
        score: d.score,
        area: w * h,
        box: { minX, maxX, minY, maxY } as NormBox,
      };
    })
    .filter(
      (f) =>
        f.score >= FACE_DETECT_SCORE_MIN &&
        f.area >= FACE_DETECT_AREA_MIN &&
        f.box.maxX > f.box.minX &&
        f.box.maxY > f.box.minY,
    )
    .sort((a, b) => b.score - a.score);

  const kept: typeof scored = [];
  for (const face of scored) {
    const overlaps = kept.some((k) => boxIou(k.box, face.box) >= FACE_DETECT_IOU_MERGE);
    if (!overlaps) kept.push(face);
  }
  return kept.length;
}

/**
 * Estimate yaw (degrees) from MediaPipe facial transformation matrix (column-major 4x4).
 */
export function yawFromMatrix(matrixData: number[] | Float32Array): number {
  const r02 = matrixData[8];
  const r22 = matrixData[10];
  const r00 = matrixData[0];
  const yaw = (Math.atan2(r02, r22) * 180) / Math.PI;
  if (Number.isFinite(yaw) && Math.abs(yaw) > 0.01) return yaw;
  return (Math.atan2(r02, r00) * 180) / Math.PI;
}

/**
 * Estimate pitch (degrees). Positive ≈ looking down (notes / phone).
 */
export function pitchFromMatrix(matrixData: number[] | Float32Array): number {
  const r12 = matrixData[9];
  const clamped = Math.max(-1, Math.min(1, -r12));
  return (Math.asin(clamped) * 180) / Math.PI;
}

export function yawFromLandmarks(landmarks: Landmark[]): number {
  const leftEye = landmarks[33];
  const rightEye = landmarks[263];
  const nose = landmarks[1];
  if (!leftEye || !rightEye || !nose) return 0;
  const eyeDist = Math.abs(rightEye.x - leftEye.x) || 0.001;
  const midX = (leftEye.x + rightEye.x) / 2;
  const offset = (nose.x - midX) / eyeDist;
  return offset * 60;
}

/** Fallback when FaceDetector is unavailable: landmark sets with basic quality filter. */
export function countDistinctLandmarkFaces(
  faceLandmarks: Landmark[][] | undefined,
  qualityMin = 0.55,
  iouMerge = 0.35,
): number {
  if (!faceLandmarks?.length) return 0;

  const scored: { quality: number; box: NormBox }[] = [];
  for (const landmarks of faceLandmarks) {
    if (!landmarks?.length) continue;
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
    const w = Math.max(0, maxX - minX);
    const h = Math.max(0, maxY - minY);
    const area = w * h;
    const quality = area < 0.01 || w < 0.08 || h < 0.08 ? 0.35 : 1;
    if (quality < qualityMin) continue;
    scored.push({ quality, box: { minX, maxX, minY, maxY } });
  }
  scored.sort((a, b) => b.quality - a.quality);

  const kept: typeof scored = [];
  for (const face of scored) {
    const overlaps = kept.some((k) => boxIou(k.box, face.box) >= iouMerge);
    if (!overlaps) kept.push(face);
  }
  return kept.length;
}
