import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { en, zh, type Dict } from "./dict";

export type Lang = "zh" | "en";

const DICTS: Record<Lang, Dict> = { zh, en };
const STORAGE_KEY = "moneyflow-lang";

type Params = Record<string, string | number>;
/** Fully type-safe selector: t((d) => d.m3.title). A renamed or missing
 *  key fails the build instead of rendering blank. */
export type TFunc = (sel: (d: Dict) => string, params?: Params) => string;

function format(template: string, params?: Params): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, k: string) =>
    String(params[k] ?? `{${k}}`),
  );
}

function detect(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "zh" || saved === "en") return saved;
  } catch {
    /* storage unavailable (private mode) -- fall through to detection */
  }
  return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: TFunc } | null>(
  null,
);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detect);

  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);

  const t: TFunc = (sel, params) => format(sel(DICTS[lang]), params);
  return (
    <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>
  );
}

export function useLang() {
  const ctx = useContext(LangCtx);
  if (!ctx) throw new Error("useLang must be used inside LangProvider");
  return ctx;
}

/** Header toggle: shows the *other* language's label. */
export function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <button
      onClick={() => setLang(lang === "zh" ? "en" : "zh")}
      style={{
        fontSize: 13,
        padding: "4px 12px",
        borderRadius: 6,
        border: "1px solid #ccc",
        background: "#fff",
        cursor: "pointer",
      }}
      aria-label="switch language / 切换语言"
    >
      {lang === "zh" ? "EN" : "中文"}
    </button>
  );
}
