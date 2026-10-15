import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { api } from "@/api/client"
import { PriceChart } from "@/components/price-chart"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

const RANGES = [
    { value: "1", label: "1 小时" },
    { value: "6", label: "6 小时" },
    { value: "24", label: "24 小时" },
    { value: "72", label: "3 天" },
    { value: "168", label: "7 天" },
] as const

export function TrendPage() {
    const [targetId, setTargetId] = useState("")
    const [hours, setHours] = useState("24")

    const { data: targets } = useQuery({ queryKey: ["targets"], queryFn: api.listTargets })
    const selected = (targets ?? []).find((t) => t.id === targetId) ?? null

    const { data: ticks, isLoading } = useQuery({
        queryKey: ["trend", targetId, hours],
        queryFn: () => api.priceHistory(targetId, Number(hours)),
        enabled: !!targetId,
        refetchInterval: 30_000,
    })

    const unit = selected?._status?.quote?.unit ?? ""

    useEffect(() => {
        if (!targetId && targets && targets.length > 0) setTargetId(targets[0].id)
    }, [targets, targetId])

    const prices = (ticks ?? []).map((t) => t.price)
    const stats =
        prices.length >= 2
            ? {
                  first: prices[prices.length - 1],
                  last: prices[0],
                  high: Math.max(...prices),
                  low: Math.min(...prices),
                  avg: prices.reduce((a, b) => a + b, 0) / prices.length,
              }
            : null

    return (
        <div className="space-y-4">
            <h1 className="text-xl font-semibold">价格趋势</h1>

            <div className="flex flex-wrap items-end gap-4">
                <div className="min-w-56 space-y-1.5">
                    <Label>监控标的</Label>
                    <Select value={targetId} onValueChange={setTargetId}>
                        <SelectTrigger>
                            <SelectValue placeholder="选择标的" />
                        </SelectTrigger>
                        <SelectContent>
                            {(targets ?? []).map((t) => (
                                <SelectItem key={t.id} value={t.id}>
                                    {t.name}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div className="space-y-1.5">
                    <Label>时间范围</Label>
                    <div className="flex gap-1">
                        {RANGES.map((r) => (
                            <Button
                                key={r.value}
                                size="sm"
                                variant={hours === r.value ? "default" : "outline"}
                                onClick={() => setHours(r.value)}
                            >
                                {r.label}
                            </Button>
                        ))}
                    </div>
                </div>
            </div>

            {stats && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {[
                        { label: "最新", value: stats.last },
                        { label: "最高", value: stats.high },
                        { label: "最低", value: stats.low },
                        { label: "均值", value: stats.avg },
                    ].map((s) => (
                        <Card key={s.label}>
                            <CardContent className="pb-3 pt-3">
                                <div className="text-xs text-muted-foreground">{s.label}</div>
                                <div className="text-lg font-semibold tabular-nums">
                                    {s.value.toFixed(2)}
                                    <span className="ml-1 text-xs font-normal text-muted-foreground">{unit}</span>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                        {selected ? `${selected.name} 近 ${hours} 小时走势` : "走势图"}
                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                            tick 数据 {ticks?.length ?? 0} 条，30s 自动刷新
                        </span>
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    {!targetId ? (
                        <p className="py-20 text-center text-sm text-muted-foreground">请选择监控标的</p>
                    ) : isLoading ? (
                        <Skeleton className="h-64 w-full" />
                    ) : (
                        <PriceChart ticks={ticks ?? []} height={280} unit={unit} />
                    )}
                </CardContent>
            </Card>

            <p className={cn("text-xs text-muted-foreground")}>
                数据来自本地 tick 库（30 秒粒度，默认保留 90 天）；上证指数等按时段门控的标的休市期间不新增数据。
                上金所黄金日K（长线）见仪表盘。
            </p>
        </div>
    )
}
