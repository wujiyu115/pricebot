import { Bell, ChartLine, Cog, ListChecks, Radio, Target } from "lucide-react"
import { NavLink, Outlet } from "react-router-dom"
import { cn } from "@/lib/utils"

const NAV = [
    { to: "/", label: "仪表盘", icon: ChartLine, end: true },
    { to: "/targets", label: "监控标的", icon: Target },
    { to: "/rules", label: "告警规则", icon: ListChecks },
    { to: "/channels", label: "推送渠道", icon: Bell },
    { to: "/settings", label: "设置", icon: Cog },
]

export function AppLayout() {
    return (
        <div className="min-h-screen bg-background">
            <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
                <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
                    <div className="flex items-center gap-2 font-semibold">
                        <Radio className="size-5 text-amber-600" />
                        <span>PriceBot</span>
                        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-800">
                            金价监控
                        </span>
                    </div>
                    <nav className="flex items-center gap-1">
                        {NAV.map((item) => (
                            <NavLink
                                key={item.to}
                                to={item.to}
                                end={item.end}
                                className={({ isActive }) =>
                                    cn(
                                        "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
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
