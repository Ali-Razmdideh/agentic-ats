import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";

export default async function Index() {
  const user = await getCurrentUser();
  if (user) redirect("/runs");
  redirect("/login");
}
