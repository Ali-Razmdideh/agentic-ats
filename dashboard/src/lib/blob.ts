// MinIO / S3 wrapper. Same key layout as ats/storage/blob.py.

import {
  GetObjectCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { createHash } from "crypto";

const ENDPOINT = process.env.MINIO_ENDPOINT ?? "http://localhost:9000";
const ACCESS_KEY = process.env.MINIO_ACCESS_KEY ?? "minioadmin";
const SECRET_KEY = process.env.MINIO_SECRET_KEY ?? "minioadmin";
const BUCKET = process.env.MINIO_BUCKET ?? "ats-artifacts";
const REGION = process.env.MINIO_REGION ?? "us-east-1";

export const s3 = new S3Client({
  endpoint: ENDPOINT,
  region: REGION,
  credentials: { accessKeyId: ACCESS_KEY, secretAccessKey: SECRET_KEY },
  forcePathStyle: true, // required for MinIO
});

function sha256(bytes: Uint8Array | Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

/** Strip directory components and any non-portable characters from an
 * uploaded filename before we use it as the leaf of an S3 key. Refusing
 * upstream `..` segments or shell metacharacters means a malicious
 * filename cannot smuggle a path that, when normalised by a downstream
 * tool, escapes the org's prefix.
 */
export function sanitizeFilename(raw: string): string {
  const last = raw.split(/[\\/]/).pop() ?? "";
  const cleaned = last.replace(/[^A-Za-z0-9._-]/g, "_").replace(/^\.+/, "");
  if (!cleaned || cleaned === "." || cleaned === "..") return "file";
  return cleaned.slice(0, 200);
}

export function resumeKey(orgId: number, sha: string, filename: string): string {
  return `orgs/${orgId}/resumes/${sha.slice(0, 2)}/${sha}/${filename}`;
}

export function jdKey(orgId: number, sha: string, filename: string): string {
  return `orgs/${orgId}/jds/${sha}/${filename}`;
}

export async function putResume(
  orgId: number,
  bytes: Buffer,
  filename: string,
  contentType = "application/octet-stream",
): Promise<string> {
  const sha = sha256(bytes);
  const key = resumeKey(orgId, sha, sanitizeFilename(filename));
  await s3.send(
    new PutObjectCommand({
      Bucket: BUCKET,
      Key: key,
      Body: bytes,
      ContentType: contentType,
    }),
  );
  return key;
}

export async function putJd(
  orgId: number,
  bytes: Buffer,
  filename: string,
): Promise<string> {
  const sha = sha256(bytes);
  const key = jdKey(orgId, sha, sanitizeFilename(filename));
  await s3.send(
    new PutObjectCommand({
      Bucket: BUCKET,
      Key: key,
      Body: bytes,
      ContentType: "text/plain; charset=utf-8",
    }),
  );
  return key;
}

export async function presignedGet(
  key: string,
  expiresIn = 300,
): Promise<string> {
  return getSignedUrl(
    s3,
    new GetObjectCommand({ Bucket: BUCKET, Key: key }),
    { expiresIn },
  );
}
