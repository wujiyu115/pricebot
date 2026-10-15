import { cn } from "@/lib/utils"
import type { Tick } from "@/types"

interface PriceChartProps {
    ticks: Tick[] // 升序或降序均可，内部按 ts 归一
    height?: number
    unit?: string
    className?: string
}

/** 轻量价格折线图（纯 SVG，无图表库依赖） */
export function PriceChart({ ticks, height = 260, unit = "", className }: PriceChartProps) {
    const points = [...ticks].sort((a, b) => a.ts - b.ts)
    if (points.length < 2) {
        return (
            <div className={cn("flex items-center justify-center text-sm text-muted-foreground", className)} style={{ height }}>
                数据不足（至少 2 个 tick）
            </div>
        )
    }

    const prices = points.map((p) => p.price)
    const min = Math.min(...prices)
    const max = Math.max(...prices)
    const span = max - min || 1
    const w = 800
    const h = height
    const padX = 4
    const padY = 14

    const x = (i: number) => padX + (i / (points.length - 1)) * (w - padX * 2)
    const y = (v: number) => padY + (1 - (v - min) / span) * (h - padY * 2)

    const path = points.map((p, i) => `${x(i).toFixed(1)},${y(p.price).toFixed(1)}`).join(" ")
    const first = prices[0]
    const last = prices[prices.length - 1]
    const up = last >= first
    const stroke = up ? "stroke-red-500" : "stroke-green-500"

    const startTime = new Date(points[0].ts * 1000)
    const endTime = new Date(points[points.length - 1].ts * 1000)
    const fmt = (d: Date) =>
        points.length > 300 ? d.toLocaleDateString("zh-CN") : d.toLocaleTimeString("zh-CN", { hour12: false })

    return (
        <div className={cn("space-y-1", className)}>
            <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height }} preserveAspectRatio="none">
                <polyline
                    points={path}
                    fill="none"
                    strokeWidth={1.6}
                    vectorEffect="non-scaling-stroke"
                    className={stroke}
                />
                <line x1={padX} x2={w - padX} y1={y(max)} y2={y(max)} className="stroke-border" strokeWidth={0.5} vectorEffect="non-scaling-stroke" strokeDasharray="4 4" />
                <line x1={padX} x2={w - padX} y1={y(min)} y2={y(min)} className="stroke-border" strokeWidth={0.5} vectorEffect="non-scaling-stroke" strokeDasharray="4 4" />
            </svg>
            <div className="flex justify-between text-xs text-muted-foreground">
                <span>{fmt(startTime)}</span>
                <span>
                    高 {max.toFixed(2)} / 低 {min.toFixed(2)} {unit}
                </span>
                <span>{fmt(endTime)}</span>
            </div>
        </div>
    )
}
