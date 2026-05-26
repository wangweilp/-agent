import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-md bg-os-elevated shimmer-bg", className)} />
  );
}

export function CardSkeleton() {
  return (
    <div className="os-card p-4 space-y-3">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-6 w-32" />
      <Skeleton className="h-3 w-full" />
    </div>
  );
}
