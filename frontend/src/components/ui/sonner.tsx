import { Toaster as SonnerToaster } from "sonner"
import { useTheme } from "@/context/useTheme"

export function Toaster() {
  const { theme } = useTheme()
  return (
    <SonnerToaster
      theme={theme === "dark" ? "dark" : "light"}
      position="bottom-right"
      closeButton
      richColors={false}
      duration={4000}
      toastOptions={{
        classNames: {
          toast:
            "group bg-surface text-ink border border-edge shadow-lg rounded-md text-sm",
          title: "font-medium",
          description: "text-ink-muted",
          actionButton: "bg-brand text-brand-foreground",
          cancelButton: "bg-muted text-ink-muted",
          error: "border-destructive/40",
          success: "border-success/40",
          warning: "border-warning/40",
          info: "border-info/40",
        },
      }}
    />
  )
}
