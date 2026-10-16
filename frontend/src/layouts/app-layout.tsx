import { Bell, ChartLine, Cog, History, ListChecks, Radio, Target, TrendingUp } from "lucide-react"
import { NavLink, Outlet } from "react-router-dom"
import { cn } from "@/lib/utils"

const NAV = [
    { to: "/", label: "仪表盘", icon: ChartLine, end: true },
    { to: "/targets", label: "监控标的", icon: Target },
    { to: "/trend", label: "价格趋势", icon: TrendingUp },
    { to: "/rules", label: "告警规则", icon: ListChecks },
    { to: "/channels", label: "推送渠道", icon: Bell },
    { to: "/alerts", label: "告警历史", icon: History },
    { to: "/settings", label: "设置", icon: Cog },
]

export function AppLayout() {
    return (
        <div className="min-h-screen bg-background">
            <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
                <div className="mx-auto flex max-w-6xl flex-col px-4 py-2 sm:h-14 sm:flex-row sm:items-center sm:gap-6 sm:py-0">
                    <div className="flex items-center gap-2 font-semibold">
                        <Radio className="size-5 shrink-0 text-amber-600" />
                        <span className="whitespace-nowrap">PriceBot</span>
                        <span className="whitespace-nowrap rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-800">
                            金价监控
                        </span>
                    </div>
                    <nav className="-mx-1 mt-2 flex items-center gap-1 overflow-x-auto pb-0.5 sm:mt-0 sm:overflow-visible">
                        {NAV.map((item) => (
                            <NavLink
                                key={item.to}
                                to={item.to}
                                end={item.end}
                                className={({ isActive }) =>
                                    cn(
                                        "flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
                                        isActive
                                            ? "bg-accent font-medium text-accent-foreground"
                                            : "text-muted-foreground hover:bg-accent/60",
                                    )
                                }
                            >
                                <item.icon className="size-4" />
                                {item.label}
                            </NavLink>
                        ))}
                    </nav>
                </div>
            </header>
            <main className="mx-auto max-w-6xl px-4 py-6">
                <Outlet />
            </main>
        </div>
    )
}
