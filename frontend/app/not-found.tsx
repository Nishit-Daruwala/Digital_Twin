import Link from "next/link";
import { Wordmark } from "@/components/app-shell";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col px-5 py-8 sm:px-8">
      <Wordmark />
      <div className="flex flex-1 flex-col items-start justify-center gap-4 sm:mx-auto sm:w-full sm:max-w-md">
        <p className="eyebrow text-primary">Error 404</p>
        <h1 className="text-[32px] font-semibold leading-tight">Page not found</h1>
        <p className="text-muted-foreground">Even your twin doesn&apos;t know this one.</p>
        <Button asChild className="mt-2">
          <Link href="/">Go home</Link>
        </Button>
      </div>
    </div>
  );
}
