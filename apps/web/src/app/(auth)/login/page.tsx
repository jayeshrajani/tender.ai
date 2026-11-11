"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/types";

const schema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});

const DEMO_ACCOUNTS = ["owner@narmada.demo", "analyst@narmada.demo", "viewer@narmada.demo", "owner@malwa.demo"];

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const { register, handleSubmit, formState, setValue, setFocus } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const me = await api<Me>("/api/v1/auth/login", { method: "POST", json: values });
      qc.setQueryData(["me"], me);
      router.replace(me.active_company && !me.active_company.onboarding_complete ? "/onboarding" : safeNext(params.get("next")));
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "Could not sign in.");
    }
  });

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-[-0.02em]">Sign in</h1>
      <p className="mt-1.5 text-sm text-muted">Use your company account.</p>
      <form onSubmit={onSubmit} noValidate className="mt-8 space-y-5">
        <Field label="Email" htmlFor="email" error={formState.errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={formState.errors.password?.message}>
          <Input id="password" type="password" autoComplete="current-password" {...register("password")} />
        </Field>
        {formError ? (
          <p role="alert" className="rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
            {formError}
          </p>
        ) : null}
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-6 text-center text-xs text-muted">
        New company?{" "}
        <Link href="/register" className="font-medium text-accent underline-offset-4 hover:underline">
          Create an account
        </Link>
      </p>
      <div className="mt-10 border-t border-line pt-6">
        <p className="section-label">Local DEMO accounts</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {DEMO_ACCOUNTS.map((email) => (
            <button
              key={email}
              type="button"
              onClick={() => {
                setValue("email", email, { shouldValidate: true });
                setFocus("password");
              }}
              className="rounded-full border border-line bg-canvas px-2.5 py-1 text-2xs text-muted transition-colors duration-150 hover:border-accent-line hover:bg-accent-soft hover:text-accent-ink"
            >
              {email}
            </button>
          ))}
        </div>
        <p className="mt-3 text-2xs text-faint">Password is TENDEROS_DEMO_SEED_PASSWORD (see README). Local development only.</p>
      </div>
    </>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
