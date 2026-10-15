import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CircleAlert, CircleCheck, RefreshCw } from "lucide-react"
import { api } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { Quote } from "@/types"

function fmtTime(ts: number | null | undefined): string {
    if (!ts) return "-"
    return new Date(ts * 1000).toLocaleTimeString("zh-CN", { hour12: false })
}

function QuoteCard({
    name,
    symbol,
    quote,
}: {
    name: string
    symbol: string
    quote: Quote | null
}) {
    const last = quote?.last ?? null
    const pct =
        quote?.prev_close && quote.last ? ((quote.last - quote.prev_close) / quote.prev_close) * 100 : null
    return (
        <Card>
            <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-base">
                    <span>{name}</span>
                    <Badge variant="outline" className="font-mono text-xs text-muted-foreground">
                        {symbol}
                    </Badge>
                </CardTitle>
            </CardHeader>
            <CardContent>
                {last == null ? (
                    <Skeleton className="h-10 w-32" />
                ) : (
                    <div>
                        <div className="flex items-baseline gap-2">
                            <span className="text-3xl font-semibold tabular-nums">{last.toFixed(2)}</span>
                            <span className="text-sm text-muted-foreground">{quote?.unit ?? "元/克"}</span>
                            {pct != null && (
                                <span
                                    className={cn(
                                        "ml-auto text-sm font-medium tabular-nums",
                                        pct >= 0 ? "text-red-600" : "text-green-600",
                                    )}
                                >
                                    {pct >= 0 ? "▲" : "▼"} {pct.toFixed(2)}%
                                </span>
                            )}
                        </div>
                        <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
                            {quote?.bid != null && <span>买一 {quote.bid.toFixed(2)}</span>}
                            {quote?.ask != null && <span>卖一 {quote.ask.toFixed(2)}</span>}
                            {quote?.prev_close != null && <span>昨收 {quote.prev_close.toFixed(2)}</span>}
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

function DailyChart({ rows }: { rows: Array<[string, number, number, number, number]> }) {
    if (rows.length < 2) return <Skeleton className="h-44 w-full" />
    const prices = rows.flatMap((r) => [r[2], r[3], r[4]]).filter((p) => p > 0)
    const min = Math.min(...prices)
    const max = Math.max(...prices)
    const span = max - min || 1
    const w = 600
    const h = 120
    const pts = rows.map((r, i) => {
        const x = (i / (rows.length - 1)) * w
        const y = h - ((r[2] - min) / span) * h
        return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    const lastClose = rows[rows.length - 1][2]
    const firstClose = rows[0][2]
    const up = lastClose >= firstClose
    return (
        <div className="space-y-2">
            <svg viewBox={`0 0 ${w} ${h}`} className="h-32 w-full" preserveAspectRatio="none">
                <polyline
                    points={pts.join(" ")}
                    fill="none"
                    strokeWidth={2}
                    className={up ? "stroke-red-500" : "stroke-green-500"}
                />
            </svg>
            <div className="flex justify-between text-xs text-muted-foreground">
                <span>{rows[0][0]}</span>
                <span>
                    区间 {min.toFixed(2)} ~ {max.toFixed(2)}
                </span>
                <span>{rows[rows.length - 1][0]}</span>
            </div>
        </div>
    )
}

export function DashboardPage() {
    const { data: dash, isLoading, refetch, isFetching } = useQuery({
        queryKey: ["dashboard"],
        queryFn: api.dashboard,
        refetchInterval: 10_000,
    })
    const { data: daily } = useQuery({
        queryKey: ["daily", "Au99.99"],
        queryFn: () => api.dailyKline("Au99.99", 90),
        staleTime: 3600_000,
    })

    if (isLoading || !dash) {
        return (
            <div className="grid gap-4 md:grid-cols-2">
                <Skeleton className="h-40" />
                <Skeleton className="h-40" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                        {dash.engine.running ? (
                            <>
                                <CircleCheck className="size-4 text-green-600" /> 监控运行中
                            </>
                        ) : (
                            <>
                                <CircleAlert className="size-4 text-red-600" /> 引擎未运行
                            </>
                        )}
                    </span>
                    <span>轮询 {dash.engine.interval_seconds}s</span>
                    <span>
                        标的 {dash.counts.targets_enabled}/{dash.counts.targets} · 规则{" "}
                        {dash.counts.rules_enabled}/{dash.counts.rules}
                    </span>
                </div>
                <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                    <RefreshCw className={cn("size-4", isFetching && "animate-spin")} />
                    刷新
                </Button>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
                {dash.quotes.map((q) => (
                    <QuoteCard key={q.target_id} name={q.name} symbol={q.symbol} quote={q.quote} />
                ))}
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base">Au99.99 日线走势（近 90 交易日，上金所官网）</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <DailyChart rows={daily ?? []} />
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base">最近告警</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        {dash.recent_alerts.length === 0 ? (
                            <p className="py-8 text-center text-sm text-muted-foreground">暂无告警记录</p>
                        ) : (
                            dash.recent_alerts.slice(0, 6).map((a) => (
                                <div key={a.id} className="flex items-start gap-2 rounded-md border p-2 text-sm">
                                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="font-medium">{a.rule_name}</span>
                                            {a.price != null && (
                                                <span className="tabular-nums text-muted-foreground">
                                                    @{a.price.toFixed(2)}
                                                </span>
                                            )}
                                        </div>
                                        <p className="truncate text-xs text-muted-foreground">
                                            {fmtTime(a.ts)} ·{" "}
                                            {a.results.some((r) => r.ok)
                                                ? "已推送"
                                                : "推送失败: " + (a.results[0]?.detail ?? "无渠道")}
                                        </p>
                                    </div>
                                </div>
                            ))
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
