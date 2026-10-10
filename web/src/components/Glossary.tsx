import { BookOpen, ChevronRight } from "lucide-react";
import { GLOSSARY } from "../glossary";

export default function Glossary() {
  return (
    <details className="panel">
      <summary>
        <ChevronRight size={16} className="chev" />
        <BookOpen size={17} />
        名词看不懂？点这里
        <span className="s">每个词的人话解释</span>
      </summary>
      <div className="inner">
        <div className="gloss-grid">
          {GLOSSARY.map((g) => (
            <div className="gloss-item" key={g.term}>
              <b>{g.term}</b>：{g.plain}
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}
