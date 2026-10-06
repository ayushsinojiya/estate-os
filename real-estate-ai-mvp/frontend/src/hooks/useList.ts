import { useState } from "react";
import { useApi } from "./useApi";
import type { Page } from "../types";
import { dateBounds } from "../utils/dateFilter";
export function useList(path: string, initialSort = "createdAt,desc") {
  const [search, setSearchValue] = useState("");
  const [status, setStatusValue] = useState("");
  const [sort, setSortValue] = useState(initialSort);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(0);
  const bounds = dateBounds(dateFrom, dateTo);
  const query = useApi<Page>(
    `${path}${path.includes("?") ? "&" : "?"}page=${page}&size=10&search=${encodeURIComponent(search)}&status=${encodeURIComponent(status)}&sort=${sort}&dateFrom=${encodeURIComponent(bounds.dateFrom)}&dateTo=${encodeURIComponent(bounds.dateTo)}`,
  );
  return {
    query,
    search,
    status,
    sort,
    dateFrom,
    dateTo,
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
    onDateFrom: (v: string) => {
      setPage(0);
      setDateFrom(v);
    },
    onDateTo: (v: string) => {
      setPage(0);
      setDateTo(v);
    },
  };
}
