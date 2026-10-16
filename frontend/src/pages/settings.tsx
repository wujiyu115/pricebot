import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/api/client"
import { cn } from "@/lib/utils"
import { Switch } from "@/components/switch"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { ChannelMeta, SettingsBundle } from "@/types"

type SourceErrorNotify = {
    enabled: boolean
    min_failures: number
    repeat_minutes: number
    channels: string[]
}

type BriefingNotify = {
    enabled: boolean
    interval_days: number
    channels: string[]
}

const SE_DEFAULTS: SourceErrorNotify = { enabled: false, min_failures: 3, repeat_minutes: 30, channels: [] }
const BN_DEFAULTS: BriefingNotify = { enabled: false, interval_days: 1, channels: [] }

function ChannelChips({
    channels,
    selected,
    onToggle,
}: {
    channels: ChannelMeta[]
    selected: string[]
    onToggle: (name: string) => void
}) {
    return (
        <div className="space-y-2 sm:col-span-2">
            <Label>推送渠道（不选 = 所有启用渠道）</Label>
            <div className="flex flex-wrap gap-1.5">
                {channels.map((c) => {
                    const on = selected.includes(c.name)
                    return (
                        <button
                            key={c.name}
                            type="button"
                            className={cn(
                                "rounded-full border px-2.5 py-1 text-xs transition-colors",
                                on
                                    ? "border-amber-400 bg-amber-100 text-amber-900"
                                    : "text-muted-foreground hover:bg-accent",
                            )}
                            onClick={() => onToggle(c.name)}
                            title={c.config?.enabled ? "已启用" : "注意：该渠道未启用"}
                        >
                            {c.display_name || c.name}
                            {!c.config?.enabled && <span className="ml-1 opacity-60">（未启用）</span>}
                        </button>
                    )
                })}
            </div>
            {selected.length === 0 && (
                <p className="text-xs text-muted-foreground">未选择时，推送到所有已启用的渠道</p>
            )}
        </div>
    )
}

function MonitorSettings({ bundle }: { bundle: SettingsBundle }) {
    const queryClient = useQueryClient()
    const [interval, setIntervalValue] = useState("")
    const [timeout, setTimeoutValue] = useState("")
    const [retention, setRetention] = useState("")
    const [version, setVersion] = useState("")
    const [seEnabled, setSeEnabled] = useState(false)
    const [seMinFailures, setSeMinFailures] = useState("")
    const [seRepeat, setSeRepeat] = useState("")
    const [seChannels, setSeChannels] = useState<string[]>([])
    const [bnEnabled, setBnEnabled] = useState(false)
    const [bnDays, setBnDays] = useState("")
    const [bnChannels, setBnChannels] = useState<string[]>([])

    const { data: channels } = useQuery({ queryKey: ["channels"], queryFn: api.listChannels })

    useEffect(() => {
        const m = bundle.user_settings.monitor ?? {}
        const defaults = bundle.default_settings.monitor as
            | {
                  interval_seconds?: number
                  source_error_notify?: Partial<SourceErrorNotify>
                  briefing_notify?: Partial<BriefingNotify>
              }
            | undefined
        setIntervalValue(String(m.interval_seconds ?? defaults?.interval_seconds ?? 30))
        setTimeoutValue(String(m.source_timeout_seconds ?? 10))
        setRetention(String(m.history_retention_days ?? 90))
        const se = {
            ...SE_DEFAULTS,
            ...(defaults?.source_error_notify ?? {}),
            ...((m as { source_error_notify?: Partial<SourceErrorNotify> }).source_error_notify ?? {}),
        }
        setSeEnabled(Boolean(se.enabled))
        setSeMinFailures(String(se.min_failures))
        setSeRepeat(String(se.repeat_minutes))
        setSeChannels(se.channels ?? [])
        const bn = {
            ...BN_DEFAULTS,
            ...(defaults?.briefing_notify ?? {}),
            ...((m as { briefing_notify?: Partial<BriefingNotify> }).briefing_notify ?? {}),
        }
        setBnEnabled(Boolean(bn.enabled))
        setBnDays(String(bn.interval_days))
        setBnChannels(bn.channels ?? [])
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
                        source_error_notify: {
                            enabled: seEnabled,
                            min_failures: Math.max(1, Number(seMinFailures) || 3),
                            repeat_minutes: Math.max(0, Number(seRepeat) || 0),
                            channels: seChannels,
                        },
                        briefing_notify: {
                            enabled: bnEnabled,
                            interval_days: Math.max(0, Number(bnDays) || 0),
                            channels: bnChannels,
                        },
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
                <div className="sm:col-span-3">
                    <div className="rounded-md border p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <Label>源失效推送</Label>
                                <p className="mt-1 text-xs text-muted-foreground">
                                    数据源连续获取失败时推送告警（与价格规则推送相互独立）
                                </p>
                            </div>
                            <Switch checked={seEnabled} onCheckedChange={setSeEnabled} />
                        </div>
                        {seEnabled && (
                            <div className="mt-4 grid gap-4 sm:grid-cols-2">
                                <div className="space-y-1.5">
                                    <Label>连续失败次数阈值</Label>
                                    <Input
                                        type="number"
                                        min={1}
                                        value={seMinFailures}
                                        onChange={(e) => setSeMinFailures(e.target.value)}
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <Label>重复推送间隔（分钟，0=每次失败都推）</Label>
                                    <Input
                                        type="number"
                                        min={0}
                                        value={seRepeat}
                                        onChange={(e) => setSeRepeat(e.target.value)}
                                    />
                                </div>
                                <ChannelChips
                                    channels={channels ?? []}
                                    selected={seChannels}
                                    onToggle={(name) =>
                                        setSeChannels(
                                            seChannels.includes(name)
                                                ? seChannels.filter((x) => x !== name)
                                                : [...seChannels, name],
                                        )
                                    }
                                />
                                <p className="text-xs text-muted-foreground sm:col-span-2">
                                    连续失败达标后推送一次，恢复成功后重置；持续失效时按上方间隔重复提醒。告警会记录到「告警历史」。
                                </p>
                            </div>
                        )}
                    </div>
                </div>
                <div className="sm:col-span-3">
                    <div className="rounded-md border p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <Label>行情简报推送</Label>
                                <p className="mt-1 text-xs text-muted-foreground">
                                    每个标的每隔 N 天推送一次当前价，无需触发告警规则
                                </p>
                            </div>
                            <Switch checked={bnEnabled} onCheckedChange={setBnEnabled} />
                        </div>
                        {bnEnabled && (
                            <div className="mt-4 grid gap-4 sm:grid-cols-2">
                                <div className="space-y-1.5">
                                    <Label>推送间隔（天）</Label>
                                    <Input
                                        type="number"
                                        min={0}
                                        step={0.5}
                                        value={bnDays}
                                        onChange={(e) => setBnDays(e.target.value)}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        支持小数：0.5 = 12 小时；0 = 每次成功轮询都推。每个标的独立计时，从上次简报起算
                                    </p>
                                </div>
                                <ChannelChips
                                    channels={channels ?? []}
                                    selected={bnChannels}
                                    onToggle={(name) =>
                                        setBnChannels(
                                            bnChannels.includes(name)
                                                ? bnChannels.filter((x) => x !== name)
                                                : [...bnChannels, name],
                                        )
                                    }
                                />
                                <p className="text-xs text-muted-foreground sm:col-span-2">
                                    首次成功轮询即推一次，此后按间隔计时；简报会记录到「告警历史」（rule=行情简报）。
                                </p>
                            </div>
                        )}
                    </div>
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
