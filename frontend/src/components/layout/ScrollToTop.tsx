import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronUp } from "lucide-react";
import { useLocation } from "react-router-dom";

import { useGuestHome } from "@/hooks/usePageTitle";

export default function ScrollToTop() {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setVisible(window.scrollY > 300);
    };

    window.addEventListener("scroll", handleScroll);

    return () => {
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  // Not on the landing page. None of the pages it is measured against has
  // one, and on a phone it sat on top of the film's controls and the legal
  // links in the footer. A landing page is read top to bottom once; the
  // product's long lists are where a way back up earns its place.
  const { pathname } = useLocation();
  const guestHome = useGuestHome(pathname);

  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  };

  if (guestHome) return null;

  return (
    <button
      type="button"
      onClick={scrollToTop}
      aria-label={t("common.scrollToTop")}
      // When the button is hidden (page near the top), hide it from AT and
      // pull it out of the tab order so keyboard users don't land on an
      // invisible target. The opacity-only fade animation is preserved.
      aria-hidden={!visible}
      tabIndex={visible ? 0 : -1}
      className={`
        fixed bottom-6 right-6 z-50
        flex items-center justify-center
        w-12 h-12 rounded-full
        bg-brand text-brand-foreground
        hover:bg-brand/90
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2
        transition-opacity duration-300
        ${
          visible
            ? "opacity-100 pointer-events-auto"
            : "opacity-0 pointer-events-none"
        }
      `}
    >
      <ChevronUp className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}