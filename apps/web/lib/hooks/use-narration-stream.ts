"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { streamAnalyst, type AnalystMode, type PipelineConfig } from "../api";
import type {
  CitationRef,
  CitationsFrame,
  DoneFrame,
  ErrorFrame,
  StartFrame,
  TokenFrame,
} from "../types";

export type Mode = AnalystMode;
export type Status = "idle" | "streaming" | "done" | "error" | "cancelled";

export interface ModeState {
  status: Status;
  text: string;
  tokens: number;
  // Real LLM wall-time, not the typewriter playback duration.
  genMs: number | null;
  error: string | null;
  // cached = disk cache served it (no Ollama call); fellBack = gate rejected the
  // draft, deterministic fallback used.
  citations: CitationRef[];
  cached: boolean;
  fellBack: boolean;
  modelId: string | null;
}

const MODE_KEYS: Mode[] = ["explanation", "outlook", "risk", "differentiator"];

// Malformed frame → null (caller skips it).
function parseFrame<T>(data: string): T | null {
  try {
    return JSON.parse(data) as T;
  } catch {
    return null;
  }
}

const INITIAL: ModeState = {
  status: "idle",
  text: "",
  tokens: 0,
  genMs: null,
  error: null,
  citations: [],
  cached: false,
  fellBack: false,
  modelId: null,
};

const freshStates = (): Record<Mode, ModeState> => ({
  explanation: { ...INITIAL },
  outlook: { ...INITIAL },
  risk: { ...INITIAL },
  differentiator: { ...INITIAL },
});

// Owns the four parallel analyst streams: per-mode state, abort lifecycle, and
// reset-on-scenario-change.
export function useNarrationStream(
  scenarioId: string | null,
  config: PipelineConfig,
) {
  const [states, setStates] = useState<Record<Mode, ModeState>>(freshStates);

  // Read via refs so startMode keeps a stable identity — nuqs churns `config`
  // each render, and an unstable startMode would break ReadingPane's memo.
  const scenarioIdRef = useRef(scenarioId);
  scenarioIdRef.current = scenarioId;
  const configRef = useRef(config);
  configRef.current = config;

  const abortRefs = useRef<Record<Mode, AbortController | null>>({
    explanation: null,
    outlook: null,
    risk: null,
    differentiator: null,
  });

  const setMode = useCallback((mode: Mode, patch: Partial<ModeState>) => {
    setStates((s) => ({ ...s, [mode]: { ...s[mode], ...patch } }));
  }, []);

  const stopMode = useCallback((mode: Mode) => {
    abortRefs.current[mode]?.abort();
  }, []);

  const stopAll = useCallback(() => {
    (Object.keys(abortRefs.current) as Mode[]).forEach((m) => abortRefs.current[m]?.abort());
  }, []);

  const startMode = useCallback(
    async (mode: Mode, opts: { forceRefresh?: boolean } = {}) => {
      const scenarioId = scenarioIdRef.current;
      if (!scenarioId) return;
      abortRefs.current[mode]?.abort();
      const ac = new AbortController();
      abortRefs.current[mode] = ac;
      setMode(mode, {
        status: "streaming",
        text: "",
        tokens: 0,
        genMs: null,
        error: null,
        citations: [],
        cached: false,
        fellBack: false,
        modelId: null,
      });

      try {
        let n = 0;
        let accumulated = "";
        for await (const msg of streamAnalyst(
          {
            ...configRef.current,
            scenario_id: scenarioId,
            mode,
            rate_tps: 45,
            force_refresh: Boolean(opts.forceRefresh),
          },
          ac.signal,
        )) {
          // Frame shapes come from the API's own models (lib/types.ts); a frame
          // can still arrive malformed over the wire, so every field is re-checked.
          if (msg.event === "start") {
            const f = parseFrame<Partial<StartFrame>>(msg.data);
            if (f?.model_id) setMode(mode, { modelId: f.model_id });
          } else if (msg.event === "token") {
            const f = parseFrame<Partial<TokenFrame>>(msg.data);
            if (typeof f?.text !== "string") continue;
            n += 1;
            accumulated += f.text;
            setMode(mode, { tokens: n, text: accumulated });
          } else if (msg.event === "citations") {
            const f = parseFrame<Partial<CitationsFrame>>(msg.data);
            if (f) {
              setMode(mode, {
                citations: f.citations ?? [],
                cached: Boolean(f.cached),
                fellBack: Boolean(f.fell_back),
                modelId: f.model_id ?? null,
              });
            }
          } else if (msg.event === "done") {
            const f = parseFrame<Partial<DoneFrame>>(msg.data);
            setMode(mode, {
              status: "done",
              genMs: typeof f?.gen_ms === "number" ? f.gen_ms : null,
            });
            return;
          } else if (msg.event === "error") {
            const f = parseFrame<Partial<ErrorFrame>>(msg.data);
            throw new Error(f?.message ?? "Server signalled an error.");
          }
        }
        // Loop ended without done/error: abort is expected, anything else is a
        // truncated stream — surface it rather than feign success.
        if (ac.signal.aborted) {
          setMode(mode, { status: "cancelled" });
          return;
        }
        setMode(mode, { status: "error", error: "Stream ended unexpectedly." });
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          setMode(mode, { status: "cancelled" });
          return;
        }
        setMode(mode, { status: "error", error: (e as Error).message });
      }
    },
    [setMode],
  );

  const startAll = useCallback(() => {
    MODE_KEYS.forEach((m) => void startMode(m));
  }, [startMode]);

  // Guard on id so a re-fetched object with the same id doesn't wipe in-flight reads.
  const lastScenarioId = useRef<string | null>(null);
  useEffect(() => {
    if (scenarioId !== lastScenarioId.current) {
      stopAll();
      lastScenarioId.current = scenarioId;
      setStates(freshStates());
    }
  }, [scenarioId, stopAll]);

  useEffect(() => () => stopAll(), [stopAll]);

  return { states, startMode, stopMode, stopAll, startAll };
}
