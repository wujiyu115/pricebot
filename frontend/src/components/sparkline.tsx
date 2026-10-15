import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import type { Tick } from "@/types"

/** 迷你走势线（最近 1 小时 tick），仪表盘卡片用 */
export function Sparkline({ targetId }: { targetId: string }) {
    const { data } = useQuery({
        queryKey: ["spark", targetId],
        queryFn: () => api.priceHistory(targetId, 1),
        staleTime: 60_000,
        refetchInterval: 120_000,
    })

    const points = [...(data ?? [])].sort((a, b) => a.ts - b.ts)
    if (points.length < 2) return null

    const prices = points.map((p: Tick) => p.price)
    const min = Math.min(...prices)
    const max = Math.max(...prices)
    const span = max - min || 1
    const w = 120
    const h = 28
    const path = points
        .map(
            (p: Tick, i: number) =>
                `${((i / (points.length - 1)) * w).toFixed(1)},${(h - ((p.price - min) / span) * (h - 4) - 2).toFixed(1)}`,
        )
        .join(" ")
    const up = prices[prices.length - 1] >= prices[0]

    return (
        <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} className="ml-auto opacity-80">
            <polyline
                points={path}
                fill="none"
                strokeWidth={1.2}
                vectorEffect="non-scaling-stroke"
                className={up ? "stroke-red-500" : "stroke-green-500"}
            />
        </svg>
    )
}
