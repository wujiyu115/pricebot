import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Plus, RefreshCw, SearchCheck, Trash2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/table"
import type { SourceInfo, Target } from "@/types"

function TargetDialog({
    open,
    onOpenChange,
    sources,
    editing,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    sources: SourceInfo[]
    editing: Target | null
}) {
    const queryClient = useQueryClient()
    const [name, setName] = useState("")
    const [source, setSource] = useState("")
    const [symbol, setSymbol] = useState("")
    const [schedule, setSchedule] = useState<"always" | "sge" | "cn_stock" | "cn_futures">("always")
    const [ghUrl, setGhUrl] = useState("")
    const [ghJsonPath, setGhJsonPath] = useState("")
    const [ghRegex, setGhRegex] = useState("")
    const [verifyResult, setVerifyResult] = useState<
        { ok: true; quote: { name: string; last: number; prev_close: number | null; unit: string; time: string } } | { ok: false; error: string } | null
    >(null)

    // 打开时回填
    useEffect(() => {
        if (open) {
            setName(editing?.name ?? "")
            setSource(editing?.source ?? "sina")
            setSymbol(editing?.symbol ?? "")
            setSchedule(editing?.schedule ?? "always")
            const gh = editing?.extra as Record<string, string> | undefined
            setGhUrl(gh?.url ?? "")
            setGhJsonPath(gh?.json_path ?? "")
            setGhRegex(gh?.regex ?? "")
        }
    }, [open, editing])

    const sourceMeta = sources.find((s) => s.name === source)

    const verifyMutation = useMutation({
        mutationFn: async () => {
            const extra: Record<string, string> = {}
            if (source === "generic_http") {
                extra.url = ghUrl
                if (ghJsonPath) extra.json_path = ghJsonPath
                if (ghRegex) extra.regex = ghRegex
            }
            return api.verifySymbol({ source, symbol: symbol.trim(), extra })
        },
        onSuccess: (r) => setVerifyResult({ ok: true, quote: r.quote }),
        onError: (err) => setVerifyResult({ ok: false, error: err.message }),
    })

    const mutation = useMutation({
        mutationFn: async () => {
            const payload: Record<string, unknown> = { name, source, symbol, schedule }
            if (source === "generic_http") {
                const extra: Record<string, string> = { url: ghUrl }
                if (ghJsonPath) extra.json_path = ghJsonPath
                if (ghRegex) extra.regex = ghRegex
                payload.extra = extra
            }
            if (editing) return api.updateTarget(editing.id, payload)
            return api.createTarget(payload)
        },
        onSuccess: () => {
            toast.success(editing ? "标的已更新" : "标的已创建")
            queryClient.invalidateQueries({ queryKey: ["targets"] })
            queryClient.invalidateQueries({ queryKey: ["dashboard"] })
            onOpenChange(false)
        },
        onError: (err) => toast.error(`保存失败: ${err.message}`),
    })

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>{editing ? "编辑标的" : "新增监控标的"}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                    <div className="space-y-1.5">
                        <Label>名称</Label>
                        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如: 上金所黄金9999" />
                    </div>
                    <div className="space-y-1.5">
                        <Label>数据源</Label>
                        <Select value={source} onValueChange={setSource}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {sources.map((s) => (
                                    <SelectItem key={s.name} value={s.name}>
                                        {s.description || s.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                            <Label>代码</Label>
                            <button
                                type="button"
                                className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
                                disabled={!source || !symbol.trim() || verifyMutation.isPending}
                                onClick={() => {
                                    setVerifyResult(null)
                                    verifyMutation.mutate()
                                }}
                            >
                                {verifyMutation.isPending ? (
                                    <Loader2 className="size-3.5 animate-spin" />
                                ) : (
                                    <SearchCheck className="size-3.5" />
                                )}
                                {verifyMutation.isPending ? "查询中…" : "验证代码"}
                            </button>
                        </div>
                        <Input
                            value={symbol}
                            onChange={(e) => {
                                setSymbol(e.target.value)
                                setVerifyResult(null)
                            }}
                            placeholder="如: SGE_AU9999"
                        />
                        {verifyResult && (
                            <div
                                className={`rounded-md px-2.5 py-1.5 text-xs ${
                                    verifyResult.ok ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
                                }`}
                            >
                                {verifyResult.ok ? (
                                    <>
                                        ✓ 可用：{verifyResult.quote.name || symbol}
                                        最新价{" "}
                                        <span className="font-semibold tabular-nums">
                                            {verifyResult.quote.last.toFixed(2)}
                                        </span>
                                        {verifyResult.quote.unit && (
                                            <span className="ml-0.5">{verifyResult.quote.unit}</span>
                                        )}
                                        {verifyResult.quote.prev_close != null && (
                                            <span className="ml-1 opacity-80">
                                                (昨收 {verifyResult.quote.prev_close.toFixed(2)})
                                            </span>
                                        )}
                                    </>
                                ) : (
                                    <>✗ {verifyResult.error}</>
                                )}
                            </div>
                        )}
                        {sourceMeta && Object.keys(sourceMeta.known_symbols).length > 0 && (
                            <div className="flex flex-wrap gap-1.5 pt-1">
                                {Object.entries(sourceMeta.known_symbols).map(([code, label]) => (
                                    <button
                                        key={code}
                                        type="button"
                                        className="rounded bg-muted px-2 py-0.5 text-xs hover:bg-accent"
                                        onClick={() => setSymbol(code)}
                                        title={label}
                                    >
                                        {code}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    {source === "generic_http" && (
                        <div className="space-y-3 rounded-md border p-3">
                            <div className="space-y-1.5">
                                <Label>接口 URL（必填）</Label>
                                <Input
                                    value={ghUrl}
                                    onChange={(e) => setGhUrl(e.target.value)}
                                    placeholder="https://www.mi.com/buy/detail?product_id=10000229"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label>JSONPath（JSON 接口）</Label>
                                <Input
                                    value={ghJsonPath}
                                    onChange={(e) => setGhJsonPath(e.target.value)}
                                    placeholder="data.price（与正则二选一）"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label>正则（HTML/文本，第一个捕获组）</Label>
                                <Input
                                    value={ghRegex}
                                    onChange={(e) => setGhRegex(e.target.value)}
                                    placeholder={'"price":"([0-9.]+)"'}
                                />
                            </div>
                            <p className="text-xs text-muted-foreground">
                                适合服务端渲染价格的商城/API；京东/淘宝商品页价格由 JS
                                加载且需登录，不支持直接抓取，请用带 Cookie 的三方价格接口。
                            </p>
                        </div>
                    )}
                    <div className="space-y-1.5">
                        <Label>轮询时段</Label>
                        <Select
                            value={schedule}
                            onValueChange={(v) =>
                                setSchedule(v as "always" | "sge" | "cn_stock" | "cn_futures")
                            }
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="always">全时段</SelectItem>
                                <SelectItem value="sge">仅上金所交易时段</SelectItem>
                                <SelectItem value="cn_stock">仅A股交易时段</SelectItem>
                                <SelectItem value="cn_futures">仅国内期货交易时段</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        取消
                    </Button>
                    <Button onClick={() => mutation.mutate()} disabled={mutation.isPending || !name || !symbol}>
                        {mutation.isPending ? "保存中…" : "保存"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export function TargetsPage() {
    const queryClient = useQueryClient()
    const { data: targets, isLoading } = useQuery({ queryKey: ["targets"], queryFn: api.listTargets })
    const { data: sources } = useQuery({ queryKey: ["sources"], queryFn: api.listSources })
    const [dialogOpen, setDialogOpen] = useState(false)
    const [editing, setEditing] = useState<Target | null>(null)

    const refreshMutation = useMutation({
        mutationFn: (id: string) => api.refreshTarget(id),
        onSuccess: (r) => {
            if (r.ok) toast.success("刷新成功")
            else toast.error(`刷新失败: ${r.last_error ?? "未知错误"}`)
            queryClient.invalidateQueries({ queryKey: ["targets"] })
        },
        onError: (err) => toast.error(err.message),
    })

    const toggleMutation = useMutation({
        mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api.updateTarget(id, { enabled }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["targets"] })
            queryClient.invalidateQueries({ queryKey: ["dashboard"] })
        },
    })

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.deleteTarget(id),
        onSuccess: () => {
            toast.success("标的及关联规则已删除")
            queryClient.invalidateQueries({ queryKey: ["targets"] })
            queryClient.invalidateQueries({ queryKey: ["rules"] })
            queryClient.invalidateQueries({ queryKey: ["dashboard"] })
        },
        onError: (err) => toast.error(err.message),
    })

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-xl font-semibold">监控标的</h1>
                <Button
                    size="sm"
                    onClick={() => {
                        setEditing(null)
                        setDialogOpen(true)
                    }}
                >
                    <Plus className="size-4" /> 新增标的
                </Button>
            </div>

            <Card>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>名称</TableHead>
                                <TableHead>数据源</TableHead>
                                <TableHead>代码</TableHead>
                                <TableHead className="text-right">最新价</TableHead>
                                <TableHead>状态</TableHead>
                                <TableHead className="text-right">启用</TableHead>
                                <TableHead className="text-right">操作</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {isLoading && (
                                <TableRow>
                                    <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                                        加载中…
                                    </TableCell>
                                </TableRow>
                            )}
                            {targets?.map((t) => (
                                <TableRow key={t.id}>
                                    <TableCell className="font-medium">{t.name}</TableCell>
                                    <TableCell>
                                        <Badge variant="outline">{t.source}</Badge>
                                    </TableCell>
                                    <TableCell className="font-mono text-xs">{t.symbol}</TableCell>
                                    <TableCell className="text-right tabular-nums">
                                        {t._status?.quote?.last != null ? (
                                            <>
                                                {t._status.quote.last.toFixed(2)}
                                                {t._status.quote.prev_close != null && (
                                                    <span className="ml-1 text-xs text-muted-foreground">
                                                        (昨收 {t._status.quote.prev_close.toFixed(2)})
                                                    </span>
                                                )}
                                            </>
                                        ) : (
                                            <span className="text-muted-foreground">—</span>
                                        )}
                                    </TableCell>
                                    <TableCell>
                                        {t._status?.last_error ? (
                                            <span className="text-xs text-red-600" title={t._status.last_error}>
                                                轮询失败
                                            </span>
                                        ) : t._status?.quote ? (
                                            <span className="text-xs text-green-600">正常</span>
                                        ) : (
                                            <span className="text-xs text-muted-foreground">等待数据</span>
                                        )}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <Switch
                                            checked={t.enabled}
                                            onCheckedChange={(v) => toggleMutation.mutate({ id: t.id, enabled: v })}
                                        />
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex justify-end gap-1">
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                title="立即刷新"
                                                onClick={() => refreshMutation.mutate(t.id)}
                                            >
                                                <RefreshCw className="size-4" />
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                title="编辑"
                                                onClick={() => {
                                                    setEditing(t)
                                                    setDialogOpen(true)
                                                }}
                                            >
                                                ✎
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                title="删除"
                                                className="text-red-600 hover:text-red-700"
                                                onClick={() => {
                                                    if (confirm(`删除「${t.name}」及其关联规则？`))
                                                        deleteMutation.mutate(t.id)
                                                }}
                                            >
                                                <Trash2 className="size-4" />
                                            </Button>
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                        </Table>
                    </div>
                </CardContent>
            </Card>

            <TargetDialog
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                sources={sources ?? []}
                editing={editing}
            />
        </div>
    )
}
