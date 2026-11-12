import { Logo } from "@/components/app-shell";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-secondary/40 px-4 py-10">
      <div className="mb-6 flex items-center gap-2">
        <Logo className="h-9 w-9" />
        <span className="text-2xl font-semibold">Twin</span>
      </div>
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}
