import { useEffect } from "react";

export function usePageMetadata(title: string, description?: string) {
  useEffect(() => {
    document.title = `${title} | EstraOS`;
    const meta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (meta) {
      meta.content = description || `Explore ${title} in your EstraOS workspace.`;
    }
  }, [title, description]);
}
