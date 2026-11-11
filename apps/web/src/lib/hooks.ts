"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import type { Me, Profile, Reference } from "@/lib/types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/v1/auth/me"), staleTime: 60_000 });
}

export function useReference() {
  return useQuery({
    queryKey: ["reference"],
    queryFn: () => api<Reference>("/api/v1/company/reference"),
    staleTime: Infinity,
  });
}

export function useProfile() {
  return useQuery({ queryKey: ["profile"], queryFn: () => api<Profile>("/api/v1/company/profile") });
}

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Profile>("/api/v1/company/profile", { method: "PUT", json: body }),
    onSuccess: (data) => {
      qc.setQueryData(["profile"], data);
      void qc.invalidateQueries({ queryKey: ["me"] });
      void qc.invalidateQueries({ queryKey: ["tenders"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["tender"] });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: () => api<void>("/api/v1/auth/logout", { method: "POST" }),
    onSettled: () => {
      qc.clear();
      router.replace("/login");
    },
  });
}

export function canEdit(role: string | undefined, minimum: "analyst" | "admin" | "owner"): boolean {
  const rank: Record<string, number> = { viewer: 1, analyst: 2, admin: 3, owner: 4 };
  return (rank[role ?? "viewer"] ?? 0) >= rank[minimum]!;
}
