import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Send } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/switch"
import type { ChannelMeta } from "@/types"

/** 每个渠道的可编辑配置字段说明 */
const FIELD_DEFS: Record<string, Array<{ key: string; label: string; placeholder?: string; hint?: string }>> = {
    bark: [
        { key: "server", label: "服务器", placeholder: "https://api.day.app", hint: "自建 bark-server 可改" },
        { key: "device_keys", label: "设备 Key", placeholder: "key1,key2", hint: "App 里复制，多设备逗号分隔" },
        { key: "group", label: "消息分组", placeholder: "PriceBot" },
        { key: "sound", label: "铃声", placeholder: "minuet", hint: "留空 = 默认" },
        { key: "level", label: "推送级别", placeholder: "timeSensitive", hint: "active/timeSensitive/critical 等" },
    ],
    ntfy: [
        { key: "server", label: "服务器", placeholder: "https://ntfy.sh", hint: "可在 NAS 自托管 ntfy" },
        { key: "topic", label: "Topic", placeholder: "my-pricebot-x7k2", hint: "APP 订阅同名 topic；topic 即密码，建议带随机后缀" },
        { key: "priority", label: "优先级", placeholder: "high", hint: "min/low/default/high/urgent（对应 1-5）" },
        { key: "tags", label: "图标 tags", placeholder: "chart_with_upwards_trend", hint: "官方 emoji shortcode，逗号分隔" },
    ],
    telegram: [
        { key: "bot_token", label: "Bot Token", placeholder: "123456:ABC-xxx" },
        { key: "chat_id", label: "Chat ID", placeholder: "-1001234567890" },
    ],
    feishu: [
        { key: "webhook_url", label: "Webhook URL", placeholder: "https://open.feishu.cn/..." },
        { key: "secret", label: "签名密钥", placeholder: "可选" },
    ],
    dingtalk: [
        { key: "webhook_url", label: "Webhook URL", placeholder: "https://oapi.dingtalk.com/..." },
        { key: "secret", label: "加签密钥", placeholder: "SEC..." },
    ],
    wecom: [
        { key: "webhook_url", label: "Webhook URL", placeholder: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...", hint: "群聊 → 添加机器人即得" },
    ],
    webhook: [
        { key: "url", label: "URL", placeholder: "https://example.com/hook" },
        { key: "method", label: "Method", placeholder: "POST" },
    ],
}

function ChannelCard({ channel }: { channel: ChannelMeta }) {
    const queryClient = useQueryClient()
    const [values, setValues] = useState<Record<string, string>>({})
    const fields = FIELD_DEFS[channel.name] ?? []

    useEffect(() => {
        const initial: Record<string, string> = {}
        for (const f of fields) {
            const v = channel.config[f.key]
            initial[f.key] = v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v)
        }
        setValues(initial)
    }, [channel.name]) // eslint-disable-line react-hooks/exhaustive-deps

    const saveMutation = useMutation({
        mutationFn: () =>
            api.updateChannel(channel.name, {
                enabled: !channel.config.enabled,
                values: Object.fromEntries(Object.entries(values).filter(([, v]) => v !== "")),
            }),
        onSuccess: () => {
            toast.success("渠道配置已保存")
            queryClient.invalidateQueries({ queryKey: ["channels"] })
        },
        onError: (err) => toast.error(`保存失败: ${err.message}`),
    })

    const testMutation = useMutation({
        mutationFn: () => api.testChannel(channel.name),
        onSuccess: (r) => {
            if (r.ok) toast.success(`测试推送成功: ${r.detail}`)
            else toast.error(`测试推送失败: ${r.detail}`)
        },
        onError: (err) => toast.error(err.message),
    })

    const setField = (key: string, value: string) => setValues((prev) => ({ ...prev, [key]: value }))

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="flex items-center justify-between text-base">
                    <span className="flex items-center gap-2">
                        {channel.display_name}
                        <Badge variant="outline" className="font-mono text-xs">
                            {channel.name}
                        </Badge>
                    </span>
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                            {channel.config.enabled ? "已启用" : "未启用"}
                        </span>
                        <Switch
                            checked={!!channel.config.enabled}
                            onCheckedChange={() => saveMutation.mutate()}
                        />
                    </div>
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
                {fields.map((f) => (
                    <div key={f.key} className="space-y-1">
                        <Label className="text-xs">{f.label}</Label>
                        <Input
                            value={values[f.key] ?? ""}
                            onChange={(e) => setField(f.key, e.target.value)}
                            placeholder={f.placeholder}
                        />
                        {f.hint && <p className="text-xs text-muted-foreground">{f.hint}</p>}
                    </div>
                ))}
                <div className="flex justify-end gap-2 pt-1">
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={!channel.config.enabled || testMutation.isPending}
                        onClick={() => testMutation.mutate()}
                    >
                        <Send className="size-4" /> 发送测试推送
                    </Button>
                    <Button size="sm" disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                        保存配置
                    </Button>
                </div>
            </CardContent>
        </Card>
    )
}

export function ChannelsPage() {
    const { data: channels } = useQuery({ queryKey: ["channels"], queryFn: api.listChannels })
    const order = ["bark", "ntfy"]
    const sorted = [...(channels ?? [])].sort(
        (a, b) =>
            (order.indexOf(a.name) + 1 || 99) - (order.indexOf(b.name) + 1 || 99) ||
            a.name.localeCompare(b.name),
    )

    return (
        <div className="space-y-4">
            <div>
                <h1 className="text-xl font-semibold">推送渠道</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    Bark 为首选渠道；启用开关后规则触发时按渠道推送。测试推送需要先启用渠道。
                </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
                {sorted.map((c) => (
                    <ChannelCard key={c.name} channel={c} />
                ))}
            </div>
        </div>
    )
}
