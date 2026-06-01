import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchEquityAnalyze } from "../api/client";

export function useEquityAnalyze(ticker: string, enabled: boolean) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["equity", ticker],
    queryFn: () => fetchEquityAnalyze(ticker),
    enabled: enabled && ticker.length >= 1,
    staleTime: 60_000,
  });

  const refreshBypassCache = useCallback(async () => {
    const data = await fetchEquityAnalyze(ticker, true);
    queryClient.setQueryData(["equity", ticker], data);
    return data;
  }, [queryClient, ticker]);

  return { ...query, refreshBypassCache };
}
