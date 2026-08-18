import { cn } from "@/lib/utils";

type TrustItem = {
  label: string;
  value: string;
  dot: string;
};

const TRUST_ITEMS: TrustItem[] = [
  { label: "运行时", value: "就绪", dot: "bg-os-success" },
  { label: "内核", value: "分离", dot: "bg-os-accent" },
  { label: "执行", value: "Rootless", dot: "bg-os-data-cyan" },
  { label: "记忆", value: "三层", dot: "bg-os-memory-violet" },
  { label: "链路", value: "全链路", dot: "bg-os-success" },
];

export function SystemTrustRail({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "border-y border-slate-900/[0.075] bg-white/55 backdrop-blur-sm",
        className,
      )}
      role="list"
      aria-label="系统可信度"
    >
      <div className="grid grid-cols-2 gap-px sm:grid-cols-5">
        {TRUST_ITEMS.map((item, index) => (
          <div
            key={item.label}
            role="listitem"
            className={cn(
              "min-w-0 px-3 py-3 sm:px-4",
              index > 0 && "sm:border-l sm:border-slate-900/[0.055]",
              index === TRUST_ITEMS.length - 1 && "col-span-2 sm:col-span-1",
            )}
          >
            <p className="truncate text-[11px] font-medium uppercase leading-4 tracking-[0.08em] text-os-subtle">
              {item.label}
            </p>
            <p className="mt-1 flex min-w-0 items-center gap-2 text-[13px] font-semibold leading-5 text-os-text-high sm:text-sm">
              <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", item.dot)} />
              <span className="truncate">{item.value}</span>
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
