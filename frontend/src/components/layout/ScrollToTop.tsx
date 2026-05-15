import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronUp } from "lucide-react";

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

  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  };

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
        bg-primary text-primary-foreground
        hover:bg-primary/90
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2
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