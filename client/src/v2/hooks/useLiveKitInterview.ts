import { useCallback, useEffect, useRef, useState } from "react";
import {
  ConnectionState,
  Room,
  RoomEvent,
  Track,
  type RemoteTrack,
  type RemoteTrackPublication,
} from "livekit-client";

export type LiveKitPhase = "idle" | "connecting" | "live" | "reconnecting" | "ended" | "error";

export type Caption = {
  id: string;
  role: "user" | "assistant";
  text: string;
  final: boolean;
};

type Options = {
  url: string;
  token: string;
  /** Must be called from a user gesture on iOS before connect. */
  unlockAudio?: boolean;
};

export function useLiveKitInterview() {
  const roomRef = useRef<Room | null>(null);
  const [phase, setPhase] = useState<LiveKitPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [canPlayAudio, setCanPlayAudio] = useState(true);
  const [remoteAudioReady, setRemoteAudioReady] = useState(false);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [remoteVideoStream, setRemoteVideoStream] = useState<MediaStream | null>(null);
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [connectionQuality, setConnectionQuality] = useState<"excellent" | "good" | "poor" | "unknown">(
    "unknown",
  );

  const disconnect = useCallback(async () => {
    const room = roomRef.current;
    roomRef.current = null;
    if (room) {
      await room.disconnect();
    }
    setLocalStream(null);
    setRemoteStream(null);
    setRemoteVideoStream(null);
    setPhase("ended");
  }, []);

  const connect = useCallback(async (opts: Options) => {
    setError(null);
    setPhase("connecting");
    setCaptions([]);

    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
      // Prefer WebAudio mix for Safari background quirks
      // @ts-expect-error experimental option varies by SDK version
      expWebAudioMix: true,
    });
    roomRef.current = room;

    room.on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
      if (state === ConnectionState.Connected) setPhase("live");
      else if (state === ConnectionState.Reconnecting) setPhase("reconnecting");
      else if (state === ConnectionState.Disconnected) setPhase((p) => (p === "ended" ? p : "ended"));
    });

    room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      setCanPlayAudio(room.canPlaybackAudio);
    });

    room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack, publication: RemoteTrackPublication) => {
      if (track.kind === Track.Kind.Audio) {
        // The agent's background_audio track (typing sounds) must not replace its voice stream.
        if (publication.trackName !== "background_audio") {
          setRemoteStream(new MediaStream([track.mediaStreamTrack]));
          setRemoteAudioReady(true);
        }
        // Attach to a hidden audio element as backup
        const el = track.attach();
        el.setAttribute("playsinline", "true");
        el.style.display = "none";
        document.body.appendChild(el);
        void el.play().catch(() => setCanPlayAudio(false));
      } else if (track.kind === Track.Kind.Video) {
        setRemoteVideoStream(new MediaStream([track.mediaStreamTrack]));
      }
    });

    room.on(RoomEvent.TrackPublished, (publication: RemoteTrackPublication) => {
      if (publication.kind === Track.Kind.Video && !publication.isSubscribed) {
        publication.setSubscribed(true);
      }
    });

    room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
      track.detach().forEach((el) => el.remove());
      if (track.kind === Track.Kind.Video) {
        setRemoteVideoStream(null);
      }
    });

    room.on(RoomEvent.ConnectionQualityChanged, (_q, participant) => {
      if (participant.isLocal) return;
      // ConnectionQuality enum: Excellent=3, Good=2, Poor=1, Lost=0
      const q = participant.connectionQuality as unknown as number | string;
      if (q === 3 || q === "excellent") setConnectionQuality("excellent");
      else if (q === 2 || q === "good") setConnectionQuality("good");
      else if (q === 1 || q === "poor" || q === 0 || q === "lost") setConnectionQuality("poor");
      else setConnectionQuality("unknown");
    });

    try {
      // iOS: unlock audio inside the same user gesture that triggered connect
      if (opts.unlockAudio !== false) {
        try {
          await room.startAudio();
        } catch {
          setCanPlayAudio(false);
        }
      }

      await room.connect(opts.url, opts.token, { autoSubscribe: true });

      for (const participant of room.remoteParticipants.values()) {
        for (const publication of participant.trackPublications.values()) {
          if (publication.kind === Track.Kind.Video) {
            if (!publication.isSubscribed) publication.setSubscribed(true);
            const existing = publication.track;
            if (existing) {
              setRemoteVideoStream(new MediaStream([existing.mediaStreamTrack]));
            }
          }
        }
      }

      // Mic: echo cancel on, browser NS off (agent-side isolation), AGC on
      await room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: false,
        autoGainControl: true,
      });

      const micPub = room.localParticipant.getTrackPublication(Track.Source.Microphone);
      const micTrack = micPub?.track;
      if (micTrack?.mediaStreamTrack) {
        setLocalStream(new MediaStream([micTrack.mediaStreamTrack]));
      }

      setPhase("live");
      setCanPlayAudio(room.canPlaybackAudio);
    } catch (err) {
      console.error("LiveKit connect failed", err);
      setError(err instanceof Error ? err.message : "Failed to connect");
      setPhase("error");
      await room.disconnect().catch(() => undefined);
      roomRef.current = null;
    }
  }, []);

  const unlockAudio = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    try {
      await room.startAudio();
      setCanPlayAudio(room.canPlaybackAudio);
    } catch (err) {
      console.warn("startAudio failed", err);
      setCanPlayAudio(false);
    }
  }, []);

  useEffect(() => {
    return () => {
      void disconnect();
    };
  }, [disconnect]);

  return {
    phase,
    error,
    canPlayAudio,
    remoteAudioReady,
    localStream,
    remoteStream,
    remoteVideoStream,
    captions,
    connectionQuality,
    connect,
    disconnect,
    unlockAudio,
    room: roomRef,
  };
}
