import { Dumbbell } from "lucide-react";
import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <Link href="/" className="mb-8 flex items-center gap-2 font-semibold">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand text-brand-fg">
          <Dumbbell className="h-4 w-4" />
        </span>
        GymFlow AI
      </Link>
      <div className="card w-full max-w-md p-6 sm:p-8">{children}</div>
    </div>
  );
}
