import * as React from "react"
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog"
import { cn } from "@/lib/utils"
import { buttonVariants } from "./buttonVariants"

const AlertDialog = AlertDialogPrimitive.Root
const AlertDialogPortal = AlertDialogPrimitive.Portal

const AlertDialogOverlay = React.forwardRef<
  React.ComponentRef<typeof AlertDialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Overlay
    ref={ref}
    className={cn(
      // Frosted glass dim: softer than the previous near-black wash, paired
      // with a real `backdrop-blur-md` so the page behind reads as context
      // (not just darkness). The fallback `bg-black/60` keeps the contrast
      // budget when backdrop-filter is unsupported; under `supports`, the
      // dim drops to `/45` since the blur does the layering work.
      "fixed inset-0 z-50 bg-black/60 backdrop-blur-md supports-[backdrop-filter]:bg-black/45 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className,
    )}
    {...props}
  />
))
AlertDialogOverlay.displayName = AlertDialogPrimitive.Overlay.displayName

const AlertDialogContent = React.forwardRef<
  React.ComponentRef<typeof AlertDialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Content>
>(({ className, ...props }, ref) => (
  <AlertDialogPortal>
    <AlertDialogOverlay />
    <AlertDialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-[50%] top-[50%] z-50 grid w-full max-w-md translate-x-[-50%] translate-y-[-50%] gap-4 border border-border bg-background p-6 shadow-lg sm:rounded-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
        className,
      )}
      {...props}
    />
  </AlertDialogPortal>
))
AlertDialogContent.displayName = AlertDialogPrimitive.Content.displayName

function AlertDialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1.5 text-left", className)} {...props} />
}

function AlertDialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)}
      {...props}
    />
  )
}

const AlertDialogTitle = React.forwardRef<
  React.ComponentRef<typeof AlertDialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props}
  />
))
AlertDialogTitle.displayName = AlertDialogPrimitive.Title.displayName

const AlertDialogDescription = React.forwardRef<
  React.ComponentRef<typeof AlertDialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
))
AlertDialogDescription.displayName = AlertDialogPrimitive.Description.displayName

const AlertDialogAction = React.forwardRef<
  React.ComponentRef<typeof AlertDialogPrimitive.Action>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Action> & {
    variant?: "default" | "destructive"
  }
>(({ className, variant = "default", ...props }, ref) => (
  <AlertDialogPrimitive.Action
    ref={ref}
    className={cn(buttonVariants({ variant }), className)}
    {...props}
  />
))
AlertDialogAction.displayName = AlertDialogPrimitive.Action.displayName

const AlertDialogCancel = React.forwardRef<
  React.ComponentRef<typeof AlertDialogPrimitive.Cancel>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Cancel>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Cancel
    ref={ref}
    className={cn(buttonVariants({ variant: "outline" }), className)}
    {...props}
  />
))
AlertDialogCancel.displayName = AlertDialogPrimitive.Cancel.displayName

interface ConfirmOptions {
  title: string
  description?: string
  /** Optional bullet list rendered below ``description``. Use sparingly —
   *  only when the user genuinely needs to see a small list of specific
   *  items before deciding (e.g. "the following critical checks will
   *  ship to students if you publish anyway"). */
  bulletList?: readonly string[]
  confirmLabel?: string
  cancelLabel?: string
  tone?: "default" | "destructive"
}

interface PromptOptions {
  title: string
  description?: string
  placeholder?: string
  defaultValue?: string
  confirmLabel?: string
  cancelLabel?: string
  inputType?: "text" | "url"
}

interface ConfirmState extends ConfirmOptions {
  open: boolean
  resolve?: (value: boolean) => void
}

interface PromptState extends PromptOptions {
  open: boolean
  value: string
  resolve?: (value: string | null) => void
}

const ConfirmContext = React.createContext<(opts: ConfirmOptions) => Promise<boolean>>(
  async () => false,
)

const PromptContext = React.createContext<(opts: PromptOptions) => Promise<string | null>>(
  async () => null,
)

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [confirmState, setConfirmState] = React.useState<ConfirmState>({ open: false, title: "" })
  const [promptState, setPromptState] = React.useState<PromptState>({ open: false, title: "", value: "" })

  const confirm = React.useCallback(
    (opts: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        setConfirmState({ ...opts, open: true, resolve })
      }),
    [],
  )

  const prompt = React.useCallback(
    (opts: PromptOptions) =>
      new Promise<string | null>((resolve) => {
        setPromptState({ ...opts, open: true, value: opts.defaultValue ?? "", resolve })
      }),
    [],
  )

  const handleConfirmDone = React.useCallback(
    (value: boolean) => {
      confirmState.resolve?.(value)
      setConfirmState((s) => ({ ...s, open: false, resolve: undefined }))
    },
    [confirmState],
  )

  const handlePromptDone = React.useCallback(
    (value: string | null) => {
      promptState.resolve?.(value)
      setPromptState((s) => ({ ...s, open: false, resolve: undefined }))
    },
    [promptState],
  )

  return (
    <ConfirmContext.Provider value={confirm}>
      <PromptContext.Provider value={prompt}>
        {children}
        <AlertDialog
          open={confirmState.open}
          onOpenChange={(open) => {
            if (!open) handleConfirmDone(false)
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{confirmState.title}</AlertDialogTitle>
              {confirmState.description && (
                <AlertDialogDescription className="whitespace-pre-line">
                  {confirmState.description}
                </AlertDialogDescription>
              )}
              {confirmState.bulletList && confirmState.bulletList.length > 0 && (
                <ul className="mt-3 space-y-1 rounded-md border border-border bg-muted/30 px-4 py-3 text-sm text-foreground">
                  {confirmState.bulletList.map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-wrap-safe">
                      <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted-foreground" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              )}
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel onClick={() => handleConfirmDone(false)}>
                {confirmState.cancelLabel ?? "Cancel"}
              </AlertDialogCancel>
              <AlertDialogAction
                variant={confirmState.tone === "destructive" ? "destructive" : "default"}
                onClick={() => handleConfirmDone(true)}
              >
                {confirmState.confirmLabel ?? "Confirm"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <AlertDialog
          open={promptState.open}
          onOpenChange={(open) => {
            if (!open) handlePromptDone(null)
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{promptState.title}</AlertDialogTitle>
              {promptState.description && (
                <AlertDialogDescription>{promptState.description}</AlertDialogDescription>
              )}
            </AlertDialogHeader>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                handlePromptDone(promptState.value)
              }}
            >
              <input
                autoFocus
                type={promptState.inputType ?? "text"}
                value={promptState.value}
                onChange={(e) => setPromptState((s) => ({ ...s, value: e.target.value }))}
                placeholder={promptState.placeholder}
                // Use the dialog title as the accessible name — the prompt
                // input is the dialog's sole field, so the title IS its label.
                aria-label={promptState.title}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
              <AlertDialogFooter className="mt-4">
                <AlertDialogCancel type="button" onClick={() => handlePromptDone(null)}>
                  {promptState.cancelLabel ?? "Cancel"}
                </AlertDialogCancel>
                <AlertDialogAction type="submit">
                  {promptState.confirmLabel ?? "OK"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </form>
          </AlertDialogContent>
        </AlertDialog>
      </PromptContext.Provider>
    </ConfirmContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useConfirm() {
  return React.useContext(ConfirmContext)
}

// eslint-disable-next-line react-refresh/only-export-components
export function usePrompt() {
  return React.useContext(PromptContext)
}
