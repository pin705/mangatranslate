"use client";

import dynamic from "next/dynamic";
import { LoadingState } from "@/components/states";

// The editor is heavy and purely interactive: load it on the client only.
export const EditorLoader = dynamic(() => import("./editor").then((m) => m.Editor), {
  ssr: false,
  loading: () => (
    <div className="mx-auto w-full max-w-7xl px-4 py-6">
      <LoadingState rows={8} />
    </div>
  ),
});
