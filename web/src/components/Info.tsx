import { HelpCircle } from "lucide-react";

/** 名词解释气泡：鼠标悬停显示通俗解释。 */
export default function Info({ text }: { text: string }) {
  return (
    <span
      title={text}
      aria-label={text}
      style={{ display: "inline-flex", cursor: "help", color: "var(--text-3)" }}
    >
      <HelpCircle size={13} strokeWidth={2} />
    </span>
  );
}
