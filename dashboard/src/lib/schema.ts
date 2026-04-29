import { z } from "zod";

export const SignupInput = z.object({
  email: z.string().email().max(254),
  password: z.string().min(8).max(256),
  display_name: z.string().max(120).optional().nullable(),
});

export const LoginInput = z.object({
  email: z.string().email().max(254),
  password: z.string().min(1).max(256),
});

export const SwitchOrgInput = z.object({
  slug: z.string().min(1).max(64),
});

export const DecisionInput = z.object({
  run_id: z.coerce.number().int().positive(),
  candidate_id: z.coerce.number().int().positive(),
  decision: z.enum(["shortlist", "reject", "hold"]),
  notes: z.string().max(2000).optional().nullable(),
});

export const CommentInput = z.object({
  run_id: z.coerce.number().int().positive(),
  candidate_id: z.coerce.number().int().positive(),
  body: z.string().min(1).max(4000),
});

export const RunUploadInput = z.object({
  top_n: z.coerce.number().int().min(1).max(50).default(5),
  skip_optional: z
    .union([z.boolean(), z.string()])
    .transform((v) => v === true || v === "true" || v === "on")
    .default(false),
});
