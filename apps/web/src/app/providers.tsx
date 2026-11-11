"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, useTheme } from "next-themes";
import { useState } from "react";
import { Toaster } from "sonner";

import { ApiError } from "@/lib/api";

function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  return <Toaster position="bottom-right" theme={resolvedTheme === "dark" ? "dark" : "light"} toastOptions={{ className: "text-sm" }} />;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: false,
            retry: (count, error) =>
              !(error instanceof ApiError && [401, 403, 404, 409, 422].includes(error.status)) && count < 2,
          },
        },
      }),
  );
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={client}>
        {children}
        <ThemedToaster />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
