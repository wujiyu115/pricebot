import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Rule, RuleType } from "@/types"

function RuleDialog({
    open,
    onOpenChange,
    targets,
    ruleTypes,
    channels,
    editing,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    targets: Array<{ id: string; name: string }>
    ruleTypes: Array<{ value: RuleType; label: string; hint: string }>
    channels: Array<{ name: string; display_name: string }>
    editing: Rule | null
}) {
    const queryClient = useQueryClient()
    const [targetId, setTargetId] = useState("")
    const [name, setName] = useState("")
    const [type, setType] = useState<RuleType>("cross_above")
    const [threshold, setThreshold] = useState("")
    const [windowMinutes, setWindowMinutes] = useState("30")
    const [confirmCount, setConfirmCount] = useState("1")
    const [cooldown, setCooldown] = useState("60")
    const [selectedChannels, setSelectedChannels] = useState<string[]>([])

    useEffect(() => {
        if (open && targets.length > 0) {
            setTargetId(editing?.target_id ?? targets[0].id)
            setName(editing?.name ?? "")
            setType(editing?.type ?? "cross_above")
            setThreshold(editing ? String(editing.threshold) : "")
            setWindowMinutes(String(editing?.window_minutes ?? 30))
            setConfirmCount(String(editing?.confirm_count ?? 1))
            setCooldown(String(editing?.cooldown_minutes ?? 60))
            setSelectedChannels(editing?.channels ?? [])
        }
    }, [open, editing, targets])

    const typeMeta = ruleTypes.find((t) => t.value === type)
    const isWindowRule = type.startsWith("pct_") || type.startsWith("price_")

    const mutation = useMutation({
        mutationFn: async () => {
            const payload = {
                target_id: targetId,
                name,
                type,
                threshold: Number(threshold),
                window_minutes: Number(windowMinutes),
                confirm_count: Number(confirmCount),
                cooldown_minutes: Number(cooldown),
                channels: selectedChannels,
            }
            if (editing) return api.updateRule(editing.id, payload)
            return api.createRule(payload)
        },
        onSuccess: () => {
            toast.success(editing ? "规则已更新" : "规则已创建")
            queryClient.invalidateQueries({ queryKey: ["rules"] })
            queryClient.invalidateQueries({ queryKey: ["dashboard"] })
            onOpenChange(false)
        },
        onError: (err) => toast.error(`保存失败: ${err.message}`),
    })

    const toggleChannel = (ch: string) => {
        setSelectedChannels((prev) => (prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]))
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle>{editing ? "编辑规则" : "新增告警规则"}</DialogTitle>
                </DialogHeader>
                <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                        <Label>监控标的</Label>
                        <Select value={targetId} onValueChange={setTargetId}>
                            <SelectTrigger>
                                <SelectValue placeholder="选择标的" />
                            </SelectTrigger>
                            <SelectContent>
                                {targets.map((t) => (
                                    <SelectItem key={t.id} value={t.id}>
                                        {t.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1.5">
                        <Label>规则名称</Label>
                        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如: 金价上穿900" />
                    </div>
                    <div className="space-y-1.5">
                        <Label>规则类型</Label>
                        <Select value={type} onValueChange={(v) => setType(v as RuleType)}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {ruleTypes.map((t) => (
                                    <SelectItem key={t.value} value={t.value}>
                                        {t.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {typeMeta && <p className="text-xs text-muted-foreground">{typeMeta.hint}</p>}
                    </div>
                    <div className="space-y-1.5">
                        <Label>{type.startsWith("pct_") ? "阈值 (%)" : "阈值 (元/克)"}</Label>
                        <Input
                            type="number"
                            step="0.01"
                            value={threshold}
                            onChange={(e) => setThreshold(e.target.value)}
                        />
                    </div>
                    {isWindowRule && (
                        <div className="space-y-1.5">
                            <Label>窗口 (分钟)</Label>
                            <Input
                                type="number"
                                value={windowMinutes}
                                onChange={(e) => setWindowMinutes(e.target.value)}
                            />
                        </div>
                    )}
                    <div className="space-y-1.5">
                        <Label>连续确认次数</Label>
                        <Input
                            type="number"
                            min={1}
                            value={confirmCount}
                            onChange={(e) => setConfirmCount(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">防抖：连续 N 次轮询成立才触发</p>
                    </div>
                    <div className="space-y-1.5">
                        <Label>冷却 (分钟)</Label>
                        <Input type="number" min={0} value={cooldown} onChange={(e) => setCooldown(e.target.value)} />
                        <p className="text-xs text-muted-foreground">0 = 不冷却</p>
                    </div>
                    <div className="space-y-1.5 sm:col-span-2">
                        <Label>推送渠道</Label>
                        <div className="flex flex-wrap gap-3">
                            {channels.map((c) => (
                                <label key={c.name} className="flex items-center gap-1.5 text-sm">
                                    <input
                                        type="checkbox"
                                        checked={selectedChannels.includes(c.name)}
                                        onChange={() => toggleChannel(c.name)}
                                    />
                                    {c.display_name}
                                </label>
                            ))}
                        </div>
                        <p className="text-xs text-muted-foreground">不选 = 推送到所有已启用渠道</p>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        取消
                    </Button>
                    <Button
                        onClick={() => mutation.mutate()}
                        disabled={mutation.isPending || !name || !threshold}
                    >
                        {mutation.isPending ? "保存中…" : "保存"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export function RulesPage() {
    const queryClient = useQueryClient()
    const { data: rules } = useQuery({ queryKey: ["rules"], queryFn: api.listRules })
    const { data: targets } = useQuery({ queryKey: ["targets"], queryFn: api.listTargets })
    const { data: meta } = useQuery({ queryKey: ["rulesMeta"], queryFn: api.rulesMeta })
    const [dialogOpen, setDialogOpen] = useState(false)
    const [editing, setEditing] = useState<Rule | null>(null)

    const toggleMutation = useMutation({
        mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api.updateRule(id, { enabled }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["rules"] })
            queryClient.invalidateQueries({ queryKey: ["dashboard"] })
        },
    })

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.deleteRule(id),
        onSuccess: () => {
            toast.success("规则已删除")
            queryClient.invalidateQueries({ queryKey: ["rules"] })
            queryClient.invalidateQueries({ queryKey: ["dashboard"] })
        },
        onError: (err) => toast.error(err.message),
    })

    const typeLabel = (t: string) => meta?.rule_types.find((r) => r.value === t)?.label ?? t

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-xl font-semibold">告警规则</h1>
                <Button
                    size="sm"
                    onClick={() => {
                        setEditing(null)
                        setDialogOpen(true)
                    }}
                >
                    <Plus className="size-4" /> 新增规则
                </Button>
            </div>

            <Card>
                <CardContent className="p-0">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>规则</TableHead>
                                <TableHead>标的</TableHead>
                                <TableHead>类型</TableHead>
                                <TableHead>阈值</TableHead>
                                <TableHead>防抖/冷却</TableHead>
                                <TableHead>渠道</TableHead>
                                <TableHead className="text-right">启用</TableHead>
                                <TableHead className="text-right">操作</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {rules?.length === 0 && (
                                <TableRow>
                                    <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                                        暂无规则，点击右上角新增
                                    </TableCell>
                                </TableRow>
                            )}
                            {rules?.map((r) => (
                                <TableRow key={r.id}>
                                    <TableCell className="font-medium">{r.name}</TableCell>
                                    <TableCell>{r.target_name}</TableCell>
                                    <TableCell>
                                        <Badge variant="secondary">{typeLabel(r.type)}</Badge>
                                    </TableCell>
                                    <TableCell className="tabular-nums">
                                        {r.type.startsWith("pct_") ? `${r.threshold}%` : r.threshold}
                                        {(r.type.startsWith("pct_") || r.type.startsWith("price_")) && (
                                            <span className="text-xs text-muted-foreground"> / {r.window_minutes}min</span>
                                        )}
                                    </TableCell>
                                    <TableCell className="text-xs text-muted-foreground">
                                        确认 {r.confirm_count} 次 / 冷却 {r.cooldown_minutes} 分
                                    </TableCell>
                                    <TableCell>
                                        {r.channels.length === 0 ? (
                                            <span className="text-xs text-muted-foreground">全部启用渠道</span>
                                        ) : (
                                            <div className="flex flex-wrap gap-1">
                                                {r.channels.map((c) => (
                                                    <Badge key={c} variant="outline">
                                                        {c}
                                                    </Badge>
                                                ))}
                                            </div>
                                        )}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <Switch
                                            checked={r.enabled}
                                            onCheckedChange={(v) => toggleMutation.mutate({ id: r.id, enabled: v })}
                                        />
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex justify-end gap-1">
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                title="编辑"
                                                onClick={() => {
                                                    setEditing(r)
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
                                                    if (confirm(`删除规则「${r.name}」？`)) deleteMutation.mutate(r.id)
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
                </CardContent>
            </Card>

            <RuleDialog
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                targets={(targets ?? []).map((t) => ({ id: t.id, name: t.name }))}
                ruleTypes={meta?.rule_types ?? []}
                channels={meta?.channels ?? []}
                editing={editing}
            />
        </div>
    )
}
