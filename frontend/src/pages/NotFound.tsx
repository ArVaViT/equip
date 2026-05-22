import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Home } from "lucide-react"

export default function NotFound() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 text-center">
      <h1 className="text-6xl font-bold text-muted-foreground/30 mb-4">404</h1>
      <h2 className="text-xl font-semibold mb-2">{t("notFound.title")}</h2>
      <p className="text-sm text-muted-foreground mb-6 max-w-md">
        {t("notFound.description")}
      </p>
      <Link to="/">
        <Button>
          <Home className="h-4 w-4 mr-2" strokeWidth={1.75} />
          {t("notFound.goHome")}
        </Button>
      </Link>
    </div>
  )
}
