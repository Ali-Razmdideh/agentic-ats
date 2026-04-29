// Mint a short-lived presigned MinIO URL — but only for blob keys that
// belong to the active org. Validation is a string prefix check on the
// known key layout: orgs/{org_id}/...
import { NextResponse } from "next/server";
import { requireUserAndOrg } from "@/lib/auth";
import { presignedGet } from "@/lib/blob";

export async function GET(req: Request) {
  const { org } = await requireUserAndOrg();
  const url = new URL(req.url);
  const key = url.searchParams.get("key");
  if (!key) {
    return NextResponse.json({ error: "missing_key" }, { status: 400 });
  }
  const expectedPrefix = `orgs/${org.id}/`;
  if (!key.startsWith(expectedPrefix)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const signed = await presignedGet(key, 300);
  return NextResponse.json({ url: signed });
}
