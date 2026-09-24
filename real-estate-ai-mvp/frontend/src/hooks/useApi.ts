import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "./useAuth";
export function useApi<T = any>(path: string, enabled = true) {
  const { workspaceId } = useAuth();
  return useQuery<T>({
    queryKey: [workspaceId, path],
    queryFn: () => api<T>(path),
    enabled: enabled && !!workspaceId,
  });
}
