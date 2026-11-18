"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Copy, Loader2, RefreshCw, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";

interface PostPack {
  titles: string[];
  description: string;
  hashtags: string[];
  tags: string[];
  research?: { source?: string; videos?: { title: string; views: number; channel?: string }[] };
  created_at?: string | null;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const t = useTranslations("task.postPack");
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      size="icon-sm"
      variant="ghost"
      aria-label={copied ? t("copied") : `${t("copy")} ${label}`}
      className="shrink-0 text-muted-foreground"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </Button>
  );
}

function Field({ label, text, children }: { label: string; text: string; children?: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium text-muted-foreground">{label}</h4>
        <CopyButton text={text} label={label} />
      </div>
      {children ?? <p className="whitespace-pre-wrap break-words text-sm">{text}</p>}
    </div>
  );
}

/** Ready-to-post YouTube Shorts copy for one clip: load the saved pack, or write one. */
export function PostPackPanel({ taskId, clipId, canGenerate }: { taskId: string; clipId: string; canGenerate: boolean }) {
  const t = useTranslations("task.postPack");
  const [pack, setPack] = useState<PostPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = `/api/tasks/${encodeURIComponent(taskId)}/clips/${encodeURIComponent(clipId)}/post-pack`;

  useEffect(() => {
    const controller = new AbortController();
    setPack(null);
    setError(null);
    setLoading(true);
    fetch(path, { cache: "no-store", signal: controller.signal })
      .then(async (response) => (response.ok ? setPack(await response.json()) : setPack(null)))
      .catch(() => undefined)
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path]);

  const generate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const response = await fetch(path, { method: "POST" });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        setError(typeof body?.detail === "string" ? body.detail : t("error"));
        return;
      }
      setPack(body);
    } catch {
      setError(t("error"));
    } finally {
      setGenerating(false);
    }
  };

  if (loading) return null;

  const hashtagLine = pack ? pack.hashtags.map((tag) => `#${tag}`).join(" ") : "";
  const tagLine = pack ? pack.tags.join(", ") : "";
  const everything = pack
    ? [pack.titles[0], "", pack.description, "", `${t("tags")}: ${tagLine}`].join("\n")
    : "";
  const researched = pack?.research?.videos?.length ?? 0;

  return (
    <section className="space-y-3 rounded-xl border p-4" aria-busy={generating}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-semibold"><Sparkles className="size-3.5" />{t("title")}</p>
          <p className="text-xs text-muted-foreground">
            {pack && researched > 0 ? t("basedOn", { count: researched }) : t("subtitle")}
          </p>
        </div>
        {pack && canGenerate && (
          <Button type="button" size="sm" variant="ghost" onClick={() => void generate()} disabled={generating}>
            {generating ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}{t("regenerate")}
          </Button>
        )}
      </div>

      {!pack && canGenerate && (
        <Button type="button" size="sm" onClick={() => void generate()} disabled={generating}>
          {generating ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}{t("generate")}
        </Button>
      )}
      {generating && <p className="text-xs text-muted-foreground" role="status">{t("generating")}</p>}
      {error && <p className="text-xs text-destructive" role="alert">{error}</p>}

      {pack && (
        <div className="space-y-4">
          <div className="space-y-1">
            <h4 className="text-xs font-medium text-muted-foreground">{t("titles")}</h4>
            <ul className="space-y-1">
              {pack.titles.map((title) => (
                <li key={title} className="flex items-center justify-between gap-2 rounded-md bg-muted px-2.5 py-1.5 text-sm">
                  <span className="min-w-0 break-words">{title}</span>
                  <CopyButton text={title} label={t("titles")} />
                </li>
              ))}
            </ul>
          </div>
          <Field label={t("description")} text={pack.description} />
          <Field label={t("hashtags")} text={hashtagLine} />
          <Field label={t("tags")} text={tagLine}>
            <ul className="flex flex-wrap gap-1.5">
              {pack.tags.map((tag) => <li key={tag} className="rounded-md bg-muted px-2 py-0.5 text-xs">{tag}</li>)}
            </ul>
          </Field>
          <Button type="button" size="sm" variant="outline" onClick={() => void navigator.clipboard.writeText(everything)}>
            <Copy className="size-3.5" />{t("copyAll")}
          </Button>
        </div>
      )}
    </section>
  );
}
