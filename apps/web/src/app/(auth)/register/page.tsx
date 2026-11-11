"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/types";

const schema = z.object({
  company_name: z.string().trim().min(2, "Enter your company's legal name"),
  full_name: z.string().trim().min(2, "Enter your name"),
  email: z.email("Enter a valid email"),
  password: z.string().min(10, "Use at least 10 characters"),
});

export default function RegisterPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const me = await api<Me>("/api/v1/auth/register", { method: "POST", json: values });
      qc.setQueryData(["me"], me);
      router.replace("/onboarding");
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "Could not create the account.");
    }
  });

  return (
    <>
      <h1 className="text-xl font-semibold">Create your company</h1>
      <p className="mt-1 text-sm text-muted">You will be the owner. Invite colleagues afterwards.</p>
      <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
        <Field label="Company legal name" htmlFor="company_name" error={formState.errors.company_name?.message}>
          <Input id="company_name" autoComplete="organization" {...register("company_name")} />
        </Field>
        <Field label="Your name" htmlFor="full_name" error={formState.errors.full_name?.message}>
          <Input id="full_name" autoComplete="name" {...register("full_name")} />
        </Field>
        <Field label="Work email" htmlFor="email" error={formState.errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" hint="At least 10 characters." error={formState.errors.password?.message}>
          <Input id="password" type="password" autoComplete="new-password" {...register("password")} />
        </Field>
        {formError ? (
          <p role="alert" className="rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
            {formError}
          </p>
        ) : null}
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Creating…" : "Create company"}
        </Button>
      </form>
      <p className="mt-6 text-xs text-muted">
        Already registered?{" "}
        <Link href="/login" className="font-medium text-accent underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}
