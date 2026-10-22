/** 后端 API 类型定义 */

export interface Quote {
    symbol: string
    name: string
    last: number | null
    bid: number | null
    ask: number | null
    open: number | null
    high: number | null
    low: number | null
    prev_close: number | null
    volume: number | null
    turnover: number | null
    time: string
    unit?: string
    /** 源附加信息（smzdm 商城/到手价、manmanbuy 历史最低/价位状态等） */
    extra?: Record<string, unknown>
}

export interface Target {
    id: string
    name: string
    source: string
    symbol: string
    enabled: boolean
    schedule?: "always" | "sge" | "cn_stock" | "hk_stock" | "cn_futures"
    interval_seconds?: number | null
    extra?: Record<string, unknown>
    _status?: {
        last_poll: number | null
        last_error: string | null
        error_count: number
        quote: Quote | null
    }
}

export interface SourceInfo {
    name: string
    description: string
    homepage: string
    known_symbols: Record<string, string>
}

export type RuleType =
    | "cross_above"
    | "cross_below"
    | "pct_move_up"
    | "pct_move_down"
    | "price_move_up"
    | "price_move_down"

export interface Rule {
    id: string
    target_id: string
    target_name?: string
    name: string
    type: RuleType
    threshold: number
    window_minutes: number
    confirm_count: number
    cooldown_minutes: number
    channels: string[]
    enabled: boolean
}

export interface RuleTypeMeta {
    value: RuleType
    label: string
    hint: string
}

export interface ChannelMeta {
    name: string
    display_name: string
    config: Record<string, unknown> & { enabled?: boolean }
}

export interface Alert {
    id: number
    ts: number
    rule_id: string
    target_id: string
    rule_name: string
    price: number | null
    message: string
    channels: string[]
    results: Array<{ channel: string; ok: boolean; detail: string }>
}

export interface Tick {
    ts: number
    price: number
    bid: number | null
    ask: number | null
}

export interface Dashboard {
    engine: { running: boolean; interval_seconds: number }
    counts: {
        targets: number
        targets_enabled: number
        rules: number
        rules_enabled: number
    }
    quotes: Array<{
        target_id: string
        name: string
        symbol: string
        source: string
        enabled: boolean
        quote: Quote | null
        last_error: string | null
    }>
    recent_alerts: Alert[]
    sources: string[]
}

export interface SettingsBundle {
    default_settings: Record<string, unknown>
    user_overrides: Record<string, unknown>
    user_settings: {
        monitor?: {
            interval_seconds?: number
            source_timeout_seconds?: number
            history_retention_days?: number
        }
    }
    version: string
}
