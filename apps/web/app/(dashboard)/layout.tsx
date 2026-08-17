import { AuthGuard } from "@/components/AuthGuard";
import { DashboardNav } from "@/components/DashboardNav";
import { Footer } from "@/components/editorial/Footer";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex min-h-full flex-1 flex-col">
        <DashboardNav />
        <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col px-6 py-16 sm:px-10 sm:py-24">
          {children}
        </main>
        <Footer />
      </div>
    </AuthGuard>
  );
}
