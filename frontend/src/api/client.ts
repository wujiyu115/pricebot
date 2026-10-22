import type {
    Alert,
    ChannelMeta,
    Dashboard,
    Rule,
    RuleTypeMeta,
    SettingsBundle,
    SourceInfo,
    Target,
    Tick,
} from "@/types"

export class ApiError extends Error {
    status: number

    constructor(status: number, message: string) {
        super(message)
        this.status = status
        this.name = "ApiError"
    }
}

const DEFAULT_TIMEOUT_MS = 15_000

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
    const init: RequestInit = {
        credentials: "same-origin",
        ...options,
        signal: controller.signal,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers ?? {}),
        },
    }
    try {
        const response = await fetch(`/api${path}`, init)
        if (!response.ok) {
            let detail = response.statusText
            try {
                const body = await response.json()
                detail = body.detail ?? detail
            } catch {
                /* ignore body parse errors */
            }
            throw new ApiError(response.status, detail)
        }
        return (await response.json()) as T
    } finally {
        clearTimeout(timer)
    }
}

// ---------------------------------------------------------------- targets
export const api = {
    listTargets: () => request<{ targets: Target[] }>("/targets").then((r) => r.targets),
    listSources: () => request<{ sources: SourceInfo[] }>("/targets/sources").then((r) => r.sources),
    createTarget: (data: Partial<Target>) => request<{ target: Target }>("/targets", {
        method: "POST",
        body: JSON.stringify(data),
    }).then((r) => r.target),
    updateTarget: (id: string, patch: Partial<Target>) => request<{ target: Target }>(`/targets/${id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
    }).then((r) => r.target),
    deleteTarget: (id: string) => request<{ ok: boolean }>(`/targets/${id}`, { method: "DELETE" }),
    verifySymbol: (data: { source: string; symbol: string; extra?: Record<string, unknown> }) =>
        request<{ ok: boolean; quote: { name: string; last: number; prev_close: number | null; unit: string; time: string } }>(
            "/targets/verify",
            { method: "POST", body: JSON.stringify(data) },
        ),
    searchTargets: (q: string) =>
        request<{ results: Array<{ source: string; symbol: string; name: string; market: string; kind: string }> }>(
            `/targets/search?q=${encodeURIComponent(q)}`,
        ).then((r) => r.results),
    refreshTarget: (id: string) =>
        request<{ ok: boolean; quote: object | null; last_error: string | null }>(
            `/targets/${id}/refresh`,
            { method: "POST" },
        ),
    sendBriefing: () =>
        request<{ ok: boolean; sent: number; total: number; detail?: string; channels?: string[] }>(
            "/dashboard/briefing/send",
            { method: "POST" },
        ),

    // ---------------------------------------------------------------- rules
    listRules: () => request<{ rules: Rule[] }>("/rules").then((r) => r.rules),
    rulesMeta: () =>
        request<{ rule_types: RuleTypeMeta[]; channels: Array<{ name: string; display_name: string }> }>(
            "/rules/meta",
        ),
    createRule: (data: Partial<Rule>) =>
        request<{ rule: Rule }>("/rules", { method: "POST", body: JSON.stringify(data) }).then((r) => r.rule),
    updateRule: (id: string, patch: Partial<Rule>) =>
        request<{ rule: Rule }>(`/rules/${id}`, { method: "PATCH", body: JSON.stringify(patch) }).then((r) => r.rule),
    deleteRule: (id: string) => request<{ ok: boolean }>(`/rules/${id}`, { method: "DELETE" }),

    // --------------------------------------------------------------- prices
    livePrices: () => request<{ targets: Array<{ target: Target; quote: object | null; last_error: string | null }> }>(
        "/prices/live",
    ),
    priceHistory: (targetId: string, hours = 24) =>
        request<{ ticks: Tick[] }>(`/prices/history?target_id=${targetId}&hours=${hours}`).then((r) => r.ticks),
    dailyKline: (symbol: string, days = 120) =>
        request<{ rows: Array<[string, number, number, number, number]> }>(
            `/prices/daily?symbol=${encodeURIComponent(symbol)}&days=${days}`,
        ).then((r) => r.rows),

    // --------------------------------------------------------------- alerts
    listAlerts: (limit = 50) => request<{ alerts: Alert[] }>(`/alerts?limit=${limit}`).then((r) => r.alerts),
    clearAlerts: () => request<{ ok: boolean }>("/alerts", { method: "DELETE" }),

    // ------------------------------------------------------------- channels
    listChannels: () => request<{ channels: ChannelMeta[] }>("/channels").then((r) => r.channels),
    updateChannel: (name: string, patch: { enabled?: boolean; values?: Record<string, unknown> }) =>
        request<{ ok: boolean; version: string }>(`/channels/${name}`, {
            method: "PUT",
            body: JSON.stringify(patch),
        }),
    testChannel: (name: string) =>
        request<{ ok: boolean; channel: string; detail: string }>(`/channels/${name}/test`, { method: "POST" }),

    // ------------------------------------------------------------- settings
    getSettings: () => request<SettingsBundle>("/settings"),
    updateSettings: (patch: Record<string, unknown>, version: string) =>
        request<{ ok: boolean; version: string }>("/settings", {
            method: "PUT",
            body: JSON.stringify({ patch, version }),
        }),
    unsetSettingKey: (path: string) => request<{ ok: boolean }>(`/settings/keys/${path}`, { method: "DELETE" }),

    // ------------------------------------------------------------ dashboard
    dashboard: () => request<Dashboard>("/dashboard"),
}
