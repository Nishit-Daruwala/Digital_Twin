import { AuthForm } from "@/components/auth-form";

export const metadata = { title: "Create account · Twin" };

export default function RegisterPage() {
  return <AuthForm mode="register" />;
}
