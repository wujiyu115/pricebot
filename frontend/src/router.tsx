import { createBrowserRouter } from "react-router-dom"
import { AppLayout } from "@/layouts/app-layout"
import { ChannelsPage } from "@/pages/channels"
import { DashboardPage } from "@/pages/dashboard"
import { RulesPage } from "@/pages/rules"
import { SettingsPage } from "@/pages/settings"
import { TargetsPage } from "@/pages/targets"

export const router = createBrowserRouter([
    {
        element: <AppLayout />,
        children: [
            { path: "/", element: <DashboardPage /> },
            { path: "/targets", element: <TargetsPage /> },
            { path: "/rules", element: <RulesPage /> },
            { path: "/channels", element: <ChannelsPage /> },
            { path: "/settings", element: <SettingsPage /> },
        ],
    },
])
