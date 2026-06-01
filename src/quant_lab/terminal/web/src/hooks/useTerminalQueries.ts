import { useQuery } from "@tanstack/react-query";
import { fetchDates, fetchSnapshot } from "../api/client";
import type { ChainFlowMode } from "../types/snapshot";

export function useDates(symbol: string) {
  return useQuery({
    queryKey: ["dates", symbol],
    queryFn: () => fetchDates(symbol),
  });
}

export function useSnapshot(
  symbol: string,
  date: string,
  time: string,
  enabled: boolean,
  options?: {
    livePollCandidate?: boolean;
    includeTrinity?: boolean;
    chainFlowMode?: ChainFlowMode;
  },
) {
  const livePollCandidate = options?.livePollCandidate ?? false;
  const includeTrinity = options?.includeTrinity ?? false;
  const chainFlowMode = options?.chainFlowMode ?? "pin";
  return useQuery({
    queryKey: ["snapshot", symbol, date, time, includeTrinity, chainFlowMode],
    queryFn: () => fetchSnapshot(symbol, date, time, includeTrinity, chainFlowMode),
    enabled: enabled && Boolean(date),
    placeholderData: (prev) => prev,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.meta?.live_follow) {
        return (data.meta.live_refresh_seconds ?? 30) * 1000;
      }
      return livePollCandidate && !data ? 30_000 : false;
    },
    refetchIntervalInBackground: false,
  });
}
