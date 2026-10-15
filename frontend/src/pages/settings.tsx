import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { SettingsBundle } from "@/types"

function MonitorSettings({ bundle }: { bundle: SettingsBundle }) {
    const queryClient = useQueryClient()
    const [interval, setIntervalValue] = useState("")
    const [timeout, setTimeoutValue] = useState("")
    const [retention, setRetention] = useState("")
    const [version, setVersion] = useState("")

    useEffect(() => {
        const m = bundle.user_settings.monitor ?? {}
        const defaults = bundle.default_settings.monitor as { interval_seconds?: number } | undefined
        setIntervalValue(String(m.interval_seconds ?? defaults?.interval_seconds ?? 30))
        setTimeoutValue(String(m.source_timeout_seconds ?? 10))
        setRetention(String(m.history_retention_days ?? 90))
        setVersion(bundle.version)
    }, [bundle])

    const saveMutation = useMutation({
        mutationFn: () =>
            api.updateSettings(
                {
                    monitor: {
                        interval_seconds: Number(interval),
                        source_timeout_seconds: Number(timeout),
                        history_retention_days: Number(retention),
                    },
                },
                version,
            ),
        onSuccess: () => {
            toast.success("设置已保存")
            queryClient.invalidateQueries({ queryKey: ["settings"] })
        },
        onError: (err) => toast.error(`保存失败: ${err.message}`),
    })

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="text-base">监控引擎</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-1.5">
                    <Label>轮询间隔（秒）</Label>
                    <Input type="number" min={5} value={interval} onChange={(e) => setIntervalValue(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                    <Label>数据源超时（秒）</Label>
                    <Input type="number" value={timeout} onChange={(e) => setTimeoutValue(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                    <Label>历史保留（天）</Label>
                    <Input type="number" value={retention} onChange={(e) => setRetention(e.target.value)} />
                </div>
                <div className="sm:col-span-3 flex justify-end">
                    <Button size="sm" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
                        {saveMutation.isPending ? "保存中…" : "保存"}
                    </Button>
                </div>
            </CardContent>
        </Card>
    )
}

export function SettingsPage() {
    const { data: bundle } = useQuery({ queryKey: ["settings"], queryFn: api.getSettings })
    const [expanded, setExpanded] = useState(false)

    const channelCount = Object.keys((bundle?.user_overrides as Record<string, unknown>)?.notify ?? {}).length

    return (
        <div className="space-y-4">
            <div>
                <h1 className="text-xl font-semibold">设置</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    配置两层（默认层 + 用户覆盖层），此处编辑只写用户层。推送渠道参数在「推送渠道」页维护。
                </p>
            </div>

            {bundle && <MonitorSettings bundle={bundle} />}

            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center justify-between text-base">
                        <span>用户覆盖层（user_settings.json，稀疏）</span>
                        <span className="text-xs font-normal text-muted-foreground">
                            {channelCount > 0 ? `notify 已有 ${channelCount} 个渠道配置` : "尚无覆盖"}
                        </span>
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" onClick={() => setExpanded(!expanded)}>
                            {expanded ? "收起" : "展开 JSON"}
                        </Button>
                    </div>
                    {expanded && (
                        <pre className="mt-3 max-h-96 overflow-auto rounded bg-muted p-3 text-xs">
                            {JSON.stringify(bundle?.user_overrides ?? {}, null, 2)}
                        </pre>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
