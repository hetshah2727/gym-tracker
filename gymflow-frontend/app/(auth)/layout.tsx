import Link from "next/link";

const APP = process.env.NEXT_PUBLIC_APP_NAME || "GymFlow";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <Link href="/" className="mb-8 flex items-center gap-2.5 font-display text-lg font-extrabold">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icon.svg" alt="" className="h-9 w-9 rounded-xl" /> {APP}
      </Link>
      <div className="card w-full max-w-md p-6 shadow-soft sm:p-8">{children}</div>
    </div>
  );
}
