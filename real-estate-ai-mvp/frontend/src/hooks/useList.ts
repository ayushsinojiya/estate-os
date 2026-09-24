import { useState } from "react";
import { useApi } from "./useApi";
import type { Page } from "../types";
export function useList(path: string, initialSort = "createdAt,desc") {
  const [search, setSearchValue] = useState("");
  const [status, setStatusValue] = useState("");
  const [sort, setSortValue] = useState(initialSort);
  const [page, setPage] = useState(0);
  const query = useApi<Page>(
    `${path}${path.includes("?") ? "&" : "?"}page=${page}&size=10&search=${encodeURIComponent(search)}&status=${encodeURIComponent(status)}&sort=${sort}`,
  );
  return {
    query,
    search,
    status,
    sort,
    page,
    setPage,
    onSearch: (v: string) => {
      setPage(0);
      setSearchValue(v);
    },
    onStatus: (v: string) => {
      setPage(0);
      setStatusValue(v);
    },
    onSort: (v: string) => {
      setPage(0);
      setSortValue(v);
    },
  };
}
