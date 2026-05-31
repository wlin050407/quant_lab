import { useQuery } from "@tanstack/react-query";
import { fetchDates, fetchSnapshot } from "../api/client";

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
  options?: { livePollCandidate?: boolean },
) {
  const livePollCandidate = options?.livePollCandidate ?? false;
  return useQuery({
    queryKey: ["snapshot", symbol, date, time],
    queryFn: () => fetchSnapshot(symbol, date, time),
    enabled: enabled && Boolean(date),
    placeholderData: (prev) => prev,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.meta?.data_source === "thetadata_live") {
        return (data.meta.live_refresh_seconds ?? 60) * 1000;
      }
      return livePollCandidate && !data ? 60_000 : false;
    },
    refetchIntervalInBackground: false,
  });
}
