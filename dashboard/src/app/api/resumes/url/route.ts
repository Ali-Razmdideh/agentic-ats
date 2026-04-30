// Mint a short-lived presigned MinIO URL — but only for blob keys that
// belong to the active org.
//
// Validation is two-stage:
//   1. Reject any key that contains a path-traversal segment, double slash,
//      backslash, or control character. MinIO/S3 normalises `..` segments
//      server-side, so a naive `startsWith("orgs/2/")` check would let
//      `orgs/2/../1/...` resolve into another org's namespace.
//   2. After the key is normalised, re-check the prefix.
import { NextResponse } from "next/server";
import { requireUserAndOrg } from "@/lib/auth";
import { presignedGet } from "@/lib/blob";

const SAFE_KEY = /^[A-Za-z0-9._/+-]+$/;

function isSafeKey(key: string): boolean {
  if (!SAFE_KEY.test(key)) return false;
  // Reject path-traversal segments and pathological prefixes.
  if (key.includes("//") || key.includes("..") || key.startsWith("/")) {
    return false;
  }
  return true;
}

export async function GET(req: Request) {
  const { org } = await requireUserAndOrg();
  const url = new URL(req.url);
  const key = url.searchParams.get("key");
  if (!key) {
    return NextResponse.json({ error: "missing_key" }, { status: 400 });
  }
  if (!isSafeKey(key)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const expectedPrefix = `orgs/${org.id}/`;
  if (!key.startsWith(expectedPrefix)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const signed = await presignedGet(key, 300);
  return NextResponse.json({ url: signed });
}
