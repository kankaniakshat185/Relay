import { AuthGuard } from "@/components/AuthGuard";
import { DashboardNav } from "@/components/DashboardNav";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex min-h-full flex-1 flex-col">
        <DashboardNav />
        <main className="flex flex-1 flex-col px-6 py-8">{children}</main>
      </div>
    </AuthGuard>
  );
}
