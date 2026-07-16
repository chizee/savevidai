import { useCallback, useState } from "react";
import { ApiError, resolveTweet, type ResolveResponse } from "../lib/api";

export type ResolveState =
  | { status: "idle" }
  | { status: "resolving" }
  | { status: "ready"; data: ResolveResponse }
  | { status: "error"; code: string; message: string };

export function useResolve() {
  const [state, setState] = useState<ResolveState>({ status: "idle" });

  const resolve = useCallback(async (url: string) => {
    setState({ status: "resolving" });
    try {
      const data = await resolveTweet(url);
      setState({ status: "ready", data });
    } catch (err) {
      if (err instanceof ApiError) {
        setState({ status: "error", code: err.code, message: err.message });
      } else {
        setState({
          status: "error",
          code: "network",
          message: "Network error. Check your connection and try again.",
        });
      }
    }
  }, []);

  const reset = useCallback(() => setState({ status: "idle" }), []);

  return { state, resolve, reset };
}
