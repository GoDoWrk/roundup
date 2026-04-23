export interface QualityFlags {
  isBlank: boolean;
  isVeryShort: boolean;
  isRepetitive: boolean;
}

function tokenize(text: string): string[] {
  return (text.toLowerCase().match(/[a-z0-9]+/g) || []).filter(Boolean);
}

export function evaluateTextQuality(text: string): QualityFlags {
  const trimmed = text.trim();
  const tokens = tokenize(trimmed);
  const uniqueTokens = new Set(tokens);

  const isBlank = trimmed.length === 0;
  const isVeryShort = tokens.length > 0 && tokens.length < 8;
  const uniquenessRatio = tokens.length === 0 ? 1 : uniqueTokens.size / tokens.length;
  const isRepetitive = tokens.length >= 8 && uniquenessRatio < 0.5;

  return {
    isBlank,
    isVeryShort,
    isRepetitive
  };
}

export function qualityLabels(flags: QualityFlags): string[] {
  const labels: string[] = [];
  if (flags.isBlank) labels.push("blank");
  if (flags.isVeryShort) labels.push("very short");
  if (flags.isRepetitive) labels.push("repetitive");
  return labels;
}
