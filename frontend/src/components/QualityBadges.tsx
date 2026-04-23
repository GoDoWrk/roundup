import { evaluateTextQuality, qualityLabels } from "../utils/quality";

interface Props {
  text: string;
}

export function QualityBadges({ text }: Props) {
  const labels = qualityLabels(evaluateTextQuality(text));
  if (labels.length === 0) {
    return <span className="quality-ok">quality ok</span>;
  }

  return (
    <span className="quality-warn">
      {labels.map((label) => (
        <code key={label}>{label}</code>
      ))}
    </span>
  );
}
