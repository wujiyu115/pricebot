import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { History, Trash2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { api } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/table"

function fmtTime(ts: number): string {
    return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false })
}

export function AlertsPage() {
    const queryClient = useQueryClient()
    const [limit, setLimit] = useState("100")
    const [targetId, setTargetId] = useState("all")

    const { data: targets } = useQuery({ queryKey: ["targets"], queryFn: api.listTargets })
    const { data: alerts, isLoading } = useQuery({
        queryKey: ["alerts", limit, targetId],
        queryFn: async () => {
            const list = await api.listAlerts(Number(limit))
            return targetId === "all" ? list : list.filter((a) => a.target_id === targetId)
        },
        refetchInterval: 30_000,
    })

    const clearMutation = useMutation({
        mutationFn: api.clearAlerts,
        onSuccess: () => {
            toast.success("告警日志已清空")
            queryClient.invalidateQueries({ queryKey: ["alerts"] })
            queryClient.invalidateQueries({ queryKey: ["dashboard"] })
        },
        onError: (err) => toast.error(err.message),
    })

    const nameById = new Map((targets ?? []).map((t) => [t.id, t.name]))

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h1 className="flex items-center gap-2 text-xl font-semibold">
                    <History className="size-5" />
                    告警历史
                </h1>
                <div className="flex flex-wrap items-end gap-3">
                    <div className="min-w-0 flex-1 space-y-1">
                        <span className="text-xs text-muted-foreground">标的筛选</span>
                        <Select value={targetId} onValueChange={setTargetId}>
                            <SelectTrigger className="w-44">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">全部标的</SelectItem>
                                {(targets ?? []).map((t) => (
                                    <SelectItem key={t.id} value={t.id}>
                                        {t.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1">
                        <span className="text-xs text-muted-foreground">条数</span>
                        <Select value={limit} onValueChange={setLimit}>
                            <SelectTrigger className="w-24">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {["50", "100", "200", "500"].map((n) => (
                                    <SelectItem key={n} value={n}>
                                        {n}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <Button
                        variant="outline"
                        size="sm"
                        className="text-red-600 hover:text-red-700"
                        disabled={!alerts?.length || clearMutation.isPending}
                        onClick={() => {
                            if (confirm(`清空全部 ${alerts?.length ?? 0} 条告警记录？（含所有标的）`))
                                clearMutation.mutate()
                        }}
                    >
                        <Trash2 className="size-4" /> 清空
                    </Button>
                </div>
            </div>

            <Card>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>时间</TableHead>
                                <TableHead>规则</TableHead>
                                <TableHead>标的</TableHead>
                                <TableHead className="text-right">触发价</TableHead>
                                <TableHead>推送结果</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {isLoading && (
                                <TableRow>
                                    <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                                        加载中…
                                    </TableCell>
                                </TableRow>
                            )}
                            {alerts?.length === 0 && (
                                <TableRow>
                                    <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                                        暂无告警记录——等价格触达你的规则，或去「告警规则」页加一条
                                    </TableCell>
                                </TableRow>
                            )}
                            {alerts?.map((a) => {
                                const ok = a.results?.some((r) => r.ok)
                                const failed = a.results?.find((r) => !r.ok)
                                const renderResult = () => {
                                    if (a.results == null || a.results.length === 0)
                                        return (
                                            <Badge variant="outline" className="text-muted-foreground">
                                                无渠道结果
                                            </Badge>
                                        )
                                    if (ok)
                                        return (
                                            <Badge className="bg-green-100 text-green-800 hover:bg-green-100">
                                                已推送 {a.results.length} 渠道
                                            </Badge>
                                        )
                                    return (
                                        <Badge
                                            variant="destructive"
                                            className="max-w-56 truncate"
                                            title={failed?.detail}
                                        >
                                            失败: {failed?.detail ?? "未知"}
                                        </Badge>
                                    )
                                }
                                return (
                                    <TableRow key={a.id} title={a.message}>
                                        <TableCell className="whitespace-nowrap text-muted-foreground">
                                            {fmtTime(a.ts)}
                                        </TableCell>
                                        <TableCell className="font-medium">{a.rule_name}</TableCell>
                                        <TableCell>{(nameById.get(a.target_id) ?? a.target_id) || "—"}</TableCell>
                                        <TableCell className="text-right tabular-nums">
                                            {a.price == null ? "—" : a.price.toFixed(2)}
                                        </TableCell>
                                        <TableCell>{renderResult()}</TableCell>
                                    </TableRow>
                                )
                            })}
                        </TableBody>
                        </Table>
                    </div>
                </CardContent>
            </Card>

            <p className="text-xs text-muted-foreground">
                推送失败常见原因：渠道未启用、Bark 设备 Key 无效、Webhook 地址不可达——见「推送渠道」页，修复后可发测试推送验证。
            </p>
        </div>
    )
}
